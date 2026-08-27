# SOMPO — Monitor de Furto e Incêndio para Máquinas Agrícolas

Projeto acadêmico da **FIAP** para a **Sompo Seguros** (Sprint 3). Sistema IoT embarcado em
máquina agrícola (trator) que detecta **furto/roubo** e **incêndio**, envia telemetria e eventos
para a nuvem, e gera **relatórios de risco** — inclusive um relatório interpretado por IA — para
apoiar a seguradora.

## Arquitetura

```
sensores → ESP32 → Wi-Fi → Supabase (PostgREST)
                                 ↓
                        API em Flask (Python)
                                 ↓
                          LLM (Google Gemini)
                                 ↓
              relatórios: bruto (factual) + risco (interpretado)
```

- **`firmware/`** — código do ESP32 (C++/Arduino, PlatformIO). Lê os sensores, decide na borda o que é
  ocorrência e envia telemetria (a cada 10s) e eventos ao Supabase.
- **`api/`** — API REST em Flask. Lê o Supabase, calcula **scores de risco determinísticos** e gera os
  relatórios, usando o LLM apenas para redigir a análise (nunca para calcular os números).

## Escopo

Apenas **furto/roubo** e **incêndio** — os dois riscos sem cobertura tecnológica em máquinas agrícolas.
Colisão, distância e previsão do tempo estão fora de escopo (máquinas novas já saem com esses sensores).

## Como rodar

### Firmware (`firmware/`)
1. Copie `src/segredos.exemplo.h` para `src/segredos.h` e preencha Wi-Fi + chave publishable do Supabase.
2. Compile com PlatformIO: `pio run`.
3. Rode no simulador **Wokwi** (VS Code: `F1 → Wokwi: Start Simulator`) ou grave num ESP32 físico
   (`pio run -t upload`).

> 🔌 **Montagem e fiação do ESP32** (sensores, pinos e ligações): abra
> [`firmware/montagem_esp32.html`](firmware/montagem_esp32.html) no navegador.
> Se o `pio` não for reconhecido no PowerShell, veja o troubleshooting em
> [`docs/COMO_TESTAR.md`](docs/COMO_TESTAR.md).

### API (`api/`)
Guia completo em [`docs/COMO_TESTAR.md`](docs/COMO_TESTAR.md). Resumo:
```bash
cd api
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m pytest          # 18 testes, sem rede
venv\Scripts\python.exe app.py             # sobe a API em localhost:5000
```
Configuração em `.env` (copie de `.env.example`): URL/secret do Supabase e a chave do Gemini.

**Painel público:** o `GET /` serve o dashboard visual. Para publicá-lo na internet com HTTPS e
login (Docker + Render), veja [`docs/DEPLOY.md`](docs/DEPLOY.md).

## Endpoints da API

| Rota | O que faz |
|------|-----------|
| `GET /` | Painel visual (dashboard) — pede login se `PAINEL_SENHA` estiver definida |
| `GET /saude` | Health check (API + banco) |
| `GET /telemetria` | Últimas leituras de telemetria |
| `GET /eventos` | Eventos (furto/incêndio) do período |
| `GET /scores` | Scores de risco determinísticos por eixo |
| `GET /relatorio/bruto` | Relatório factual |
| `GET /relatorio/risco` | Relatório interpretado pela IA (com fallback gracioso) |

## Segurança

- **Segredos nunca vão para o repositório.** `api/.env` e `firmware/src/segredos.h` estão no
  `.gitignore`; o repositório traz só os modelos (`.env.example`, `segredos.exemplo.h`).
- O ESP32 usa apenas a **publishable key** do Supabase, limitada a INSERT por políticas de RLS
  (`firmware/sql/preparar_supabase.sql`). A **secret key** vive só na API.
- Detalhes e endurecimento em [`docs/SEGURANCA.md`](docs/SEGURANCA.md).

## Stack

ESP32 (Arduino/PlatformIO) · Supabase (PostgREST) · Python/Flask · Google Gemini · Wokwi
