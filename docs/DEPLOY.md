# Deploy — Painel SOMPO público

Este guia sobe o **painel + API** (o mesmo app Flask) para a internet com **HTTPS** e **login**,
numa **VPS/EC2 com Docker + Nginx + Let's Encrypt** (seção 3). O [Render](https://render.com)
continua documentado como plano B na seção 6.

O ESP32 continua falando direto com o Supabase — publicar o painel **não** muda nada no firmware.

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

## 3. Deploy em EC2 (free tier) com Docker + Nginx + HTTPS

### 3.1 Um domínio, antes de tudo

⚠️ **O Let's Encrypt não emite certificado para IP puro.** Sem um domínio apontando para a
instância, não existe HTTPS. Caminho de custo zero: **[DuckDNS](https://duckdns.org)** — login com
Google, escolha um nome (`sompo-fiap.duckdns.org`) e deixe para preencher o IP no passo 3.3.

### 3.2 Criar a instância

1. **EC2 → Launch instance.** AMI **Ubuntu Server 24.04 LTS**, tipo **t3.micro** (free tier).
2. **Key pair:** crie um `.pem` e guarde — é o único jeito de entrar depois.
3. **Security group** — libere as três portas:

   | Tipo | Porta | Origem |
   |---|---|---|
   | SSH | 22 | **só o seu IP** (não `0.0.0.0/0`) |
   | HTTP | 80 | `0.0.0.0/0` (o certbot precisa) |
   | HTTPS | 443 | `0.0.0.0/0` |

4. **Elastic IP:** aloque um e associe à instância. Sem isso o IP muda a cada reboot e o domínio
   aponta para o vazio.

### 3.3 Apontar o domínio

No painel do DuckDNS, cole o Elastic IP no campo `current ip` → **update ip**. Confirme:
```bash
nslookup seu-nome.duckdns.org     # tem de devolver o Elastic IP
```
Só siga quando isso responder certo — o certbot falha se o DNS não resolver.

### 3.4 Preparar o servidor

```bash
ssh -i sua-chave.pem ubuntu@SEU-IP

sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker ubuntu && newgrp docker      # usar docker sem sudo

git clone https://github.com/SEU-USUARIO/sompo-sprint3.git && cd sompo-sprint3
```

### 3.5 Configurar

```bash
cp .env.deploy.example .env && nano .env       # DOMINIO e EMAIL_CERTBOT
cp api/.env.example api/.env  && nano api/.env # SUPABASE_URL, SUPABASE_SECRET_KEY,
                                               # LLM_API_KEY, PAINEL_USUARIO, PAINEL_SENHA
```
⚠️ Defina **`PAINEL_SENHA`** — sem ela o painel fica aberto para qualquer um com a URL.

### 3.6 Emitir o certificado (a ordem importa)

O Nginx não sobe sem o certificado, e o certbot não emite o certificado sem o Nginx servindo a
porta 80. Quebra-se o impasse subindo só o que é preciso:

```bash
# 1. Um Nginx temporário, só na porta 80, servindo o desafio ACME
docker compose -f docker-compose.prod.yml up -d api
docker run --rm -d --name nginx-acme -p 80:80 \
  -v sompo-sprint3_certbot-www:/var/www/certbot \
  nginx:1.27-alpine sh -c "echo 'server{listen 80;location /.well-known/acme-challenge/{root /var/www/certbot;}}' \
  > /etc/nginx/conf.d/default.conf; nginx -g 'daemon off;'"

# 2. Emitir (troque os dois valores pelos do seu .env)
docker compose -f docker-compose.prod.yml run --rm --entrypoint certbot certbot \
  certonly --webroot -w /var/www/certbot \
  -d seu-nome.duckdns.org --email voce@exemplo.com --agree-tos --no-eff-email

# 3. Derrubar o temporário e subir a stack de verdade
docker rm -f nginx-acme
docker compose -f docker-compose.prod.yml up -d --build
```

> 💡 Testando? Acrescente `--staging` ao certbot. A Let's Encrypt limita a **5 emissões por
> domínio por semana**, e é fácil queimar a cota errando o comando. Com `--staging` o certificado
> é inválido para o navegador, mas prova que o fluxo funciona; depois refaça sem a flag.

### 3.7 Conferir

```bash
curl -I http://seu-nome.duckdns.org     # 301 -> https
curl -I https://seu-nome.duckdns.org    # 200, certificado válido
docker compose -f docker-compose.prod.yml logs -f
```
No navegador: cadeado fechado e a tela de `/login`.

A renovação é automática (o serviço `certbot` tenta a cada 12h; o `nginx` recarrega a config no
mesmo intervalo para pegar o certificado novo). Com `restart: always`, a stack volta sozinha
depois de um reboot da instância.

## 4. (Opcional) Rodar a mesma imagem localmente

Mesma imagem que vai para produção, útil para testar antes:

```bash
# na raiz do repo
docker build -t sompo-painel api
docker run -p 5000:5000 --env-file api/.env sompo-painel
# abre em http://localhost:5000 (com login se PAINEL_SENHA estiver no .env)
```

## 5. Stack local (para desenvolver e testar antes de subir)

O mesmo desenho da produção, sem HTTPS, na sua máquina:

```bash
docker compose up --build      # usa docker-compose.yml (nao o .prod.yml)
# abre em http://localhost:8080
```

Fluxo: `navegador → Nginx (8080) → Gunicorn → Flask`. A porta do Gunicorn (5000) **não** é
publicada no host de propósito — o tráfego é obrigado a passar pelo Nginx.

| | `docker-compose.yml` (local) | `docker-compose.prod.yml` (VPS/EC2) |
|---|---|---|
| Porta | 8080 (HTTP) | 80 + 443 (HTTPS) |
| Certificado | nenhum | Let's Encrypt, renovação automática |
| Config do Nginx | `nginx/nginx.conf` | `nginx/prod.conf.template` (envsubst do `${DOMINIO}`) |
| Restart | `unless-stopped` | `always` (sobrevive a reboot) |

## 6. (Plano B) Render via Blueprint

Mantido como alternativa: se o EC2 cair perto da entrega, o Render sobe o painel em minutos.

1. **New → Blueprint**, aponte para o repo. Ele lê o [`render.yaml`](../render.yaml) e cria o
   serviço `sompo-painel` (Docker, contexto `api/`, plano free).
2. Em **Environment**, preencha `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `LLM_API_KEY`,
   `PAINEL_USUARIO` e `PAINEL_SENHA` (não ficam no repositório).
3. Ao final o Render dá uma URL `https://sompo-painel.onrender.com`, já com HTTPS.

> **Plano free:** hiberna após inatividade; o primeiro acesso depois disso demora ~50s.
> Foi justamente essa hibernação, somada à falta de controle sobre o servidor, que motivou a
> migração para o EC2.

### Por que o deploy oficial passou a ser o EC2

| Critério | EC2 + Nginx + Gunicorn (escolhido) | Render |
|---|---|---|
| Controle de infra | Total — é o desenho real de produção | Menor, plataforma decide |
| Disponibilidade | Sempre no ar | Hiberna no free tier (~50s para acordar) |
| HTTPS/SSL | Certbot/Let's Encrypt (automatizado no compose) | Automático |
| Valor didático | Demonstra proxy reverso, TLS e orquestração | Abstrai tudo isso |
| Custo | Free tier 12 meses, depois pago | Free tier permanente |
| Manutenção | Você gerencia SO, updates, firewall | Nenhuma |

Para uma disciplina cujo foco é **arquitetura, segurança e integração IoT**, montar o servidor
demonstra o domínio do modelo de produção — proxy reverso, terminação TLS, renovação de
certificado e orquestração de containers — em vez de delegá-lo a uma plataforma.

## Segurança em resumo

- **HTTPS com certificado válido** (Let's Encrypt) — os dados da seguradora não trafegam em texto
  puro, e a porta 80 só existe para o desafio ACME e o redirect.
- **Login obrigatório** no site inteiro (página `/login` + sessão, comparação em tempo constante).
  Sem a senha, ninguém com a URL vê os dados.
- **Segredos fora do repo** — só em `api/.env` (gitignorado) e no `.env` da raiz; o
  `.dockerignore` garante que nenhum dos dois entra na imagem.
- **SSH restrito ao seu IP** no security group; 80/443 são as únicas portas públicas.
- **Seguro por configuração** — sem `PAINEL_SENHA`, a demo local segue aberta; em produção,
  basta preencher a senha.
