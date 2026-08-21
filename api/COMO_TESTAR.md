# Como testar tudo, do zero

Duas coisas para testar: a **API (Python/Flask)** e o **firmware (ESP32/Wokwi)**.
O roteiro vai do mais simples (sem hardware, sem internet) ao completo (ponta a ponta).
Comandos em **PowerShell** (Windows).

Caminhos:
- API: `C:\Users\USUARIO\Downloads\api\api`
- Firmware: `C:\Users\USUARIO\OneDrive - Fiap-Faculdade de Informática e Administração Paulista\FIAP\AICSS\Sompo\sensor-sompo`

---

## 0. Pré-requisitos (uma vez)
- Python instalado (`python --version` deve responder).
- PlatformIO (extensão no VS Code) para o firmware.

---

## 0.b Preparar o Supabase (uma vez, quando tiver acesso ao banco)

O banco começa **vazio e sem tabelas**. Antes de qualquer passo que use o banco (3 em diante):

1. Crie/entre no projeto em [supabase.com](https://supabase.com).
2. Abra o **SQL Editor** e rode o script **`sql/preparar_supabase.sql`** (na pasta do firmware).
   Ele cria as tabelas `telemetria` e `eventos`, a view `resumo_diario`, os índices e o RLS.
   É idempotente — pode rodar de novo sem quebrar.
3. Em **Settings → API**, copie e cole:
   - **Project URL** → `SUPABASE_URL_CFG` no `segredos.h` **e** `SUPABASE_URL` no `.env`.
   - **anon / publishable key** → `SUPABASE_CHAVE_CFG` no `segredos.h` (é a que vai no ESP32).
   - **service_role / secret key** → `SUPABASE_SECRET_KEY` no `.env` (fica só na API).

Feito isso, **todo o resto funciona sem tocar em código** — o schema já bate com o que o ESP32
grava e a API lê. (Confira a conexão com `scripts/testar_supabase.py`, passo 2.)

> O `preparar_supabase.sql` é o **único** script — cria as tabelas do sensor e, se o projeto também
> tiver as tabelas de negócio (cliente/sinistros/etc.), protege essas também. Roda em qualquer caso,
> sem erro (o que não existe é ignorado).

---

## 1. API offline — testa o código sem internet nem hardware (~2 min)

```powershell
cd "C:\Users\USUARIO\Downloads\api\api"
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m pytest
```

**Esperado:** `14 passed`. Cobre `scores.py`, as rotas e os 3 cenários do relatório de risco
(com IA / sem chave / provedor fora) — tudo mockado, sem rede.

> Dica: para ativar o venv e não digitar o caminho toda vez: `.\venv\Scripts\Activate.ps1`.
> Se o PowerShell bloquear, rode antes: `Set-ExecutionPolicy -Scope Process RemoteSigned`.

---

## 2. Conexão com o Supabase (~1 min)

```powershell
.\venv\Scripts\python.exe scripts\testar_supabase.py
```

**Esperado:** as 3 tabelas (`telemetria`, `eventos`, `resumo_diario`) com **Status 200**.

---

## 3. Subir a API e testar as rotas (~2 min)

Num terminal (deixe rodando):
```powershell
.\venv\Scripts\python.exe app.py
```

Em **outro** terminal:
```powershell
cd "C:\Users\USUARIO\Downloads\api\api"
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

1. Confira `sensor-sompo\src\segredos.h`. Para o **Wokwi**, já funciona com
   `WIFI_SSID_CFG "Wokwi-GUEST"` e senha vazia. (Para hardware real, use o hotspot do celular.)
2. Compile:
   ```powershell
   cd "C:\Users\USUARIO\OneDrive - Fiap-Faculdade de Informática e Administração Paulista\FIAP\AICSS\Sompo\sensor-sompo"
   pio run
   ```
3. No VS Code: `F1` → **"Wokwi: Start Simulator"** (usa `wokwi.toml` + `diagram.json` + o firmware compilado).
4. No Serial Monitor você deve ver `[SISTEMA] Wi-Fi conectado` e, a cada 5s, o envio de telemetria.

**Esperado:** uma linha nova na tabela `telemetria` do painel do Supabase a cada 5s.

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

**2. Editar `sensor-sompo\src\segredos.h`** (troque só estas duas linhas):
```c
#define WIFI_SSID_CFG        "NomeDoSeuHotspot"
#define WIFI_PASSWORD_CFG    "suasenha123"
```

**3. Gravar no ESP32 físico (via USB) e ver o log:**
```powershell
cd "C:\Users\USUARIO\OneDrive - Fiap-Faculdade de Informática e Administração Paulista\FIAP\AICSS\Sompo\sensor-sompo"
pio run -t upload
pio device monitor
```
**Esperado:** `[SISTEMA] Wi-Fi conectado, IP ...` e, a cada 5s, o envio de telemetria.

> Opcional, já que agora há internet real: `#define VALIDAR_CERTIFICADO 1` no `app.ino` liga a
> validação de certificado. `0` funciona igual e é mais simples para a demo.

---

## 5. Ver o dado ponta a ponta

- **Painel do Supabase** → Table Editor → `telemetria`: linhas entrando a cada 5s.
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
- **pytest falha:** me manda a saída do erro.
- **testar_supabase 401/403:** problema de chave ou RLS — ver `SEGURANCA.md`.
- **ESP32 não conecta no Wokwi:** confira `segredos.h`; no hardware real, use o hotspot.
- **`[REDE] falha` no Serial do ESP32:** RLS bloqueando o INSERT — rodar `sql/preparar_supabase.sql`.
- **quer o relatório com IA de verdade:** preencher `LLM_API_KEY` no `.env` (sem ela a origem fica
  `prompt_apenas`, que é o esperado agora).
