#!/usr/bin/env python3
"""Servidor MCP (stdio) que expõe o Codex CLI como ferramentas para o Claude Code.

Sem dependências externas: fala JSON-RPC 2.0 delimitado por linha (transporte stdio do
MCP) e delega o trabalho ao binário `codex` já instalado (`codex exec` / `codex review`).

Ferramentas expostas:
  codex_ask     - consulta read-only (segunda opinião, análise, debug); não altera arquivos.
  codex_review  - revisão de código do diff (uncommitted / contra uma branch / de um commit).
  codex_edit    - Codex implementa mudanças no workspace (sandbox workspace-write).
  codex_resume  - continua a última sessão do Codex (ou uma sessão por id) com nova mensagem.
  codex_status  - versão do binário, diretório padrão e checagem de autenticação.

Registro no Claude Code (escopo de usuário, vale para todos os projetos):
  copie este arquivo para ~/.claude/mcp/ e rode
  claude mcp add --scope user codex -- python <home>/.claude/mcp/codex_mcp_server.py
Ou por projeto, num .mcp.json na raiz:
  {"mcpServers": {"codex": {"command": "python", "args": ["tools/codex-mcp/codex_mcp_server.py"]}}}

Variáveis de ambiente opcionais:
  CODEX_BIN              caminho do executável (padrão: "codex" no PATH)
  CODEX_MCP_CWD          diretório de trabalho padrão (padrão: cwd do processo)
  CODEX_MCP_TIMEOUT      timeout padrão em segundos (padrão: 900)
  CODEX_MCP_MODEL        modelo padrão passado em `-m` (padrão: o do config.toml do Codex)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

SERVER_NAME = "codex-mcp"
SERVER_VERSION = "1.0.0"
PROTOCOL_FALLBACK = "2025-06-18"
DEFAULT_TIMEOUT = int(os.environ.get("CODEX_MCP_TIMEOUT", "900"))
DEFAULT_CWD = os.environ.get("CODEX_MCP_CWD") or os.getcwd()
DEFAULT_MODEL = os.environ.get("CODEX_MCP_MODEL") or None
MAX_OUTPUT_CHARS = 60_000

_write_lock = threading.Lock()


# ----------------------------------------------------------------------------- util

def log(msg: str) -> None:
    print(f"[{SERVER_NAME}] {msg}", file=sys.stderr, flush=True)


def codex_bin() -> str:
    override = os.environ.get("CODEX_BIN")
    if override:
        return override
    found = shutil.which("codex")
    if not found:
        raise RuntimeError(
            "Executável `codex` não encontrado no PATH. Instale o Codex CLI ou defina CODEX_BIN."
        )
    return found


def resolve_cwd(value: str | None) -> str:
    cwd = Path(value or DEFAULT_CWD).expanduser()
    if not cwd.is_dir():
        raise ValueError(f"Diretório inexistente: {cwd}")
    return str(cwd.resolve())


_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def strip_ansi(text: str) -> str:
    """Remove códigos de cor/cursor do console do codex (chegam mesmo sem TTY)."""
    return _ANSI.sub("", text)


def truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    """Corta pelo MEIO: a conclusão do Codex fica no fim da saída, então o fim é preservado."""
    if len(text) <= limit:
        return text
    head, tail = limit // 3, limit - limit // 3
    return (text[:head] + f"\n\n[... {len(text) - limit} caracteres omitidos no meio ...]\n\n"
            + text[-tail:])


class Cancelled(Exception):
    """Chamada cancelada pelo cliente (notifications/cancelled)."""


# Subprocessos em andamento, por id da requisição JSON-RPC, para poder cancelá-los.
_running: dict = {}
_cancelled: set = set()
_running_lock = threading.Lock()
_current_request = threading.local()   # .id = id da requisição atendida por esta thread


def _register(proc) -> None:
    req_id = getattr(_current_request, "id", None)
    with _running_lock:
        _running[req_id] = proc


def _unregister() -> None:
    req_id = getattr(_current_request, "id", None)
    with _running_lock:
        _running.pop(req_id, None)


def _was_cancelled() -> bool:
    req_id = getattr(_current_request, "id", None)
    with _running_lock:
        if req_id in _cancelled:
            _cancelled.discard(req_id)
            return True
        return False


def kill_tree(proc) -> None:
    """Mata o codex E os filhos (sandbox, app-server). Só matar o pai deixa órfãos que
    seguram o pipe de stdout e travam o communicate() para sempre."""
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        else:
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:  # noqa: BLE001 - último recurso: mata ao menos o pai
        try:
            proc.kill()
        except OSError:
            pass


def cancel_request(req_id) -> None:
    """Chamado na thread principal: marca a requisição e mata o codex correspondente."""
    with _running_lock:
        _cancelled.add(req_id)
        proc = _running.get(req_id)
    if proc and proc.poll() is None:
        log(f"cancelando requisição {req_id}: matando codex (pid {proc.pid}) e filhos")
        kill_tree(proc)


def run_codex(args: list[str], *, prompt: str | None, cwd: str, timeout: int,
              last_message_file: bool = True) -> dict:
    """Executa o codex e devolve {'text', 'exit_code', 'stderr_tail'}.

    O prompt vai por stdin (`-`) para não esbarrar em limites/escapes de argumentos. A
    última mensagem do agente é lida do arquivo indicado em `-o` (mais confiável que
    filtrar o stdout, que mistura progresso e logs); `codex review` não tem `-o`, então
    nesse caso (last_message_file=False) a resposta é o próprio stdout.
    """
    exe = codex_bin()
    # ignore_cleanup_errors: um filho órfão pode manter console.log aberto no Windows.
    with tempfile.TemporaryDirectory(prefix="codex-mcp-", ignore_cleanup_errors=True) as tmp:
        out_file = os.path.join(tmp, "last-message.md")
        console_file = os.path.join(tmp, "console.log")
        cmd = [exe, *args]
        if last_message_file:
            cmd += ["-o", out_file]
        if prompt is not None:
            cmd.append("-")
        log("exec: " + " ".join(cmd[:6]) + (" ..." if len(cmd) > 6 else ""))
        # stdout/stderr vão para ARQUIVO, não para pipe: o codex dispara filhos (sandbox,
        # git...) que herdam o handle; se um deles fica órfão e pendurado, um pipe nunca
        # chegaria ao EOF e a chamada travaria mesmo com o codex já encerrado.
        with open(console_file, "wb") as console_fh:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE if prompt is not None else subprocess.DEVNULL,
                stdout=console_fh,
                stderr=subprocess.STDOUT,
                cwd=cwd,
                start_new_session=(os.name != "nt"),   # POSIX: grupo próprio para o killpg
            )
        _register(proc)
        try:
            if prompt is not None:
                try:
                    proc.stdin.write(prompt.encode("utf-8"))
                    proc.stdin.close()
                except OSError:
                    pass  # codex morreu antes de ler o prompt; o exit code conta a história
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                kill_tree(proc)
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    pass
                return {"text": "", "exit_code": -1,
                        "stderr_tail": f"Codex excedeu o timeout de {timeout}s e foi encerrado."}
        finally:
            _unregister()
        if _was_cancelled():
            raise Cancelled()
        console = strip_ansi(Path(console_file).read_bytes().decode("utf-8", errors="replace"))
        last = ""
        if last_message_file:
            if os.path.exists(out_file):
                last = Path(out_file).read_text(encoding="utf-8", errors="replace").strip()
        elif proc.returncode == 0:
            last = console.strip()
        return {"text": last, "exit_code": proc.returncode,
                "stderr_tail": console[-4000:].strip()}


def format_result(res: dict, header: str) -> tuple[str, bool]:
    """Devolve (texto, ok). `ok` vem do código de saída, não do conteúdo do texto."""
    ok = res["exit_code"] == 0
    parts = [header]
    if res["text"]:
        parts.append(truncate(res["text"]))
    if not ok:
        parts.append(f"\n---\n⚠ codex terminou com código {res['exit_code']}.")
        if res["stderr_tail"]:
            parts.append("Últimas linhas do console:\n```\n" + res["stderr_tail"] + "\n```")
    elif not res["text"]:
        parts.append("(o Codex não produziu mensagem final)\n```\n" + res["stderr_tail"] + "\n```")
    return "\n\n".join(parts), ok


def common_flags(model: str | None) -> list[str]:
    flags: list[str] = []
    chosen = model or DEFAULT_MODEL
    if chosen:
        flags += ["-m", chosen]
    return flags


# ----------------------------------------------------------------------------- tools

def tool_codex_ask(a: dict) -> tuple[str, bool]:
    cwd = resolve_cwd(a.get("cwd"))
    timeout = int(a.get("timeout_seconds") or DEFAULT_TIMEOUT)
    args = ["exec", "-s", "read-only", "-C", cwd, *common_flags(a.get("model"))]
    res = run_codex(args, prompt=a["prompt"], cwd=cwd, timeout=timeout)
    return format_result(res, f"## Codex (read-only) — {cwd}")


def tool_codex_review(a: dict) -> tuple[str, bool]:
    cwd = resolve_cwd(a.get("cwd"))
    timeout = int(a.get("timeout_seconds") or DEFAULT_TIMEOUT)
    scope = a.get("scope", "uncommitted")
    if scope == "uncommitted":
        flag, diff_cmd = ["--uncommitted"], "`git status --short`, `git diff HEAD` e `git ls-files --others --exclude-standard` (arquivos novos)"
    elif scope == "base":
        if not a.get("base"):
            raise ValueError("scope='base' exige o parâmetro `base` (nome da branch).")
        flag, diff_cmd = ["--base", a["base"]], f"`git diff {a['base']}...HEAD`"
    elif scope == "commit":
        if not a.get("commit"):
            raise ValueError("scope='commit' exige o parâmetro `commit` (SHA).")
        flag, diff_cmd = ["--commit", a["commit"]], f"`git show {a['commit']}`"
    else:
        raise ValueError("scope deve ser 'uncommitted', 'base' ou 'commit'.")

    instructions = (a.get("instructions") or "").strip()
    if not instructions:
        # Revisão padrão do Codex. `codex review` não aceita -C/-o/-m: cwd via subprocess,
        # modelo via -c, resposta pelo stdout.
        args = ["review"]
        model = a.get("model") or DEFAULT_MODEL
        if model:
            args += ["-c", f'model="{model}"']
        res = run_codex(args + flag, prompt=None, cwd=cwd, timeout=timeout, last_message_file=False)
    else:
        # `codex review --uncommitted/--base/--commit` recusa prompt customizado, então a
        # revisão dirigida roda como `codex exec` read-only lendo o diff pelo git.
        prompt = (
            "Você é um revisor de código adversarial. Não edite nada.\n"
            f"Veja as mudanças com {diff_cmd} e leia os arquivos completos que precisar.\n\n"
            f"Instruções de revisão:\n{instructions}\n\n"
            "Responda com uma lista de achados concretos (arquivo:linha, cenário, impacto), "
            "do mais grave para o menos grave. Se não houver problemas, diga isso explicitamente."
        )
        args = ["exec", "-s", "read-only", "-C", cwd, *common_flags(a.get("model"))]
        res = run_codex(args, prompt=prompt, cwd=cwd, timeout=timeout)
    return format_result(res, f"## Revisão do Codex ({scope}) — {cwd}")


def tool_codex_edit(a: dict) -> tuple[str, bool]:
    cwd = resolve_cwd(a.get("cwd"))
    timeout = int(a.get("timeout_seconds") or DEFAULT_TIMEOUT)
    args = ["exec", "-s", "workspace-write", "-C", cwd, *common_flags(a.get("model"))]
    for extra in a.get("add_dirs") or []:
        args += ["--add-dir", str(extra)]
    res = run_codex(args, prompt=a["prompt"], cwd=cwd, timeout=timeout)
    diff = ""
    try:
        diff = subprocess.run(["git", "status", "--short"], cwd=cwd, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=30).stdout
    except Exception:  # noqa: BLE001 - git ausente ou fora de repo: apenas omite
        pass
    body, ok = format_result(res, f"## Codex (workspace-write) — {cwd}")
    if diff.strip():
        body += "\n\n### git status --short após a execução\n```\n" + diff.strip() + "\n```"
    return body, ok


def tool_codex_resume(a: dict) -> tuple[str, bool]:
    cwd = resolve_cwd(a.get("cwd"))
    timeout = int(a.get("timeout_seconds") or DEFAULT_TIMEOUT)
    sandbox = a.get("sandbox", "read-only")
    if sandbox not in ("read-only", "workspace-write"):
        raise ValueError("sandbox deve ser 'read-only' ou 'workspace-write'.")
    args = ["exec", "-s", sandbox, "-C", cwd, *common_flags(a.get("model")), "resume"]
    args += [a["session_id"]] if a.get("session_id") else ["--last"]
    res = run_codex(args, prompt=a["prompt"], cwd=cwd, timeout=timeout)
    return format_result(res, f"## Codex (sessão retomada, {sandbox}) — {cwd}")


def tool_codex_status(a: dict) -> tuple[str, bool]:
    try:
        exe = codex_bin()
    except RuntimeError as e:
        return f"❌ {e}", False
    version = subprocess.run([exe, "--version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=30).stdout.strip()
    lines = [f"executável: {exe}", f"versão: {version}", f"cwd padrão: {DEFAULT_CWD}",
             f"timeout padrão: {DEFAULT_TIMEOUT}s", f"modelo padrão: {DEFAULT_MODEL or '(config.toml do Codex)'}"]
    try:
        login = subprocess.run([exe, "login", "status"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=30)
        lines.append("login: " + (login.stdout or login.stderr).strip().splitlines()[-1])
    except Exception as e:  # noqa: BLE001
        lines.append(f"login: não foi possível verificar ({e})")
    return "\n".join(lines), True


TOOLS = [
    {
        "name": "codex_ask",
        "description": (
            "Pede uma análise, segunda opinião ou investigação ao Codex em modo read-only "
            "(ele pode ler arquivos e rodar comandos que não escrevem). Use para: revisar um "
            "trecho, explicar um bug, comparar abordagens, verificar uma hipótese. Nunca altera arquivos."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Instrução completa para o Codex, com o contexto necessário (arquivos, objetivo, formato da resposta)."},
                "cwd": {"type": "string", "description": "Diretório do projeto. Padrão: onde o servidor foi iniciado."},
                "model": {"type": "string", "description": "Modelo do Codex (opcional)."},
                "timeout_seconds": {"type": "integer", "description": f"Timeout em segundos (padrão {DEFAULT_TIMEOUT})."},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "codex_review",
        "description": (
            "Revisão de código pelo Codex. scope='uncommitted' revisa staged+unstaged+untracked; "
            "'base' compara com uma branch; 'commit' revisa um SHA. `instructions` direciona a revisão "
            "(ex.: focar em regressões, segurança, um arquivo específico). Read-only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["uncommitted", "base", "commit"], "default": "uncommitted"},
                "base": {"type": "string", "description": "Branch base quando scope='base' (ex.: main)."},
                "commit": {"type": "string", "description": "SHA quando scope='commit'."},
                "instructions": {"type": "string", "description": "Instruções extras de revisão (opcional)."},
                "cwd": {"type": "string"},
                "model": {"type": "string"},
                "timeout_seconds": {"type": "integer"},
            },
        },
    },
    {
        "name": "codex_edit",
        "description": (
            "O Codex implementa mudanças no projeto (sandbox workspace-write: pode editar arquivos "
            "dentro do cwd e rodar comandos; sem acesso à rede). Devolve a mensagem final do Codex e o "
            "`git status --short` resultante. Use para delegar uma tarefa bem delimitada; revise o diff depois."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Tarefa a implementar, com critérios de aceite e limites (quais arquivos pode/não pode tocar)."},
                "cwd": {"type": "string"},
                "add_dirs": {"type": "array", "items": {"type": "string"}, "description": "Diretórios extras com permissão de escrita."},
                "model": {"type": "string"},
                "timeout_seconds": {"type": "integer"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "codex_resume",
        "description": (
            "Continua a última sessão do Codex (ou uma sessão específica por id) com uma nova mensagem, "
            "preservando o contexto anterior. Útil para pedir ajustes sobre uma revisão/implementação recém-feita."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "session_id": {"type": "string", "description": "Id da sessão; omitido = última sessão."},
                "sandbox": {"type": "string", "enum": ["read-only", "workspace-write"], "default": "read-only"},
                "cwd": {"type": "string"},
                "model": {"type": "string"},
                "timeout_seconds": {"type": "integer"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "codex_status",
        "description": "Mostra versão do Codex, diretório/timeout/modelo padrão e estado do login.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

HANDLERS = {
    "codex_ask": tool_codex_ask,
    "codex_review": tool_codex_review,
    "codex_edit": tool_codex_edit,
    "codex_resume": tool_codex_resume,
    "codex_status": tool_codex_status,
}


# ----------------------------------------------------------------------------- JSON-RPC

def send(msg: dict) -> None:
    data = json.dumps(msg, ensure_ascii=False)
    with _write_lock:
        sys.stdout.buffer.write((data + "\n").encode("utf-8"))
        sys.stdout.buffer.flush()


def reply(req_id, result) -> None:
    send({"jsonrpc": "2.0", "id": req_id, "result": result})


def reply_error(req_id, code: int, message: str) -> None:
    send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def handle(msg: dict) -> None:
    method = msg.get("method")
    req_id = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        reply(req_id, {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL_FALLBACK,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": (
                "Ferramentas que delegam trabalho ao Codex CLI. Prefira codex_ask/codex_review "
                "(read-only) para segunda opinião e revisão; codex_edit escreve no workspace. "
                "Chamadas podem levar minutos: informe o usuário antes de disparar tarefas longas."
            ),
        })
    elif method == "ping":
        reply(req_id, {})
    elif method == "tools/list":
        reply(req_id, {"tools": TOOLS})
    elif method == "tools/call":
        name = params.get("name")
        handler = HANDLERS.get(name)
        if not handler:
            reply_error(req_id, -32601, f"Ferramenta desconhecida: {name}")
            return
        # Cada chamada roda em thread própria para não bloquear pings/cancelamentos.
        def work():
            _current_request.id = req_id
            try:
                text, ok = handler(params.get("arguments") or {})
                reply(req_id, {"content": [{"type": "text", "text": text}], "isError": not ok})
            except Cancelled:
                log(f"requisição {req_id} cancelada; sem resposta")
            except Exception as e:  # noqa: BLE001 - erro vai para o cliente como resultado
                reply(req_id, {"content": [{"type": "text", "text": f"Erro: {e}"}], "isError": True})
        threading.Thread(target=work, daemon=True).start()
    elif method == "notifications/cancelled":
        # Mata o codex da requisição cancelada (senão codex_edit seguiria editando arquivos).
        cancel_request(params.get("requestId"))
    elif method and method.startswith("notifications/"):
        return  # demais notificações não têm resposta
    elif req_id is not None:
        reply_error(req_id, -32601, f"Método não suportado: {method}")


def main() -> None:
    log(f"iniciado (cwd padrão: {DEFAULT_CWD})")
    for raw in sys.stdin.buffer:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            log(f"linha ignorada (JSON inválido): {line[:120]}")
            continue
        if isinstance(msg, list):  # batch
            for m in msg:
                handle(m)
        else:
            handle(msg)
    log("stdin fechado; encerrando")


if __name__ == "__main__":
    main()
