"""Teste de fumaça do servidor MCP: sobe o servidor em subprocesso e conversa por stdio.

Uso: python tools/codex-mcp/smoke_test.py [--ask]
  --ask  também dispara uma chamada real ao Codex (codex_ask), que leva alguns segundos.
"""
import json
import subprocess
import sys
from pathlib import Path

SERVER = Path(__file__).with_name("codex_mcp_server.py")
proc = subprocess.Popen([sys.executable, str(SERVER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, cwd=str(SERVER.parents[2]))


def call(msg):
    proc.stdin.write((json.dumps(msg) + "\n").encode("utf-8")); proc.stdin.flush()
    if "id" not in msg:
        return None
    while True:
        line = proc.stdout.readline()
        if not line:
            raise SystemExit("servidor encerrou: " + proc.stderr.read().decode("utf-8", "replace"))
        resp = json.loads(line)
        if resp.get("id") == msg["id"]:
            return resp


init = call({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "smoke", "version": "0"}}})
assert init["result"]["serverInfo"]["name"] == "codex-mcp", init
call({"jsonrpc": "2.0", "method": "notifications/initialized"})
tools = call({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
print("tools:", [t["name"] for t in tools])
status = call({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "codex_status", "arguments": {}}})
print("codex_status:\n" + status["result"]["content"][0]["text"])
if "--ask" in sys.argv:
    ask = call({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "codex_ask", "arguments": {
        "prompt": "Responda em uma frase: qual é o framework web usado em api/app.py deste repositório?",
        "timeout_seconds": 300}}})
    print("codex_ask:\n" + ask["result"]["content"][0]["text"])
if "--cancel" in sys.argv:
    import time
    before = {int(l.split(",")[1].strip('"')) for l in subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq codex.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout.splitlines() if "codex" in l}
    # envia sem esperar resposta (a chamada vai ser cancelada)
    proc.stdin.write((json.dumps({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "codex_ask", "arguments": {
        "prompt": "Liste todos os arquivos do repositório e resuma cada um em detalhes.", "timeout_seconds": 300}}}) + "\n").encode()); proc.stdin.flush()
    time.sleep(4)
    during = {int(l.split(",")[1].strip('"')) for l in subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq codex.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout.splitlines() if "codex" in l}
    novos = during - before
    print("codex iniciado pelo servidor:", bool(novos))
    call({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 5}})
    time.sleep(2)
    after = {int(l.split(",")[1].strip('"')) for l in subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq codex.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout.splitlines() if "codex" in l}
    print("codex morto após cancelamento:", not (novos & after))
    # o servidor continua respondendo depois do cancelamento
    print("ping após cancelar:", call({"jsonrpc": "2.0", "id": 6, "method": "ping"})["result"] == {})
proc.stdin.close(); proc.wait(timeout=10)
print("OK")
