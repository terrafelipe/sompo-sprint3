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

- **`firmware/`** — código do ESP32 (C++/Arduino, **Arduino IDE**). Sketch
  `sompo_hardware_final/sompo_hardware_final.ino`.
- **`api/`** — API REST em Flask. Lê o Supabase, calcula **scores de risco determinísticos** e gera os
  relatórios, usando o LLM apenas para redigir a análise (nunca para calcular os números).

> ⚠️ **Estado atual do firmware:** o projeto migrou do simulador para a **placa física**, com um
> conjunto de sensores diferente do que era simulado. O sketch está na fase de **bring-up
> incremental** (um sensor por vez, ver abaixo) e **ainda não tem Wi-Fi nem envio ao Supabase** — a
> etapa de rede será portada depois que todos os sensores estiverem validados no hardware. Enquanto
> isso, a `api/` roda e é testada com os dados já existentes no banco.

## Escopo

Apenas **furto/roubo** e **incêndio** — os dois riscos sem cobertura tecnológica em máquinas agrícolas.
Colisão, distância e previsão do tempo estão fora de escopo (máquinas novas já saem com esses sensores).

## Como rodar

### Firmware (`firmware/`)
Requer a **Arduino IDE** (não PlatformIO). Abra
`firmware/sompo_hardware_final/sompo_hardware_final.ino`, selecione a placa **ESP32 Dev Module**
e grave. Monitor Serial em **115200**.

**Bring-up incremental:** no topo do `.ino` há uma flag `USAR_<SENSOR>` por sensor. Cada flag
protege o `#include`, o objeto global, a init do `setup()`, a chamada no `loop()` e a própria
função `lerX()` — com a flag em `0` aquele sensor não é compilado e nenhum pino dele é tocado.
Liga-se **um por vez**, na ordem `MPU → AHT → BUZZER → RFID/TERMOPAR/CHAMA/REED/POT`, confirmando
cada um na bancada antes de passar para o próximo. Assim o Monitor Serial não enche de leitura de
pino solto e o build nunca quebra por biblioteca ausente.

O mapa de pinos e as notas de fiação (AD0 do MPU no GND, RC522 só em 3.3V, I2C e SPI
compartilhados de propósito) estão no cabeçalho do próprio `.ino`.

### API (`api/`)
Guia completo em [`docs/COMO_TESTAR.md`](docs/COMO_TESTAR.md). Resumo:
```bash
cd api
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m pytest          # 25 testes, sem rede
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

- **Segredos nunca vão para o repositório.** `api/.env` e
  `firmware/sompo_hardware_final/segredos.h` estão no `.gitignore`; o repositório traz só os
  modelos (`.env.example`, `segredos.exemplo.h`).
- **API protegida por chave** (`SOMPO_API_KEY`): em produção, toda rota — exceto `/saude` —
  exige o header `X-API-Key`. Sem ele (ou errado) a resposta é `401`. Exemplo:
  `curl -H "X-API-Key: SUA_CHAVE" https://sua-api.onrender.com/telemetria`.
- O ESP32 usará apenas a **publishable key** do Supabase, limitada a INSERT por políticas de RLS
  (`firmware/sql/preparar_supabase.sql`). A **secret key** vive só na API.
- Detalhes e endurecimento em [`docs/SEGURANCA.md`](docs/SEGURANCA.md).

## Stack

ESP32 (Arduino IDE) · Supabase (PostgREST) · Python/Flask · Google Gemini
