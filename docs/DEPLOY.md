# Deploy — Painel SOMPO público (simples e seguro)

Este guia sobe o **painel + API** (o mesmo app Flask) para a internet com **HTTPS** e
**login**, no [Render](https://render.com) usando o `Dockerfile`. O ESP32 continua
falando direto com o Supabase — publicar o painel **não** muda nada no firmware.

> Por que um app só: a rota `/` serve o dashboard (`static/index.html`) e a página busca
> os dados por caminhos relativos (`/saude`, `/relatorio/risco`, ...). Painel e API sobem
> juntos, na mesma origem — nada de `localhost` no código, nada para reconfigurar.

---

## 1. Antes de expor: rotacione as chaves do Supabase

As chaves atuais já circularam (zip, Downloads). Antes de deixar público, siga
[`SEGURANCA.md`](SEGURANCA.md): gere **novas** chaves publishable/secret e confirme que o
**RLS** está aplicado. Use a **nova secret key** nas variáveis abaixo.

## 2. Escolha o usuário e a senha do painel

O login cobre o site inteiro. Defina:

- `PAINEL_USUARIO` — ex.: `sompo`
- `PAINEL_SENHA` — uma senha forte e aleatória (guarde num gerenciador de senhas)

Enquanto `PAINEL_SENHA` estiver **vazia**, o login fica **desligado** (modo demo local).

## 3. Deploy no Render (via Blueprint)

1. Suba este repositório no GitHub (se ainda não estiver).
2. No Render: **New → Blueprint** e aponte para o repo. Ele lê o [`render.yaml`](../render.yaml)
   (na raiz) e cria o serviço `sompo-painel` (Docker, contexto `api/`, plano free).
3. Em **Environment**, preencha os valores (não ficam no repositório):

   | Variável | Valor |
   |---|---|
   | `SUPABASE_URL` | URL do seu projeto Supabase |
   | `SUPABASE_SECRET_KEY` | a **secret key** nova |
   | `LLM_API_KEY` | chave do Google Gemini |
   | `LLM_MODEL` | `gemini-flash-lite-latest` (já vem preenchida) |
   | `PAINEL_USUARIO` | o usuário do passo 2 |
   | `PAINEL_SENHA` | a senha do passo 2 |

4. **Create** → aguarde o build. Ao final o Render dá uma URL `https://sompo-painel.onrender.com`.
5. Abra a URL: aparece a **tela de login** (`/login`). Depois de logar, o painel carrega os
   scores e eventos do Supabase de ponta a ponta.

> **Plano free:** o serviço hiberna após inatividade; o **primeiro** acesso depois disso
> demora ~50s para acordar. Nos acessos seguintes fica normal.

## 4. (Opcional) Rodar a mesma imagem localmente

Mesma imagem que vai para produção, útil para testar antes:

```bash
# na raiz do repo
docker build -t sompo-painel api
docker run -p 5000:5000 --env-file api/.env sompo-painel
# abre em http://localhost:5000 (com login se PAINEL_SENHA estiver no .env)
```

## 5. (Alternativa) Gunicorn + Nginx via Docker Compose

Além do Render, o repositório traz o stack **Nginx (proxy reverso) + Gunicorn (API Flask)** —
o mesmo desenho de um servidor de produção (ex.: uma VM EC2), mas rodando local, com um comando:

```bash
# na raiz do repo (precisa do Docker Desktop com virtualizacao ligada)
docker compose up --build
# abre em http://localhost:8080
```

O fluxo é `navegador → Nginx (porta 8080) → Gunicorn → Flask`. Arquivos:
[`docker-compose.yml`](../docker-compose.yml) e [`nginx/nginx.conf`](../nginx/nginx.conf). A porta
do Gunicorn (5000) **não** é publicada no host de propósito — o tráfego é obrigado a passar pelo
Nginx, comprovando o proxy reverso.

### Por que o deploy oficial é o Render (e não EC2 + Gunicorn + Nginx)

| Critério | Render (escolhido) | EC2 + Gunicorn + Nginx |
|---|---|---|
| Manutenção do servidor | Nenhuma (plataforma gerencia) | Você gerencia SO, updates, firewall |
| HTTPS/SSL | Automático | Manual (Certbot/Let's Encrypt) |
| Custo | Free tier | Free tier 12 meses, depois pago |
| Deploy | `git push` → redeploy | Configurar systemd, Nginx, deploy manual |
| Controle de infra | Menor | Total |

Para um projeto acadêmico com foco em **arquitetura, segurança e integração IoT**, o Render
entrega o painel no ar com HTTPS e zero manutenção, sem custo. O stack Gunicorn + Nginx fica
documentado e versionado como alternativa reproduzível (Docker Compose), demonstrando o domínio
do modelo de produção sem o overhead de manter um servidor.

## Segurança em resumo

- **HTTPS** do Render — os dados da seguradora não trafegam em texto puro.
- **Login obrigatório** no site inteiro (página `/login` + sessão sobre HTTPS, comparação em tempo
  constante). Sem a senha, ninguém com a URL vê os dados.
- **Segredos fora do repo** — só em variáveis de ambiente do Render; o `.dockerignore`
  garante que `.env` nunca entra na imagem.
- **Seguro por configuração** — sem `PAINEL_SENHA`, a demo local segue aberta; em produção,
  basta preencher a senha.
