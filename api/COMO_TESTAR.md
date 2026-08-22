# Como testar tudo, do zero

Duas coisas para testar: a **API (Python/Flask)** e o **firmware (ESP32/Wokwi)**.
O roteiro vai do mais simples (sem hardware, sem internet) ao completo (ponta a ponta).
Comandos em **PowerShell** (Windows).

Caminhos:
- API: `C:\Users\USUARIO\Downloads\sompo-sprint3\api`
- Firmware: `C:\Users\USUARIO\Downloads\sompo-sprint3\firmware`

> ⚠️ **Todos os comandos da API rodam de dentro de `api/`**, e o venv fica em `api\venv`.
> Por isso cada bloco abaixo começa com o `cd` — assim dá para copiar e colar em qualquer
> terminal novo, sem depender do bloco anterior. Se você já está na pasta certa, pode pular o `cd`.

---

## 0. Pré-requisitos e setup inicial (uma vez por máquina)

**Requisitos necessários:**
- **Python** instalado (`python --version` deve responder). Usado pela API.
- **PlatformIO** (extensão no VS Code) — só para o firmware (ESP32/Wokwi).
- Acesso a um projeto no **Supabase** (para os passos 3 em diante). Sem ele, dá para
  fazer o passo 1 (testes offline) mesmo assim.

**Setup da API (uma vez, faça sempre que clonar o repo do zero):**
```powershell
cd "C:\Users\USUARIO\Downloads\sompo-sprint3\api"
python -m venv venv                                        # cria o ambiente virtual em api\venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt  # instala as dependências
Copy-Item .env.example .env                                # cria o seu .env a partir do molde
```

> 🔑 **Sobre o `.env`:** ele guarda os segredos (chaves do Supabase, da IA) e é **gitignorado** —
> por isso **não** vem junto quando alguém clona o repo. Cada pessoa/máquina cria o seu **uma vez**
> a partir do `.env.example` e preenche as chaves. Depois fica salvo; não precisa recriar
> a cada execução. O que vai pro repositório é só o `.env.example` (o molde, sem valores).

**Preencher as chaves no `.env`** (do painel do Supabase → **Settings → API**):

| No painel | Onde colar | Observação |
|---|---|---|
| **Project URL** (`https://<ref>.supabase.co`) | `SUPABASE_URL` no `.env` | ⚠️ Use a **Project URL** de Settings → API, **não** o link do navegador (`.../dashboard/project/...`) — senão dá **404**. |
| **service_role / secret key** | `SUPABASE_SECRET_KEY` no `.env` | Fica **só** na API. Nunca no firmware nem no repo. |
| **anon / publishable key** | `SUPABASE_CHAVE_CFG` no `segredos.h` do firmware | É a que vai no ESP32 (ver passo 4). |

As demais variáveis (`LLM_API_KEY`, `SOMPO_API_KEY`, `CORS_ORIGINS`) podem ficar **vazias** — é o
modo demo (ver passos 8 e `SEGURANCA.md`).

> **Banco vazio?** Se as tabelas (`telemetria`, `eventos`, `resumo_diario`) ainda não existem, abra
> o **SQL Editor** do Supabase e rode `firmware/sql/preparar_supabase.sql` uma vez (cria tabelas +
> view + índices + RLS; é idempotente, não apaga dados). Se o projeto já veio com elas, pule.

---

## 1. API offline — testa o código sem internet nem hardware (~2 min)

Com o setup da seção 0 já feito (venv criado e dependências instaladas), basta rodar os testes:
```powershell
cd "C:\Users\USUARIO\Downloads\sompo-sprint3\api"
.\venv\Scripts\python.exe -m pytest
```

> Ainda não fez o setup? Rode antes (uma vez):
> `python -m venv venv` e depois `.\venv\Scripts\python.exe -m pip install -r requirements.txt`.

**Esperado:** `14 passed`. Cobre `scores.py`, as rotas e os 3 cenários do relatório de risco
(com IA / sem chave / provedor fora) — tudo mockado, sem rede. Não precisa de `.env` nem internet.

> Dica: para ativar o venv e não digitar o caminho toda vez: `.\venv\Scripts\Activate.ps1`.
> Se o PowerShell bloquear, rode antes: `Set-ExecutionPolicy -Scope Process RemoteSigned`.

---

## 2. Conexão com o Supabase (~1 min)

```powershell
cd "C:\Users\USUARIO\Downloads\sompo-sprint3\api"
.\venv\Scripts\python.exe scripts\testar_supabase.py
```

**Esperado:** as 3 tabelas (`telemetria`, `eventos`, `resumo_diario`) com **Status 200**.

---

## 3. Subir a API e testar as rotas (~2 min)

Num terminal (deixe rodando):
```powershell
cd "C:\Users\USUARIO\Downloads\sompo-sprint3\api"
.\venv\Scripts\python.exe app.py
```

Em **outro** terminal:
```powershell
cd "C:\Users\USUARIO\Downloads\sompo-sprint3\api"
.\venv\Scripts\python.exe scripts\testar_api.py
```
**Esperado:** as 6 rotas com **PASSOU**.

Testar a rota nova `/scores` (abra no navegador ou use `curl.exe`):
```powershell
curl.exe "http://localhost:5000/scores?dias=7"
curl.exe "http://localhost:5000/relatorio/risco?dias=7"
```
Com o banco vazio, os scores vêm **0** e `origem_da_analise` é `prompt_apenas` — normal.

Para parar a API: `Ctrl+C` no terminal dela.

---

## 4. Firmware no Wokwi — manda dado real ao Supabase (~5 min)

> ⚠️ **Antes de compilar, crie o `segredos.h`** (equivale ao `.env`, é gitignorado e **não** vem
> no clone). Copie o modelo e preencha:
> ```powershell
> cd "C:\Users\USUARIO\Downloads\sompo-sprint3\firmware\src"
> Copy-Item segredos.exemplo.h segredos.h
> ```
> No `segredos.h`: cole a **Project URL** em `SUPABASE_URL_CFG` e a **publishable key**
> (`sb_publishable_...`) em `SUPABASE_CHAVE_CFG`. ⚠️ **Nunca** a service_role/secret aqui — no ESP32
> vai só a publishable (o RLS a limita a INSERT). Sem esse arquivo, `pio run` falha com
> `fatal error: segredos.h: No such file or directory`.

> 💡 **PlatformIO não acha o projeto?** O `platformio.ini` fica em `firmware/`, não na raiz. Abra a
> pasta `firmware/` no VS Code (File → Open Folder), ou rode `pio run` de dentro dela pelo terminal.

1. Confira `firmware\src\segredos.h`. Para o **Wokwi**, já funciona com
   `WIFI_SSID_CFG "Wokwi-GUEST"` e senha vazia. (Para hardware real, use o hotspot do celular.)
2. Compile:
   ```powershell
   cd "C:\Users\USUARIO\Downloads\sompo-sprint3\firmware"
   pio run
   ```
3. No VS Code: `F1` → **"Wokwi: Start Simulator"** (usa `wokwi.toml` + `diagram.json` + o firmware compilado).
4. No Serial Monitor você deve ver `[SISTEMA] Wi-Fi conectado` e, a cada 10s, o envio de telemetria.

**Esperado:** uma linha nova na tabela `telemetria` do painel do Supabase a cada 10s.

> Se aparecer `[REDE] falha no envio` no Serial: provavelmente o RLS está bloqueando o INSERT
> da publishable key. Ver `SEGURANCA.md` (passo 1 — aplicar o RLS).

---

## 4b. Hardware real: conectar no hotspot do celular

O Wokwi usa `"Wokwi-GUEST"`. Para a demo com o **ESP32 físico**, use o hotspot do celular.

**1. No celular, ligar o hotspot em 2.4 GHz** ⚠️ (o ESP32 NÃO enxerga 5 GHz)
- **Android:** Config → Ponto de acesso → **Banda do AP → 2.4 GHz**.
- **iPhone:** ligar **"Maximizar compatibilidade"** (força 2.4 GHz).
- SSID e senha **simples, sem acento nem caractere especial**.
- Deixe os **dados móveis ligados** — é por eles que o ESP32 alcança o Supabase.

**2. Editar `firmware\src\segredos.h`** (troque só estas duas linhas):
```c
#define WIFI_SSID_CFG        "NomeDoSeuHotspot"
#define WIFI_PASSWORD_CFG    "suasenha123"
```

**3. Gravar no ESP32 físico (via USB) e ver o log:**
```powershell
cd "C:\Users\USUARIO\Downloads\sompo-sprint3\firmware"
pio run -t upload
pio device monitor
```
**Esperado:** `[SISTEMA] Wi-Fi conectado, IP ...` e, a cada 10s, o envio de telemetria.

> Opcional, já que agora há internet real: `#define VALIDAR_CERTIFICADO 1` no `app.ino` liga a
> validação de certificado. `0` funciona igual e é mais simples para a demo.

---

## 5. Ver o dado ponta a ponta

- **Painel do Supabase** → Table Editor → `telemetria`: linhas entrando a cada 10s.
- Com a API no ar, os endpoints agora devolvem dado real:
  ```powershell
  curl.exe "http://localhost:5000/telemetria?limite=5"
  curl.exe "http://localhost:5000/relatorio/bruto?dias=7"
  ```

---

## 6. Disparar eventos na banca (Wokwi)

| Evento | Como disparar no Wokwi |
|---|---|
| `operador_nao_autorizado` (roubo) | Gire o **potenciômetro** (pino 34) para cima **sem** apertar o botão do crachá (pino 27). |
| `furto_movimento` | Com o pot **para baixo** (máquina desligada), mude a distância do **HC-SR04** (> 8 cm). |
| `escape_atencao` / `escape_critico` | Suba a **temperatura do DHT22** (mapeada para 300–600 °C; passa de 450/550). |
| `chama_detectada` | Acione o **PIR** (pino 35) depois dos 60 s de aquecimento. |

Confira o resultado:
```powershell
curl.exe "http://localhost:5000/eventos?dias=7"
curl.exe "http://localhost:5000/scores?dias=7"
```
**Esperado:** o evento aparece em `/eventos` e o `score_furto`/`score_incendio` sobe.

---

## 7. Plano B — salvar os JSONs para a apresentação

```powershell
cd "C:\Users\USUARIO\Downloads\sompo-sprint3\api"
.\venv\Scripts\python.exe scripts\salvar_plano_b.py
```
Salva um JSON de cada endpoint em `api\plano_b\`. Rode isso perto da apresentação, com dado real
no banco, para ter o seguro contra falha de Wi-Fi na sala.

---

## 8. Ligar a IA de verdade (relatório interpretado)

Sem chave, o `/relatorio/risco` sai com `origem_da_analise: prompt_apenas` (mostra o prompt com os
dados reais). Para a **IA escrever o relatório**, configure uma chave.

**Como funciona a cadeia** (já implementada):
```
ESP32 → Supabase (eventos/telemetria)
              ↓
    API lê os dados → scores.py calcula o risco (número determinístico)
              ↓
    monta o prompt com dados + scores → envia ao LLM
              ↓
    /relatorio/risco devolve o relatório interpretado
```
O score **nunca** é inventado pela IA — ela só justifica o número calculado pelo `scores.py`.

**1. Conseguir uma API key gratuita do Google Gemini** em
https://aistudio.google.com/apikey (logar com conta Google → "Create API key"). É de graça.

**2. Colar a chave no `.env`:**
```env
LLM_API_KEY=sua-chave-do-gemini
LLM_MODEL=gemini-flash-lite-latest
```
(`gemini-flash-lite-latest` é um alias "lite" — cota maior no tier grátis e menos 503, e não
deprecia. Se der erro de modelo, veja os disponíveis para sua chave com o ListModels:
`GET https://generativelanguage.googleapis.com/v1beta/models` com o header `x-goog-api-key: SUA_CHAVE`.)

**3. Reiniciar a API** (`Ctrl+C` e `python app.py` de novo).

**4. Gerar o relatório:**
```powershell
curl.exe "http://localhost:5000/relatorio/risco?dias=7"
```

**Como saber se funcionou** → campo `origem_da_analise`:
| Valor | Significado |
|---|---|
| `llm` | ✅ a IA escreveu o relatório |
| `prompt_apenas` | não há `LLM_API_KEY` no `.env` |
| `fallback` | tem chave, mas o provedor falhou (chave errada, sem crédito, ou sem internet) |

> Dá para testar a IA **sem o ESP32**: chame `/relatorio/risco` com o banco vazio (a IA responde
> risco baixo por não haver eventos) ou insira 2–3 linhas de teste na tabela `eventos` pelo SQL
> Editor do Supabase.

> **Trocar de provedor?** O `llm.py` está no formato do Google Gemini. Para usar outro (OpenAI,
> Groq, OpenRouter), é só ajustar a função `_chamar_provedor` no `llm.py` — a lógica das 3 origens
> não muda. Me avisa que eu troco.

---

## Se algo falhar
- **`No such file or directory` / `can't open file ...scripts\...` ou `Could not open requirements file`:**
  você está na pasta errada. Rode `cd "C:\Users\USUARIO\Downloads\sompo-sprint3\api"` antes — todos
  os comandos da API rodam de dentro de `api/`, e o venv fica em `api\venv`.
- **`No module named pytest`:** o venv não tem as dependências. Rode
  `.\venv\Scripts\python.exe -m pip install -r requirements.txt` (de dentro de `api/`).
- **pytest falha:** me manda a saída do erro.
- **testar_supabase 401/403:** problema de chave ou RLS — ver `SEGURANCA.md`.
- **ESP32 não conecta no Wokwi:** confira `segredos.h`; no hardware real, use o hotspot.
- **`[REDE] falha` no Serial do ESP32:** RLS bloqueando o INSERT — rodar `sql/preparar_supabase.sql`.
- **quer o relatório com IA de verdade:** preencher `LLM_API_KEY` no `.env` (sem ela a origem fica
  `prompt_apenas`, que é o esperado agora).
