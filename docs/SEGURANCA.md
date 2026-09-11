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
| `SOMPO_API_KEY` | vazio (sem auth) | uma chave forte e aleatória |
| `CORS_ORIGINS` | vazio | origens do seu frontend, separadas por vírgula |
| `PAINEL_SENHA` | vazio (painel aberto) | senha forte — liga o login do painel |
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
