# Segurança — SOMPO (ESP32 → Supabase → API Flask)

Este documento reúne o endurecimento de segurança aplicado e os **passos manuais**
que precisam ser feitos no painel do Supabase (não dá para automatizar daqui).

Princípio geral: **seguro por padrão, sem quebrar a demo.** Tudo o que poderia
afetar a demo fica atrás de uma flag/variável de ambiente, desligada por padrão.

---

## O que já foi aplicado no código

### Firmware ESP32 (`firmware/sompo_hardware_final/`)
- **Credenciais fora do repositório:** `segredos.h` fica ao lado do `.ino`, gitignorado; o repo traz
  só o `segredos.exemplo.h`.
- **Só a publishable key vai no ESP32** — nunca a service_role. Quem a limita a INSERT são as
  políticas de RLS em `firmware/sql/preparar_supabase.sql`.
- **Certificado TLS validado sempre:** `postarSupabase()` usa `setCACert(SUPABASE_ROOT_CA)` com o CA
  raiz do Supabase (**Google Trust Services – GTS Root R4**, válido até 2036), fechando a porta a
  ataques man-in-the-middle. A flag `VALIDAR_CERTIFICADO` do firmware antigo **não existe mais**: o
  `setInsecure()` só se justificava porque o simulador não trazia o bundle de CAs, e o simulador
  saiu do projeto.
- **`Prefer: return=minimal`** no POST — o Supabase não ecoa o registro gravado, o que economiza RAM
  e evita jogar dado de volta no Serial.

### API Flask
- **`FLASK_DEBUG=false`** por padrão — desliga o debugger interativo (que, exposto,
  permite execução remota de código).
- **`FLASK_HOST=127.0.0.1`** por padrão — a API não fica mais exposta na rede local.
  (O ESP32 fala direto com o Supabase; quem consome a Flask é local.)
- **CORS restrito** por `CORS_ORIGINS` (vazio = nenhuma origem cross-origin liberada).
- **Autenticação opt-in** por `SOMPO_API_KEY`:
  - vazio (padrão) → auth desligada (demo continua aberta);
  - definido → toda rota, **exceto `/saude`**, exige o header `X-API-Key` com esse valor.
- **`waitress`** adicionado às dependências, para servir em produção com um WSGI de
  verdade em vez do servidor de desenvolvimento do Flask.
- **Login do painel opt-in** por `PAINEL_SENHA`: vazio = painel aberto (demo); definido = **todo o
  site** (painel + endpoints) exige login em `/login`. A sessão é assinada por `SECRET_KEY` e
  expira em `SESSAO_HORAS` (padrão 24). Ver [`DEPLOY.md`](DEPLOY.md).
- **Análise de IA cacheada** por prompt (`llm.py`), para não chamar o provedor a cada refresh e
  estourar o limite gratuito (HTTP 429).

### Novas variáveis de ambiente (`.env`)
| Variável | Padrão (demo) | Produção |
|---|---|---|
| `FLASK_DEBUG` | `false` | `false` |
| `FLASK_HOST` | `127.0.0.1` | `127.0.0.1` (atrás de proxy) |
| `SOMPO_API_KEY` | vazio (sem auth) | **vazia** com o painel atual (autenticado por sessão; definida, o painel toma 401) |
| `CORS_ORIGINS` | vazio | origens do seu frontend, separadas por vírgula |
| `PAINEL_SENHA` | vazio (painel aberto) | valor aleatório — **só liga o login**; não é senha de ninguém (logins na tabela `usuario`, com hash) |
| `SECRET_KEY` | aleatória por start | valor fixo e aleatório (mantém a sessão) |
| `SESSAO_HORAS` | `24` | horas até a sessão expirar |

---

## Passos MANUAIS (fazer no painel do Supabase)

> ⚠️ **Para quem cuida do banco:** os dois passos abaixo **não apagam nem alteram
> dados**. O RLS mexe apenas em **permissões** e é **idempotente** (pode rodar de
> novo sem quebrar). A `secret key` da API ignora RLS, então a API continua lendo
> tudo sem precisar mudar uma linha.

### 1. Criar as tabelas e aplicar o RLS — o mais importante
Sem o RLS, a *publishable key* gravada no ESP32 (extraível da flash) funciona como
chave de administrador: pode **apagar a trilha de evidência** e **ler dados de
clientes**. O RLS a limita a apenas INSERT.

1. Abrir o **SQL Editor** no painel do Supabase.
2. Colar e rodar o conteúdo de `firmware/sql/preparar_supabase.sql` — cria as
   tabelas + a view + os índices + o RLS de uma vez (idempotente, não apaga dados).
3. Conferir com as duas queries comentadas no fim do arquivo:
   devem mostrar `rowsecurity = true` e apenas as políticas de INSERT.

### 2. Rotacionar as chaves antes de produção
As chaves atuais já circularam (zip, Downloads). Antes de ir para produção:

1. No painel do Supabase, gerar **novas** publishable e secret keys.
2. Atualizar:
   - `firmware/sompo_hardware_final/segredos.h` → nova **publishable** key;
   - `api/.env` → nova **secret** key.
3. (Opcional) me avisar as chaves novas que eu atualizo os arquivos.

---

## Como ligar o modo produção

### API
```bash
# .env
FLASK_DEBUG=false
FLASK_HOST=127.0.0.1
SOMPO_API_KEY=<uma-chave-aleatoria-forte>
CORS_ORIGINS=https://seu-painel.exemplo.com

# rodar com WSGI de producao (em vez de python app.py)
waitress-serve --host=127.0.0.1 --port=5000 app:app
```
Chamadas passam a exigir o header: `X-API-Key: <a-mesma-chave>` (menos `/saude`).

### Firmware
Nada a mudar: o `setCACert()` com o CA raiz do Supabase já é o caminho único do
`postarSupabase()` — não há flag para desligar a validação.

---

## Auditoria de 2026-09-25 (`/seguranca`)

**Escopo:** código do `main` = `baea1e9` (`C:\dev\sompo-preview`) e o painel rodando **local**
(`127.0.0.1:5055`, login ligado). Em produção, só uma visita normal à página `/login` para ler os
cabeçalhos. Nenhum dado foi gravado no banco: o pentest local fez só leituras (e logins com um
usuário inexistente).

**Ferramentas:** Gitleaks 8.30.1 (histórico + arquivos), pip-audit 2.10.1, leitura guiada por
OWASP Top 10:2025 / LLM Top 10 / insecure-defaults / sharp-edges, e roteiro Python (requests)
com 32 rotas sem login, 17 tentativas de acesso a outra fazenda, força bruta, redirecionamento,
cabeçalhos, cookie, erros e logout.

### Achados (reproduzidos)

| # | Severidade | Onde | Como reproduzir | Correção proposta |
|---|---|---|---|---|
| 1 | **Crítica** | `firmware/sql/usuarios.sql`, `docs/COMO_TESTAR.md`, `api/README.md` (repo **público**) | As senhas de `sompo` (perfil com poder total), `gestor.santarita` e `gestor.valeverde` estão no repositório e **são as mesmas em produção** (3 de 4 contas, conferido no banco sem exibir senhas). Login local com a senha do SQL → 302. | Trocar as 3 senhas no Supabase **já**; tirar senhas do SQL e da documentação (seed com senha gerada na hora); mandar as credenciais aos avaliadores por canal privado (entrega). O histórico do git continua com as antigas, por isso a troca é obrigatória. |
| 2 | Alta | `app.py:149` e `POST /usuarios` (`app.py:693-700`); coluna `usuario.senha` | Senha comparada e gravada em **texto puro**. Quem acessar o banco (ou a chave de serviço) lê todas as senhas. | `werkzeug.security.generate_password_hash` / `check_password_hash` (já vem com o Flask); migração que troca as senhas atuais por hash; teste que prova que o banco não guarda a senha. |
| 3 | Média | `POST /login` | 15 senhas erradas seguidas em 8 s, todas 401, nenhum freio. Somado ao item 2, facilita adivinhar senha fraca. | Limite por usuário + IP (ex.: 5 falhas → espera crescente) e atraso fixo na falha; na Lambda, guardar o contador no Supabase ou usar regra de rate limit da Cloudflare. |
| 4 | Média | `static/index.html:383`, `templates/login.html:13` | `<script src="https://cdn.tailwindcss.com">` sem versão nem SRI, **inclusive na página que recebe a senha**. Se o CDN for comprometido, o script lê a senha e a sessão. O próprio Tailwind diz que o Play CDN não é para produção. | Gerar o CSS com o Tailwind CLI (standalone, sem Node) e servir em `/static`. As outras bibliotecas (Sortable, Leaflet) já usam SRI. |
| 5 | Média | todas as respostas (local e produção) | Ausentes: `Content-Security-Policy`, `X-Frame-Options`/`frame-ancestors` (clickjacking), `X-Content-Type-Options`, `Referrer-Policy`, `Strict-Transport-Security`. | `@app.after_request` com `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: same-origin`, HSTS e CSP em modo *report-only* primeiro (há scripts inline). |
| 6 | Baixa | `api/requirements.txt` | pip-audit: Flask 3.1.0 (→ 3.1.3: `Vary: Cookie`, chave de fallback), Flask-Cors 5.0.0 (→ 6.0.0: casamento de rota CORS; em produção `CORS_ORIGINS` é vazio), requests 2.32.3 (→ 2.33.0: `.netrc`), python-dotenv 1.0.1 (→ 1.2.2: `set_key`, não usado). `pytest` está nas dependências de produção. | Subir as versões, rodar a suíte; mover `pytest` para `requirements-test.txt`. |
| 7 | Baixa | `app.py:349,362,375` (`dias`) | `/relatorio/risco?dias=999999` → 502 (`date value out of range`); valores grandes consultam o histórico inteiro. | `maximum=90` no `_parse_int` (a tela só usa 7/30/90) → 400 limpo. |
| 8 | Baixa | `config.py` (padrões) | Padrões que abrem tudo: `PAINEL_SENHA` vazia = site inteiro sem login; `COOKIE_SEGURO` falso por padrão. Produção está configurada, mas um deploy sem `.env` sobe aberto. | Na Lambda (`AWS_LAMBDA_FUNCTION_NAME` definido), recusar subir sem `PAINEL_SENHA`, `SECRET_KEY` fixa e `COOKIE_SEGURO=true`. |

Descartado na reprodução: redirecionamento aberto com `proximo=/\evil.example`. O servidor
devolve `Location: /%5Cevil.example`, que o navegador trata como caminho do próprio site.

### Correções (branch `fix/seguranca-seletor`, 2026-09-25)

| # | Situação |
|---|---|
| 1 | **Senhas trocadas no Supabase** (3 contas) e retiradas do repo. Achado extra na correção: o **login reserva** do env (`PAINEL_USUARIO`/`PAINEL_SENHA`) aceitava `sompo` + a senha antiga em produção, porque a `PAINEL_SENHA` de lá era essa senha. Reserva removida do código; a `PAINEL_SENHA` de produção precisa ser trocada por um valor aleatório. |
| 2 | Hash (werkzeug) no login e no cadastro; senha legada vira hash no 1º login; `tools/definir_senha.py` e `tools/migrar_senhas_hash.py`. |
| 3 | 5 falhas em 15 min → 429 com `Retry-After` (por instância da Lambda). |
| 4 | Tailwind gerado (`api/static/painel.css`, `login.css`) com o CLI 3.4.17; prints antes/depois idênticos. |
| 5 | `CABECALHOS_SEGURANCA` em toda resposta (CSP, `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`; HSTS com `COOKIE_SEGURO`). Os testes Playwright rodam sob a CSP real. |
| 6 | Flask 3.1.3, Flask-Cors 6.0.0, requests 2.33.0, python-dotenv 1.2.2; `pytest` só no `requirements-test.txt`. `pip-audit` limpo. |
| 7 | `dias` fora de 1..365 → 400 `dias_invalido` nas 6 rotas. |
| 8 | Na Lambda, o app recusa subir sem `PAINEL_SENHA`, `SECRET_KEY` e `COOKIE_SEGURO=true`. |

Revisão cruzada (Codex gpt-6-sol) destas correções, 6 achados, todos corrigidos:
o registro de falhas tem teto e não despeja alvo bloqueado; o IP do limite vem do
`CF-Connecting-IP` só com o segredo `PROXY_SEGREDO` do Worker (senão, do último
`X-Forwarded-For` que a AWS acrescenta); conta inexistente também calcula hash (sem
enumeração por tempo); a regravação da senha legada não desfaz troca simultânea e não põe
a senha na URL; limpar o seletor limpa o filtro na hora; além de 5 falhas por usuário+IP, 20
falhas por IP (qualquer nome) travam o IP. Limite aceito: os contadores valem por instância da
Lambda e um ataque distribuído (muitos IPs) não é coberto.

Informativo: nomes de máquina e fazenda digitados pelo gestor entram no prompt do Gemini
(injeção de prompt). Impacto baixo: os scores são calculados sem IA e o texto da IA vai para a
tela por `textContent`.

### O que passou

- **Segredos no git:** nada real. As ocorrências são o exemplo `SUA_CHAVE` nos READMEs e o
  `api/.env`, que o git ignora.
- **Rotas sem login:** 32 de 32 respondem 401 (leitura e escrita).
- **Autorização (IDOR):** 17 tentativas do gestor em máquina, operador, telemetria, relatório
  (PDF), ocorrências e resumo de outra fazenda, e nas áreas só da Sompo, deram 403/404.
  `?fazenda=<outra>` é ignorado para o gestor.
- **Cookie de sessão:** `HttpOnly` e `SameSite=Lax` (o `Secure` vem de `COOKIE_SEGURO` em produção).
- **Erros:** nenhum stack trace nem detalhe do Supabase nas respostas.
- **Logout** encerra a sessão; **redirecionamento** depois do login só aceita caminho interno.
- **XSS (leitura do código):** dados do banco passam por `escapar()` ou `textContent`, inclusive o
  texto da IA e o `logo_url`.
- **Credencial do ESP32:** `secrets.token_urlsafe(32)`, só o hash SHA-256 vai ao banco,
  resposta com `Cache-Control: no-store`.

### O que não foi testado

- XSS **ao vivo** (evitado para não gravar dado de ataque no banco de produção; coberto pelos
  testes automáticos de `test_painel.py` e `test_clientes_logo.py`).
- Rotas de escrita de um gestor contra outra fazenda ao vivo (verificado só na leitura do código).
- Varredura com Nuclei (o Windows Defender remove o executável).
- RLS do Supabase com a chave anônima usada pelo ESP32, o proxy da Cloudflare e a conta AWS.
- Firmware do ESP32.
