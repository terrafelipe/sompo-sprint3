# SOMPO API

API REST em Flask para consolidação, consulta e análise de risco de incêndio e roubo para o projeto SOMPO da Sprint 3 da FIAP.

## Objetivo

A API consulta dados de telemetria e eventos do Supabase, consolida informações em relatórios diários e prepara uma análise de risco com suporte de IA. O firmware ESP32 envia dados diretamente para o Supabase usando a PUBLISHABLE KEY, e a API Flask acessa dados com a SUPABASE_SECRET_KEY exclusivamente por meio de variáveis de ambiente.

## Arquitetura

- ESP32 -> Supabase (PUBLISHABLE KEY)
- Supabase -> Flask API (SUPABASE_SECRET_KEY)
- Flask API -> consultas, relatórios, IA

## Estrutura de pastas

```text
api/
├── app.py
├── config.py
├── supabase_client.py
├── relatorios.py
├── requirements.txt
├── .env
├── .env.example
├── .gitignore
├── README.md
├── tests/
│   ├── __init__.py
│   ├── test_health.py
│   ├── test_telemetria.py
│   ├── test_eventos.py
│   └── test_relatorios.py
└── scripts/
    ├── testar_api.py
    └── testar_supabase.py
```

## Instalação

### Windows

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

## Configuração do .env

Copie o arquivo `.env.example` para `.env` e ajuste os valores:

```env
SUPABASE_URL=https://SEU-PROJETO.supabase.co
SUPABASE_SECRET_KEY=
LLM_API_KEY=
LLM_MODEL=

FLASK_HOST=127.0.0.1
FLASK_PORT=5000
FLASK_DEBUG=false

# Seguranca (ver SEGURANCA.md)
SOMPO_API_KEY=
CORS_ORIGINS=
```

Variáveis de segurança:
- `SOMPO_API_KEY` — vazio desliga a autenticação (modo demo). Se definido, toda
  rota (menos `/saude`) exige o header `X-API-Key` com esse valor.
- `CORS_ORIGINS` — origens liberadas para CORS, separadas por vírgula. Vazio = nenhuma.

Detalhes e passos manuais (RLS no Supabase, rotação de chaves, modo produção) em
[`SEGURANCA.md`](SEGURANCA.md).

## Execução da API

```bash
python app.py
```

A API ficará disponível em:

- http://localhost:5000

## Execução dos testes

```bash
pytest
```

## Endpoints

### GET /saude

Verifica se a API e o banco estão disponíveis.

### GET /telemetria

Parâmetros:
- `dispositivo` (opcional, padrão: `SOMPO-ESP32`)
- `limite` (opcional, padrão: `50`, máximo: `500`)

Exemplo:

```http
GET /telemetria?dispositivo=SOMPO-ESP32&limite=50
```

### GET /eventos

Parâmetros:
- `dispositivo` (opcional, padrão: `SOMPO-ESP32`)
- `dias` (opcional, padrão: `7`)

Exemplo:

```http
GET /eventos?dispositivo=SOMPO-ESP32&dias=7
```

### GET /resumo

Parâmetros:
- `dispositivo` (opcional, padrão: `SOMPO-ESP32`)
- `dias` (opcional, padrão: `7`)

Exemplo:

```http
GET /resumo?dispositivo=SOMPO-ESP32&dias=10
```

### GET /relatorio/bruto

Exemplo:

```http
GET /relatorio/bruto?dispositivo=SOMPO-ESP32&dias=7
```

### GET /relatorio/risco

Exemplo:

```http
GET /relatorio/risco?dispositivo=SOMPO-ESP32&dias=7
```

## Integração com Supabase

A API executa consultas REST no endpoint:

```text
{SUPABASE_URL}/rest/v1/
```

Headers:

```http
apikey: {SUPABASE_SECRET_KEY}
Authorization: Bearer {SUPABASE_SECRET_KEY}
Content-Type: application/json
```

## Integração com IA

A arquitetura foi preparada para a API OpenAI compatível:

```http
POST https://api.openai.com/v1/chat/completions
```

Headers:

```http
Authorization: Bearer {LLM_API_KEY}
Content-Type: application/json
```

Body:

```json
{
  "model": "{LLM_MODEL}",
  "messages": [
    { "role": "user", "content": "PROMPT" }
  ],
  "temperature": 0.2
}
```

Se `LLM_API_KEY` estiver vazia, o endpoint `/relatorio/risco` retorna um JSON com a mensagem de configuração pendente e o prompt gerado, sem quebrar a API.

## Segurança das chaves

- Nunca colocar `SUPABASE_SECRET_KEY` em código-fonte.
- Nunca colocar `LLM_API_KEY` em código-fonte.
- Nunca enviar a secret key para o ESP32.
- A `PUBLISHABLE_KEY` pertence ao firmware.
- A `SUPABASE_SECRET_KEY` pertence exclusivamente à API Flask.
- O arquivo `.env` fica local e não deve entrar no Git.

## Exemplo de resposta

### /saude

```json
{
  "api": "ok",
  "banco": "ok"
}
```

### /telemetria

```json
{
  "total": 10,
  "dados": [
    {
      "id": 1,
      "dispositivo_id": "SOMPO-ESP32",
      "temp_escape": 41.3,
      "umidade_ar": 58.2,
      "chama_detectada": false,
      "vibracao": 0.62,
      "motor_ligado": true,
      "distancia_cm": 137.0,
      "em_movimento": false,
      "nivel_risco": "SEGURO"
    }
  ]
}
```

### /relatorio/bruto

```json
{
  "tipo": "relatorio_bruto",
  "dispositivo": "SOMPO-ESP32",
  "gerado_em": "2026-08-19T12:00:00+00:00",
  "periodo_dias": 7,
  "resumo_por_dia": [],
  "eventos": [],
  "total_eventos": 0
}
```

## Contribuição

Este projeto foi estruturado para a Sprint 3 da FIAP e busca cumprir requisitos de arquitetura, segurança e integração em ambiente IoT.
