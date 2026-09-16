# Deploy — Painel SOMPO no Render

Este guia sobe o **painel + API** (o mesmo app Flask) para a internet com **HTTPS** e **login**,
usando o **[Render](https://render.com)** a partir do `render.yaml` da raiz do repo. O Render lê o
`api/Dockerfile` (imagem com **waitress**) e provê HTTPS automaticamente.

O ESP32 continua falando direto com o Supabase — publicar o painel **não** muda nada no firmware.

> Por que um app só: a rota `/` serve o dashboard (`api/static/index.html`) e a página busca os
> dados por caminhos relativos (`/saude`, `/relatorio/risco`, ...). Painel e API sobem juntos, na
> mesma origem — nada de `localhost` no código, nada para reconfigurar.

---

## 1. Antes de expor: rotacione as chaves do Supabase

As chaves atuais já circularam (zip, Downloads). Antes de deixar público, siga
[`SEGURANCA.md`](SEGURANCA.md): gere **novas** chaves publishable/secret e confirme que o **RLS**
está aplicado (rode `firmware/sql/preparar_supabase.sql`). Use a **nova secret key** nas variáveis
abaixo.

## 2. Escolha o usuário e a senha do painel

O login cobre o site inteiro. Defina:
- `PAINEL_USUARIO` — ex.: `sompo`
- `PAINEL_SENHA` — uma senha forte (guarde num gerenciador de senhas)

Enquanto `PAINEL_SENHA` estiver **vazia**, o login fica **desligado** (modo demo aberto). Os perfis
de acesso (Sompo × Gestor de Fazenda) só funcionam com o login **ligado** — ver o README.

## 3. Deploy pelo Blueprint

1. **New → Blueprint** no painel do Render e aponte para o repositório. Ele lê o
   [`render.yaml`](../render.yaml) e cria o serviço `sompo-painel` (Docker, contexto `api/`, plano
   free).
2. Em **Environment**, preencha as variáveis da seção 4.
3. Ao final o Render dá uma URL `https://sompo-painel.onrender.com`, já com HTTPS. Todo push no
   `main` dispara um novo deploy automaticamente.

> **Plano free:** hiberna após inatividade; o **primeiro acesso** depois disso demora ~50 s para
> acordar. É esperado — basta aguardar o carregamento.

## 4. Variáveis de ambiente (no painel do Render)

As envs com `sync: false` no `render.yaml` **não** ficam no repositório — preencha no Render:

| Variável | Valor |
|---|---|
| `SUPABASE_URL` | a **Project URL** (`https://<ref>.supabase.co`) |
| `SUPABASE_SECRET_KEY` | a **secret/service_role** key (fica só na API) |
| `LLM_API_KEY` | a chave do Google Gemini (para a IA redigir o relatório) |
| `LLM_MODEL` | `gemini-flash-lite-latest` (já vem no `render.yaml`) |
| `PAINEL_USUARIO` / `PAINEL_SENHA` | credenciais do login do painel |
| `SECRET_KEY` | gerada pelo Render (`generateValue`) — mantém a sessão entre deploys |

> ⚠️ **`SOMPO_API_KEY` DEVE ficar VAZIA no Render.** Se preenchida, a API passa a exigir o header
> `X-API-Key` em toda rota de dados, e o painel embutido (que usa a sessão de login, não o header)
> recebe **401** → **dashboard vazio**. O login (`PAINEL_SENHA`) já protege o site. A `SOMPO_API_KEY`
> só faz sentido se um cliente externo (script/outro front) for consumir a API por header.

## 5. (Opcional) Rodar a mesma imagem localmente

Útil para testar a imagem de produção antes de subir (usa o mesmo `api/Dockerfile`/waitress):
```bash
docker build -t sompo-painel api
docker run -p 5000:5000 --env-file api/.env sompo-painel
# abre em http://localhost:5000 (com login se PAINEL_SENHA estiver no .env)
```
Sem Docker, o modo de desenvolvimento é `cd api && venv\Scripts\python.exe app.py` (ver
[`COMO_TESTAR.md`](COMO_TESTAR.md)).

## 6. Segurança em resumo

- **HTTPS** automático do Render — os dados da seguradora não trafegam em texto puro.
- **Login obrigatório** no site inteiro quando `PAINEL_SENHA` está definida (página `/login` +
  sessão, comparação em tempo constante). Sem a senha, ninguém com a URL vê os dados.
- **Segredos fora do repo** — só em `api/.env` (gitignorado) e nas envs do Render; o `.dockerignore`
  garante que o `.env` não entra na imagem.
- **RLS no Supabase** limita a chave do ESP32 (publishable) a INSERT; a secret key vive só na API.
- Detalhes e endurecimento em [`SEGURANCA.md`](SEGURANCA.md).
