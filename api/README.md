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
├── app.py               # rotas Flask + login/auth (opt-in)
├── config.py            # variaveis de ambiente
├── supabase_client.py   # consultas ao Supabase
├── scores.py            # scores de risco deterministicos
├── relatorios.py        # monta os relatorios (bruto/risco)
├── llm.py               # analise redigida pelo Google Gemini
├── documento.py         # gera o relatorio em PDF (fpdf2)
├── requirements.txt
├── .env / .env.example  # segredos (o .env fica local, gitignorado)
├── .gitignore
├── README.md
├── Dockerfile           # imagem de producao (waitress + Lambda Web Adapter) usada na AWS Lambda
├── .dockerignore
├── static/
│   └── index.html       # painel (dashboard) HTML
├── templates/
│   └── login.html       # tela de login (sessao)
└── tests/               # 48 testes (sem rede)
    ├── __init__.py
    ├── conftest.py
    ├── test_health.py
    ├── test_auth.py
    ├── test_telemetria.py
    ├── test_eventos.py
    ├── test_scores.py
    ├── test_relatorios.py
    ├── test_relatorio_risco_origens.py
    ├── test_documento.py
    ├── test_fazendas.py            # cadastro de fazenda/cliente
    ├── test_perfis.py              # controle de acesso por perfil (sompo x gestor)
    └── test_contrato_firmware.py   # firmware (.ino) x schema (.sql) x scores.py
```

> Os guias (COMO_TESTAR, SEGURANCA, DEPLOY) ficam em [`../docs/`](../docs). O deploy na AWS fica
> em [`../infra/`](../infra) (script + proxy do Cloudflare Pages); o `render.yaml` da raiz e o plano B.

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

# Seguranca (ver docs/SEGURANCA.md)
SOMPO_API_KEY=
CORS_ORIGINS=

# Login do painel publico (ver docs/DEPLOY.md)
PAINEL_USUARIO=sompo
PAINEL_SENHA=
SECRET_KEY=
SESSAO_HORAS=24
COOKIE_SEGURO=false
```

Variáveis de segurança:
- `SOMPO_API_KEY` — deve ficar vazia em produção (Lambda) com o painel atual, autenticado por sessão.
  Vazia desliga somente a exigência do header; o login continua ativo. Se definido,
  toda rota (menos `/saude`) exige o header `X-API-Key` com esse valor.
- `CORS_ORIGINS` — origens liberadas para CORS, separadas por vírgula. Vazio = nenhuma.
- `PAINEL_SENHA` — vazio desliga o login do painel (demo local aberta). Se definido, **todo o
  site** (painel + endpoints) exige login em `/login`. `PAINEL_USUARIO` é o usuário (padrão `sompo`).
- `SECRET_KEY` — assina o cookie de sessão; vazio gera uma aleatória por start.
- `SESSAO_HORAS` — horas até a sessão expirar e exigir novo login (padrão 24).
- `COOKIE_SEGURO` — `true` marca o cookie de sessão como `Secure` (só HTTPS). Ligado em
  produção pelo `infra/deploy-aws.ps1`; deixe `false` no dev local em `http://`.

Detalhes e passos manuais (RLS no Supabase, rotação de chaves, modo produção) em
[`docs/SEGURANCA.md`](../docs/SEGURANCA.md). Para publicar o painel na internet, ver
[`docs/DEPLOY.md`](../docs/DEPLOY.md).

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

## Autenticação (header `X-API-Key`)

Para clientes externos, quando `SOMPO_API_KEY` está definida, **toda rota — exceto `/saude`** — exige o
header `X-API-Key` com o valor da chave. Sem o header, ou com valor errado, a API responde
`401` e **não** processa a rota:

```json
{ "erro": "nao_autorizado", "detalhe": "X-API-Key ausente ou invalida" }
```

Exemplo de chamada autenticada (curl):

```bash
curl -H "X-API-Key: SUA_CHAVE" "https://<host-da-api>/telemetria?dispositivo=SOMPO-ESP32"
```

No Postman: aba **Headers** → `Key = X-API-Key`, `Value = SUA_CHAVE`.

Com `SOMPO_API_KEY` vazia, nenhuma rota exige o header. Esta é a configuração do painel
em produção: a sessão de login protege o acesso quando `PAINEL_SENHA` está definida.

## Endpoints

O painel e o login vivem no mesmo app:
- `GET /` — painel (dashboard) HTML. Se `PAINEL_SENHA` estiver definida, redireciona para `/login`.
- `GET/POST /login` e `GET /logout` — tela de login e saída (sessão).

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

### GET /scores

Scores de risco determinísticos por eixo (sem IA). Parâmetros: `dispositivo`, `dias`.

### GET /relatorio/risco.pdf

Mesmo conteúdo do `/relatorio/risco`, porém em PDF (A4) para download. Parâmetros: `equipamento` (ou
`dispositivo`) e `dias`.

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

A análise de risco é **redigida pelo Google Gemini** (Generative Language API). Os números
(scores) são **determinísticos**, calculados em `scores.py` — a IA nunca inventa valores, só
justifica o risco já calculado. A chamada (em `llm.py`) usa:

```http
POST https://generativelanguage.googleapis.com/v1beta/models/{LLM_MODEL}:generateContent
x-goog-api-key: {LLM_API_KEY}
Content-Type: application/json
```

Body:

```json
{
  "contents": [{ "parts": [{ "text": "PROMPT" }] }],
  "generationConfig": { "temperature": 0.2, "responseMimeType": "application/json" }
}
```

O campo `origem_da_analise` na resposta indica o que aconteceu: `llm` (a IA escreveu),
`prompt_apenas` (sem `LLM_API_KEY` — devolve o prompt gerado, sem quebrar a API) ou
`fallback` (tem chave, mas o provedor falhou). Trocar de provedor mexe só em
`_chamar_provedor` de `llm.py`.

> A análise é **cacheada por prompt** (`llm.py`): a mesma situação reaproveita a resposta por
> alguns minutos, evitando chamar o Gemini a cada refresh (o que estourava o limite gratuito — 429).

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
      "criado_em": "2026-08-19T12:00:00+00:00",
      "temp_escape": 41.3,
      "temp_ambiente": 27.4,
      "umidade_ar": 58.2,
      "chama_detectada": null,
      "vibracao": 0.02,
      "motor_ligado": false,
      "capo_aberto": false,
      "tanque_aberto": false,
      "operador_autorizado": false,
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
