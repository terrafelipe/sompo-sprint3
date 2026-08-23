# 🎒 Handoff — rodar o sompo-sprint3 ao vivo no notebook (FIAP)

> Cole este arquivo inteiro no Claude Code do notebook. Ele tem tudo pra você
> clonar, configurar e rodar a demo do zero, incluindo o ESP32 físico.

---

## 🎯 O que é o projeto

IoT de risco para seguro. Fluxo:

**ESP32 (sensores)** → grava eventos no **Supabase** (banco na nuvem) → **API Flask (Python)** lê os dados, calcula scores de risco e gera um **relatório em Word (.docx)** com ajuda de IA (Google Gemini).

- Repositório: **https://github.com/terrafelipe/sompo-sprint3**
- Painel web da API: `http://localhost:5000/` (tem botão **📄 Baixar Word**)
- Endpoint do relatório Word: `http://localhost:5000/relatorio/risco.docx`

A apresentação é na segunda: mostrar o **ESP32 físico funcionando** e os dados chegando/relatório sendo gerado.

---

## 🔑 Segredos que você precisa preencher (NÃO estão no repositório)

`.env` (da API) e `segredos.h` (do firmware) são **gitignorados** de propósito — quem clona precisa recriá-los. O `setup.ps1` cria os dois a partir dos moldes; depois você preenche.

### 1) `api/.env`
| Variável | O que colocar | Onde pegar |
|---|---|---|
| `SUPABASE_URL` | `https://ljkfuwvkmczpmjupxnxw.supabase.co` | ⚠️ é a **Project URL** (termina em `.supabase.co`), **não** o link do dashboard |
| `SUPABASE_SECRET_KEY` | a chave **secret / service_role** | Supabase → Project Settings → **API Keys** → `service_role` (secret). Fica **só aqui**, nunca no firmware |
| `LLM_API_KEY` | chave do Google Gemini | grátis em https://aistudio.google.com/apikey |
| `LLM_MODEL` | `gemini-flash-lite-latest` | já vem preenchido |
| `SOMPO_API_KEY` | **deixe vazio** (auth desligada p/ demo) | — |
| `CORS_ORIGINS` | **deixe vazio** | — |

### 2) `firmware/src/segredos.h`
| Define | Valor |
|---|---|
| `WIFI_SSID_CFG` | nome do WiFi. **Na FIAP use o hotspot do celular** (o WiFi da facul costuma bloquear) |
| `WIFI_PASSWORD_CFG` | senha do WiFi/hotspot |
| `SUPABASE_URL_CFG` | `https://ljkfuwvkmczpmjupxnxw.supabase.co` |
| `SUPABASE_CHAVE_CFG` | `sb_publishable_fFTozL0gCyE_EKHzaa4smg_SMG1Dw8f` |

> A chave do firmware é a **publishable** (`sb_publishable_...`), que é pública de propósito — o RLS do Supabase só deixa ela fazer INSERT. **Nunca** coloque a secret/service_role no firmware.

---

## ⚙️ Setup no notebook novo (uma vez)

```powershell
# 1. clonar
git clone https://github.com/terrafelipe/sompo-sprint3.git
cd sompo-sprint3

# 2. setup em um comando (cria venv, instala deps, cria .env e segredos.h dos moldes)
.\setup.ps1
```

Depois do `setup.ps1`, **abra e preencha** os dois arquivos com as chaves da tabela acima:
- `api/.env`
- `firmware/src/segredos.h`

### Pré-requisitos que precisam estar instalados no notebook
- **Python 3** (`python --version`)
- **PlatformIO** (para o ESP32). Se `pio` não for reconhecido, o executável costuma ficar em:
  `C:\Users\<SEU_USUARIO>\.platformio\penv\Scripts\pio.exe`
  → ou instale a extensão **PlatformIO IDE** no VS Code e use o terminal dela.
- **Driver USB do ESP32**: CP2102 ou CH340 (senão o Windows não cria a porta COM).
- **Cabo USB de dados** (não serve cabo só de carga).

---

## ✅ Testar se a API está de pé (sem ESP32)

```powershell
cd api
.\venv\Scripts\Activate.ps1
pytest            # deve dar 18 passed
python app.py     # sobe a API em http://localhost:5000
```

Abra `http://localhost:5000/` no navegador → clique **📄 Baixar Word** → deve baixar um `.docx` com o relatório de risco.

Testar a conexão com o Supabase isoladamente:
```powershell
cd api
.\venv\Scripts\Activate.ps1
python scripts\testar_supabase.py   # as 3 tabelas devem responder 200 (não 404)
```

---

## 🔌 ESP32 físico — a parte da apresentação

Ideia: **grava uma vez, o ESP32 roda sozinho** e fica mandando eventos pro Supabase.

```powershell
cd firmware
pio run -t upload        # compila E grava no ESP32 (conecte o cabo antes)
pio device monitor       # (opcional) ver os logs do ESP32; sai com Ctrl+C
```

- `pio run -t upload` = compila o código e grava na placa numa tacada só.
- `pio device monitor` = só pra **ver** o que o ESP32 está imprimindo (WiFi conectado, POST 201, etc). É opcional — depois de gravado o ESP32 funciona sem o monitor.
- Se der conflito de porta COM: feche o `pio device monitor` antes de dar `upload` (os dois disputam a mesma porta).

Enquanto ele roda, os eventos aparecem no Supabase e o `/relatorio/risco.docx` já reflete os dados.

---

## 🆘 Troubleshooting rápido

| Sintoma | Causa / solução |
|---|---|
| Supabase **404** em tudo | `SUPABASE_URL` está errada. Use a Project URL `https://....supabase.co`, não o link do dashboard |
| **401/403** no Supabase | chave errada ou RLS. API usa a **secret**; ESP32 usa a **publishable** |
| `segredos.h: No such file` ao compilar | não rodou `setup.ps1` ou não criou o `firmware/src/segredos.h` |
| `pio` não é reconhecido | PlatformIO fora do PATH → use o caminho completo `...\.platformio\penv\Scripts\pio.exe` ou o terminal PIO do VS Code |
| `No module named pytest` | você não ativou o venv **de dentro de `api/`** (`cd api; .\venv\Scripts\Activate.ps1`) |
| ESP32 erro TLS **-80** / connection refused | é instabilidade do **Wokwi** (simulador), não do seu código. No físico com hotspot é estável |
| Sem porta COM | falta driver CP2102/CH340 ou o cabo é só de carga |
| Horário do Supabase "errado" | o banco guarda em UTC de propósito; o relatório Word já converte pra **Brasília (UTC-3)** |

---

## 📌 Regras de segurança (manter sempre)
- **Nunca** commitar/pushar `.env` nem `segredos.h` (já estão no `.gitignore`).
- A **secret / service_role** fica só em `api/.env`. No firmware/ESP32 vai só a **publishable**.
- Guia completo em `api/COMO_TESTAR.md` (passo a passo detalhado) e `api/SEGURANCA.md`.
