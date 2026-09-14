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

> **Estado atual do firmware:** placa física com **Wi-Fi ligado** (`USAR_WIFI 1`) e envio ao
> Supabase em produção. Sensores ativos: MPU-6050, AHT10, buzzer, RC522, termopar MAX6675, reed
> do capô e do tanque, GPS. Dois ficam desligados por flag no topo do `.ino`: `USAR_CHAMA 0`
> (módulo KY-026 defeituoso — religar com sensor novo) e `USAR_POT 0` (potenciômetro não montado,
> então o motor conta sempre como "desligado").
>
> Não há HC-SR04 no hardware: `distancia_cm`/`em_movimento` saíram da tabela e entraram
> `temp_ambiente`, `capo_aberto`, `tanque_aberto` e `operador_autorizado`. O evento de furto por
> deslocamento deu lugar a **`furto_adulteracao`** (vibração pelo MPU-6050 com a máquina desligada).
>
> O contrato entre firmware, banco e API é verificado por testes
> (`api/tests/test_contrato_firmware.py`): uma chave nova no `.ino` sem coluna no `.sql`, ou um
> evento que não pontua no `scores.py`, quebra o `pytest`.

## Escopo

Apenas **furto/roubo** e **incêndio** — os dois riscos sem cobertura tecnológica em máquinas agrícolas.
Colisão, distância e previsão do tempo estão fora de escopo (máquinas novas já saem com esses sensores).

## Como rodar

### Firmware (`firmware/`)
Um sketch Arduino, compilado pelo **arduino-cli portátil do próprio repo** (sem instalação global,
sem PlatformIO). Uma vez por máquina:

```powershell
.\firmware\tools\instalar-arduino-cli.ps1      # baixa o CLI + o core ESP32
```

Depois, pelo VS Code (extensão **Arduino Community Edition**, já configurada em
`firmware/sompo_hardware_final/.vscode/`) ou pela linha de comando:

```powershell
.\firmware\tools\arduino-cli.exe --config-file firmware\arduino-cli.yaml `
  compile --fqbn esp32:esp32:esp32 firmware\sompo_hardware_final
```

Placa **ESP32 Dev Module** (`esp32:esp32:esp32`), Monitor Serial em **115200**.

**Flags por sensor:** no topo do `.ino` há uma flag `USAR_<SENSOR>` por sensor. Com a flag em
`0` aquele sensor não é compilado, nenhum pino dele é tocado e o campo correspondente é **omitido**
do JSON (coluna fica `NULL` — mandar `0` seria inventar medição). Serve para isolar um sensor com
defeito ou para o bring-up de um sensor novo: liga-se um por vez, confirmando no Monitor Serial.
Ordem sugerida: `MPU → AHT → BUZZER → RFID/TERMOPAR/CHAMA/REED/POT → WIFI`.

**Envio ao Supabase (`USAR_WIFI 1`):** o POST roda numa tarefa própria no núcleo 0 — o `loop()`
só enfileira, nunca fala com a rede. Duas filas com semânticas diferentes: eventos numa FIFO de 16
que não se perde por falta de cobertura (é a trilha de evidência do sinistro) e telemetria numa
caixa de um slot sobrescrito (a amostra de agora vale mais que a antiga). Exige
`segredos.h` preenchido (copie de `segredos.exemplo.h`; o `setup.ps1` faz isso). Para conferir o
JSON sem rede, ligue `DIAG_TELEMETRIA 1`: o payload é impresso no Serial.

O mapa de pinos e as notas de fiação (AD0 do MPU no GND, RC522 só em 3.3V, I2C compartilhado
entre MPU e AHT de propósito, MAX6675 em pinos próprios fora do SPI do RC522) estão no cabeçalho
do próprio `.ino`.

### API (`api/`)
Guia completo em [`docs/COMO_TESTAR.md`](docs/COMO_TESTAR.md). Resumo:
```bash
cd api
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m pytest          # 32 testes, sem rede
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
| `GET /resumo` | Resumo diário (view `resumo_diario`) |
| `GET /scores` | Scores de risco determinísticos por eixo |
| `GET /relatorio/bruto` | Relatório factual |
| `GET /relatorio/risco` | Relatório interpretado pela IA (com fallback gracioso) |
| `GET /relatorio/risco.docx` | O mesmo relatório como documento Word para download |

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
