# Deploy — Painel SOMPO na AWS Lambda + Cloudflare Pages

O **painel + API** (o mesmo app Flask) roda na **AWS Lambda** como imagem Docker, exposto por uma
**Function URL** (HTTPS). Na frente dela, um proxy grátis no **Cloudflare Pages** dá a URL limpa:

**https://sompo-painel.pages.dev**

```
navegador ──► Cloudflare Pages  ──► Function URL ──► Lambda (waitress + Lambda Web Adapter) ──► Supabase
             (_worker.js)           (lambda-url…on.aws)      imagem de api/Dockerfile                 │
                                                                                  Google Gemini ◄────┘
```

O ESP32 continua falando direto com o Supabase — publicar o painel **não** muda nada no firmware.

> Por que Lambda: o app é **stateless** (dados no Supabase, sessão em cookie assinado, PDF
> gerado em memória). A Lambda escala a zero sozinha — fica em ~US$ 0 — e acorda em ~1–2 s
> (o Render free levava ~50 s). O Render continua como [plano B](#6-plano-b-render).

---

## 1. Onde roda: AWS Academy Learner Lab

A conta AWS é a do **Learner Lab** da FIAP. Isso impõe regras:

- Região **`us-east-1`** (o lab só libera `us-east-1`/`us-west-2`).
- Não dá para criar roles IAM: a função usa a **`LabRole`** pronta.
- As credenciais são temporárias (por sessão) → **não há deploy automático pelo GitHub**; o deploy
  é o script `infra/deploy-aws.ps1`, rodado à mão.
- A Lambda **continua no ar com o lab encerrado** (testado). EC2 não serviria: para com a sessão.
- ⚠️ **A conta é apagada quando o curso termina.** Aí: novo lab/conta + rodar o script de novo, ou
  voltar ao [Render](#6-plano-b-render) e trocar a `LAMBDA_URL_PADRAO` do proxy (seção 4).

## 2. Variáveis de ambiente (`infra/.env.aws`)

> **Antes de expor numa conta nova:** as chaves antigas do Supabase já circularam (zip, Downloads).
> Siga [`SEGURANCA.md`](SEGURANCA.md): gere **novas** chaves publishable/secret, confirme o **RLS**
> (`firmware/sql/preparar_supabase.sql`) e use a **nova secret key** abaixo. Cadastros de
> validação só em ambiente de teste — preserve os dados existentes.

Copie `infra/.env.aws.example` para `infra/.env.aws` (**gitignorado**) e preencha:

| Variável | Valor |
|---|---|
| `SUPABASE_URL` | a **Project URL** (`https://<ref>.supabase.co`) |
| `SUPABASE_SECRET_KEY` | a **secret/service_role** key (fica só na API) |
| `LLM_API_KEY` / `LLM_MODEL` | chave do Google Gemini / `gemini-flash-lite-latest` |
| `PAINEL_USUARIO` / `PAINEL_SENHA` | credenciais do login do painel (senha **obrigatória**) |
| `SECRET_KEY` | **fixa**: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `SESSAO_HORAS` | `24` |
| `SOMPO_API_KEY` | **VAZIA** |

O script injeta sozinho as fixas do ambiente Lambda: `PORT=8080` (porta do waitress/adapter),
`AWS_LWA_READINESS_CHECK_PATH=/login` (rota que responde sem sessão) e `COOKIE_SEGURO=true`
(cookie `Secure`, só HTTPS).

> ⚠️ **`SOMPO_API_KEY` DEVE ficar VAZIA.** Se preenchida, a API passa a exigir o header `X-API-Key`
> em toda rota de dados, e o painel (que usa a sessão de login) recebe **401** → **dashboard
> vazio**. O script recusa rodar se ela estiver preenchida.
>
> ⚠️ **`SECRET_KEY` precisa ser fixa.** Vazia, o `config.py` gera outra a cada cold start e todo
> mundo é deslogado.

## 3. Deploy pelo AWS CloudShell (recomendado)

> **Banco primeiro.** Mapa da carteira e Ocorrências precisam de `firmware/sql/mapa_ocorrencias.sql`
> (aditivo e repetível: só acrescenta `latitude`/`longitude` em `fazenda` e a tabela `ocorrencias`).
> Rode uma vez no **SQL Editor** do Supabase antes de publicar. Sem ele o painel continua no ar: as
> duas telas mostram um aviso e as rotas respondem 409 `migracao_pendente`.

O CloudShell (ícone `>_` no console) já tem Docker, AWS CLI, git e PowerShell (`pwsh`) com as
credenciais do lab — não precisa de nada instalado no PC.

1. Learner Lab → **Start Lab** → abra o console → região **N. Virginia (us-east-1)** → CloudShell.
2. Primeira vez:
   ```bash
   git clone https://github.com/terrafelipe/sompo-sprint3.git
   cd sompo-sprint3
   cp infra/.env.aws.example infra/.env.aws
   nano infra/.env.aws        # preencher (seção 2); Ctrl+O, Enter, Ctrl+X
   pwsh infra/deploy-aws.ps1
   ```
3. Próximos deploys (o `.env.aws` continua lá):
   ```bash
   cd sompo-sprint3 && git checkout main && git pull && pwsh infra/deploy-aws.ps1
   ```

Confira se a linha `Deploy ok` termina com o hash do commit esperado.

O script é **idempotente**: na 1ª vez cria o repositório ECR, a função (`sompo-painel`, 512 MB,
timeout 60 s, `LabRole`), a Function URL pública com as duas permissões e a retenção de logs de
7 dias; nas seguintes só publica a imagem nova e atualiza as variáveis. No fim imprime a
**Function URL**. O painel faz várias requisições em paralelo, então um teto baixo de concorrência
gera respostas 429. O script remove a reserva de concorrência, e a pausa automática do painel
contém o custo quando ele não está em uso.

### Alternativa: pelo Windows

Precisa do **Docker Desktop** rodando (exige **SVM Mode** ligado na BIOS — em AMD; "Intel VT-x" em
Intel) e do **AWS CLI** (`winget install Amazon.AWSCLI`). Cole as credenciais de **AWS Details**
do lab em `%USERPROFILE%\.aws\credentials` e rode, na raiz do repo:
```powershell
powershell -ExecutionPolicy Bypass -File infra\deploy-aws.ps1
```

## 4. URL limpa: Cloudflare Pages

`infra/pages/_worker.js` (modo avançado do Pages) repassa cada requisição para a Function URL e
devolve a resposta sem alteração. O cookie de sessão não tem `Domain`, então fica gravado no
domínio do Pages, e os redirects do Flask são relativos — o navegador nunca sai do `pages.dev`.
O host de destino é fixo: um caminho `//outro-host` **não** vira proxy aberto.

- **Pelo dashboard** (como foi feito): Workers & Pages → Create → aba **Pages** → **Drag and drop
  your files** → projeto `sompo-painel` → arrastar a pasta `infra/pages` → Deploy. (Não usar
  "Upload your static files" da tela de Workers — isso cria um Worker em `*.workers.dev`.)
- **Atualizar:** projeto `sompo-painel` → **Create deployment** → arrastar a pasta de novo. Ou
  `npx wrangler pages deploy infra/pages --project-name sompo-painel`.
- A URL da Lambda está no próprio `_worker.js` (`LAMBDA_URL_PADRAO`; não é segredo). Uma variável
  `LAMBDA_URL` no projeto Pages, se criada, tem prioridade. Se a Lambda for recriada, atualize e
  publique de novo.
- Deixe o **Cloudflare Access desligado** — o login do Flask já protege o site.

## 5. Verificação e pega-ratões

Depois de cada deploy, pela URL do Pages: login → menus sem máquina → seleção de fazenda/máquina →
F5 (sessão se mantém) → relatório de risco → download do PDF → logout. Rápido pelo terminal:
`/login` → 200, `/saude` → 401 sem login.

- **500 no proxy logo após publicar** → é a propagação da versão nova; some em segundos.
- **Function URL pública precisa de 2 permissões** (`lambda:InvokeFunctionUrl` +
  `lambda:InvokeFunction` com `--invoked-via-function-url`, exigência desde out/2025). O script cria.
- **No `pwsh` do Linux um `*` vira glob** (lista de arquivos). Por isso o script usa
  `--principal=*` grudado.
- **Logs:** CloudWatch → Log groups → `/aws/lambda/sompo-painel`.
- **Créditos do lab:** confira no painel do Learner Lab; o uso normal é praticamente zero.

## 6. Plano B: Render

O `render.yaml` da raiz continua válido (a imagem com o adapter roda normalmente fora da Lambda).
Para voltar: no Render, reative o serviço `sompo-painel` (ou **New → Blueprint** apontando para o
repo), preencha as mesmas variáveis da seção 2 no painel (com `COOKIE_SEGURO=true` e
`SOMPO_API_KEY` **vazia**) e troque a `LAMBDA_URL_PADRAO` do `_worker.js` pela URL do Render. O plano free
hiberna (~50 s no 1º acesso).

## 7. Rodar a mesma imagem localmente

```bash
docker build -t sompo-painel api
docker run -p 5000:5000 --env-file api/.env sompo-painel
# abre em http://localhost:5000 (com login se PAINEL_SENHA estiver no .env)
```
Sem Docker, o modo de desenvolvimento é `cd api && venv\Scripts\python.exe app.py` (ver
[`COMO_TESTAR.md`](COMO_TESTAR.md)).

## 8. Segurança em resumo

- **HTTPS** ponta a ponta (Cloudflare → Function URL) e cookie de sessão `Secure` + `HttpOnly`.
- **Login obrigatório** no site inteiro (`PAINEL_SENHA` definida; o script exige).
- **Segredos fora do repo** — só em `api/.env` / `infra/.env.aws` (gitignorados) e nas envs da
  Lambda; o `.dockerignore` garante que nenhum `.env` entra na imagem.
- **Abuso nos créditos:** a Function URL é pública (o login barra os dados, mas cada acesso
  ainda é uma invocação). O teto de concorrência só vale se a conta aceitar a reserva (ver
  seção 3); na prática o risco é baixo — o free tier cobre 1 milhão de invocações/mês.
- **RLS no Supabase** limita a chave do ESP32 (publishable) a INSERT; a secret key vive só na API.
- Detalhes e endurecimento em [`SEGURANCA.md`](SEGURANCA.md).
