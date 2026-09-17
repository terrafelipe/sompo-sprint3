# codex-mcp — Codex CLI como servidor MCP para o Claude Code

Servidor MCP (transporte stdio) em um único arquivo Python, **sem dependências**, que
expõe o Codex CLI (`codex exec` / `codex review`) como ferramentas. Assim o Claude Code
pode pedir segunda opinião, revisão de código ou delegar uma implementação ao Codex sem
sair da conversa.

## Pré-requisitos

- Python 3.10+ no PATH (`python --version`).
- Codex CLI instalado e logado (`codex login status`). Testado com `codex-cli 0.154`.

## Registro no Claude Code (escopo de usuário — vale para todos os projetos)

O servidor não depende do projeto: cada chamada opera na pasta onde o Claude Code foi
aberto. Por isso a instalação recomendada é copiar o arquivo para um lugar fixo e
registrar no escopo de usuário:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\mcp" | Out-Null
Copy-Item tools\codex-mcp\codex_mcp_server.py "$env:USERPROFILE\.claude\mcp\"
claude mcp add --scope user codex -- python "$env:USERPROFILE\.claude\mcp\codex_mcp_server.py"
claude mcp get codex        # deve mostrar "User config" e "Connected"
```

Depois disso `codex` aparece em `/mcp` em qualquer projeto. Ao atualizar este arquivo no
repo, repita o `Copy-Item`.

Alternativa por projeto: um `.mcp.json` na raiz com
`{"mcpServers": {"codex": {"command": "python", "args": ["tools/codex-mcp/codex_mcp_server.py"]}}}`
(o Claude Code pede aprovação na primeira abertura).

## Ferramentas

| Ferramenta | Sandbox | Para quê |
|---|---|---|
| `codex_ask` | read-only | Segunda opinião, análise, explicar um bug, comparar abordagens. Nunca edita. |
| `codex_review` | read-only | Revisão do diff: `scope` = `uncommitted` (padrão), `base` (+`base`) ou `commit` (+`commit`). `instructions` direciona a revisão. |
| `codex_edit` | workspace-write | Codex implementa uma tarefa delimitada e devolve a mensagem final + `git status --short`. |
| `codex_resume` | read-only / workspace-write | Continua a última sessão do Codex (ou `session_id`) com uma nova mensagem. |
| `codex_status` | — | Versão, cwd/timeout/modelo padrão e estado do login. |

Parâmetros comuns: `cwd` (padrão: pasta onde o Claude Code iniciou o servidor), `model`,
`timeout_seconds` (padrão 900).

Cancelar a chamada no Claude Code (Esc) mata o processo `codex` correspondente — importante
no `codex_edit`, que senão seguiria editando arquivos.

## Fluxo sugerido (Claude + Codex)

1. Claude implementa.
2. `codex_review` com `instructions` focadas (regressões, contrato com o backend, a11y).
3. Claude corrige os achados; `codex_resume` para o Codex re-checar o mesmo ponto.
4. Testes rodam pelo Claude (o sandbox do Codex bloqueia o named pipe do Playwright no Windows).

## Variáveis de ambiente (opcionais, em `.mcp.json` → `env`)

| Variável | Efeito |
|---|---|
| `CODEX_BIN` | Caminho do executável (padrão: `codex` no PATH). |
| `CODEX_MCP_CWD` | Diretório padrão das chamadas. |
| `CODEX_MCP_TIMEOUT` | Timeout padrão em segundos (900). |
| `CODEX_MCP_MODEL` | Modelo padrão (senão vale o `~/.codex/config.toml`). |

## Teste de fumaça

```powershell
python tools\codex-mcp\smoke_test.py            # handshake + tools/list + codex_status
python tools\codex-mcp\smoke_test.py --ask      # + uma chamada real ao Codex
python tools\codex-mcp\smoke_test.py --cancel   # + cancelamento mata o processo codex
```

## Limitações conhecidas

- `codex review --uncommitted/--base/--commit` não aceita instruções customizadas nesta
  versão do CLI (apesar do `--help`); com `instructions` o servidor roda `codex exec`
  read-only pedindo para o Codex ler o diff pelo `git`.
- A saída é cortada pelo meio acima de 60 k caracteres (início e fim preservados).
- Chamadas são síncronas do ponto de vista do Claude: uma revisão grande pode levar
  alguns minutos.
