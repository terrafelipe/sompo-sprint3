# Como testar tudo, do zero

Duas coisas para testar: a **API (Python/Flask)** e o **firmware do ESP32** na **placa física**.
O roteiro vai do mais simples (sem hardware, sem internet) ao completo. Comandos em **PowerShell**
(Windows).

> 🎯 **Só quer a placa física funcionando (ex.: apresentação)?** Vá direto ao **passo 4** (gravar o
> sketch pela Arduino IDE). Os passos 1–3 validam a API, e o 8 é complementar.

> ⚠️ **O firmware ainda não fala com a API.** O projeto migrou do simulador para a placa física,
> com outro conjunto de sensores, e o sketch está em **bring-up incremental** (um sensor por vez).
> O envio de telemetria ao Supabase será portado depois que todos os sensores forem validados no
> hardware. Por isso os passos 5 e 7 dependem do dado que já está no banco, não de dado novo
> chegando ao vivo.

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
- **Arduino IDE** com o suporte a ESP32 instalado (Boards Manager → *esp32 by Espressif*) — para o
  firmware. **Não** usamos mais PlatformIO.
- Acesso a um projeto no **Supabase** (para os passos 3 em diante). Sem ele, dá para
  fazer o passo 1 (testes offline) mesmo assim.
- **Só para o ESP32 físico** (passo 4): a **placa ESP32 DevKit V1**, um **cabo USB de dados**
  (não serve cabo só de carga) e o **driver USB-serial** da placa (**CP2102** ou **CH340**).
  Sem o driver o Windows não cria a porta COM e o upload não acha a placa.

**Atalho (recomendado):** rode o script de setup na **raiz** do projeto — ele cria o venv, instala
as dependências e gera o `.env` e o `segredos.h` a partir dos exemplos (não sobrescreve se já
existirem), e no fim lista só o que falta você preencher:
```powershell
cd "C:\Users\USUARIO\Downloads\sompo-sprint3"
.\setup.ps1
```
> Se o PowerShell bloquear o script: `Set-ExecutionPolicy -Scope Process RemoteSigned` e rode de novo.

**Ou manualmente (uma vez, faça sempre que clonar o repo do zero):**
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

**Esperado:** `18 passed`. Cobre `scores.py`, as rotas e os 3 cenários do relatório de risco
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

**Painel visual (recomendado):** abra **`http://localhost:5000/`** no navegador — mostra os scores,
telemetria, eventos e o relatório de risco montados. O botão **📄 Exportar Word** gera o relatório de
risco como documento `.docx` (abre no Word/Google Docs), com os horários já em **Brasília**.

> 🔐 **Login opcional:** com `PAINEL_SENHA` definida no `.env`, o painel pede usuário/senha em
> `/login` (vazia = aberto, modo demo). Para publicar o painel na internet (Docker + Render),
> veja [`DEPLOY.md`](DEPLOY.md).

Para parar a API: `Ctrl+C` no terminal dela.

---

## 4. Firmware na placa física (Arduino IDE) — bring-up dos sensores

O firmware é um **sketch da Arduino IDE**, gravado direto no ESP32. Não há mais simulador,
PlatformIO nem `diagram.json`.

**1. Abrir o sketch**
```
firmware\sompo_hardware_final\sompo_hardware_final.ino
```
(A pasta tem o mesmo nome do `.ino` — é o que a Arduino IDE exige.)

**2. Configurar a IDE**
- **Ferramentas → Placa → ESP32 Arduino → ESP32 Dev Module**
- **Ferramentas → Porta →** a COM da placa (precisa do driver **CP2102/CH340**)
- **Monitor Serial → 115200 baud**

**3. Instalar as bibliotecas** (Ferramentas → Gerenciar Bibliotecas) — as versões testadas:

| Biblioteca | Versão | Para |
|---|---|---|
| Adafruit MPU6050 | 2.2.9 | MPU-6050 |
| Adafruit BusIO | 1.17.4 | dependência |
| Adafruit Unified Sensor | 1.1.15 | dependência |
| Adafruit AHTX0 | 2.0.6 | AHT10 (a mesma lib serve para o AHT20) |
| TinyGPSPlus (Mikal Hart) | 1.0.3 | GPS — **não** a "TinyGPSPlus-ESP32" |
| MFRC522 (miguelbalboa) | 1.4.12 | RC522 |
| **MAX6675 (RobTillaart)** | 0.3.4 | termopar — API **diferente** da Adafruit |

> ⚠️ **MAX6675:** a lib do RobTillaart usa `MAX6675(cs, miso, clock)`, exige `begin()` e a leitura é
> `read()` (`STATUS_OK == 0`) seguida de `getCelsius()`. Trocar pela `<max6675.h>` da Adafruit
> quebra a compilação — o cabeçalho do `.ino` avisa isso.

**4. Ligar um sensor por vez (o ponto principal deste passo)**

No topo do `.ino` há uma flag por sensor:
```cpp
#define USAR_MPU          1   // PASSO 1 - em teste agora
#define USAR_AHT          0   // PASSO 2
#define USAR_BUZZER       0   // PASSO 3
#define USAR_RFID         0
...
#define DIAG_I2C          1   // scanner I2C no setup
```
Com a flag em `0`, o `#include`, o objeto, a init, a chamada no `loop()` e a função `lerX()` daquele
sensor **não entram no binário** e nenhum pino dele é tocado. Monte o sensor na protoboard, vire
**só a flag dele** para `1`, grave e confira o Serial. Deu certo → próximo. Ordem:
`MPU → AHT → BUZZER → RFID/TERMOPAR/CHAMA/REED/POT`.

**5. Gravar e conferir**

Botão **→ (Upload)** e depois **Monitor Serial (115200)**. Com só o MPU ligado, o esperado é:
```
=== Sistema Sompo - Inicializando sensores ===
Scanner I2C: procurando dispositivos...
  I2C: dispositivo encontrado em 0x68
MPU-6050 OK - calibrando repouso, nao mexa na placa...
MPU-6050 baseline de repouso: 9.81 m/s2 (limiar de vibracao: 2.00)
=== Setup concluido ===
Acel (m/s2): X=... Y=... Z=...
|a|=9.81 m/s2 (desvio 0.03, limiar 2.00)
```
Nenhuma linha de AHT, GPS, RFID, termopar, capô, chama ou potenciômetro deve aparecer — se aparecer,
alguma flag ficou em `1` sem querer.

> 🔌 **Fiação:** o mapa de pinos completo está no **cabeçalho do próprio `.ino`**. Os três erros que
> mais custam tempo: **AD0 do MPU-6050 tem que ir no GND** (senão o endereço I2C oscila e a leitura
> falha de forma intermitente); **RC522 é 3.3V** (5V queima); e **GPS é cruzado** (TX→16, RX→17).
> MPU+AHT dividindo o I2C e RC522+MAX6675 dividindo o SPI é **de propósito**, não é erro.

> 📡 **Wi-Fi / Supabase:** ainda não estão no sketch de hardware. Quando forem portados, copie
> `firmware\sompo_hardware_final\segredos.exemplo.h` para `segredos.h` **na mesma pasta** (a Arduino
> IDE compila todos os arquivos da pasta do sketch) e preencha o hotspot do celular em **2.4 GHz**
> (o ESP32 não enxerga 5 GHz) mais a **publishable key** do Supabase — nunca a service_role.

---

## 5. Ver o dado ponta a ponta

- **Painel do Supabase** → Table Editor → `telemetria`: as linhas já gravadas pelo firmware
  anterior. (Dado **novo** só volta a entrar quando o envio Wi-Fi for portado para o sketch de
  hardware — ver o aviso no topo deste documento.)
- Com a API no ar, os endpoints devolvem esse dado:
  ```powershell
  curl.exe "http://localhost:5000/telemetria?limite=5"
  curl.exe "http://localhost:5000/relatorio/bruto?dias=7"
  ```

---

## 6. Disparar os cenários na bancada (placa física)

Estímulos para testar cada sensor conforme ele é ligado pela flag `USAR_<SENSOR>`. O resultado
aparece no **Monitor Serial** — os eventos ainda **não** sobem para a API (o envio Wi-Fi será
portado depois do bring-up).

| Cenário | Sensor | Como disparar | O que esperar no Serial |
|---|---|---|---|
| Vibração / adulteração | MPU-6050 | Bata na mesa ou mexa na placa | o `desvio` sobe e passa de `LIMIAR_VIBRACAO` |
| Ambiente | AHT10 | Sopre / encoste o dedo no sensor | temperatura e umidade mudam |
| Alarme sonoro | Buzzer | Autoteste no boot | bipe de 2500 Hz logo após o setup |
| Crachá / autorização | RC522 | Encoste a tag no leitor | `RFID detectado - UID: ...` |
| Escape quente | MAX6675 | Aqueça a ponta do termopar | a temperatura em °C sobe |
| Chama | KY-026 | Aproxime uma chama (ajuste o trimmer) | `!!! CHAMA DETECTADA !!!` + buzzer 2000 Hz |
| Capô aberto | Reed | Afaste o ímã do reed | `Capo: ABERTO` |
| Motor ligado/desligado | Potenciômetro | Gire o eixo | leitura 0–4095 e `DESLIGADO`/`ligado` |
| **Furto (regra combinada)** | Pot + MPU + buzzer | Pot **para baixo** (motor desligado) **e** sacuda a placa | `!!! ALERTA: vibracao detectada com motor desligado !!!` + buzzer 3000 Hz |

> 🎚️ **Limiares** ficam nos `#define` do topo do `.ino` (`LIMIAR_VIBRACAO`,
> `LIMIAR_POT_MOTOR_DESLIGADO`). A linha `|a|=... (desvio ..., limiar ...)` existe justamente para
> calibrar o primeiro na bancada: parado o desvio fica perto de 0; se nem sacudindo ele passar do
> limiar, baixe o valor. Nos módulos com comparador (KY-026 e reed) a sensibilidade é ajustada no
> **trimmer da própria placa**, e a polaridade HIGH/LOW pode precisar ser invertida no código.

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
curl.exe "http://localhost:5000/relatorio/risco?dias=7"        # JSON
curl.exe "http://localhost:5000/relatorio/risco.docx?dias=7" -o relatorio.docx   # documento Word
```
O `.docx` é o mesmo relatório em formato Word (também no botão **📄 Baixar Word** do painel), com os
horários em Brasília — mais fácil de ler/apresentar que o JSON.

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
- **testar_supabase 404:** a `SUPABASE_URL` está errada — use a **Project URL** (`https://<ref>.supabase.co`)
  de Settings → API, **não** o link do painel (`.../dashboard/project/...`).
- **testar_supabase 401/403:** problema de chave ou RLS — ver `SEGURANCA.md`.
- **Upload não acha a placa / erro de porta:** cabo USB de **dados** (não só carga), driver
  **CP2102/CH340** instalado, e feche o **Monitor Serial** antes de gravar (uma porta COM por vez).
  Se insistir, segure o botão **BOOT** da placa durante o "Connecting...".
- **Monitor Serial só com caracteres estranhos:** o baud está errado — tem que ser **115200**.
- **`ERRO: MPU-6050 nao encontrado` / scanner I2C não acha nada:** é fiação, não código. Confira
  **AD0 no GND**, 3.3V/GND chegando na trilha da protoboard e **SDA=21 / SCL=22**. Barramento vazio =
  alimentação ou cabo; `0x68` aparecendo mas `begin()` falhando = biblioteca/endereço.
- **`ERRO: AHT10 nao encontrado`:** o scanner tem que mostrar `0x38`. O AHT10 divide o I2C com o MPU,
  então os dois endereços (`0x38` e `0x68`) devem aparecer juntos.
- **Termopar com leitura absurda:** inverta as duas garras do termopar no bloco verde (polaridade)
  e confira o CS em **GPIO 15** (o RC522 usa o CS **5**; SCK/MISO são compartilhados de propósito).
- **Sensor "sempre acionado" (KY-026 ou reed):** são módulos com comparador — ajuste o **trimmer**
  da placa; se continuar invertido, troque o `== LOW` por `== HIGH` (ou vice-versa) na função `lerX()`.
- **Erro de compilação no MAX6675** (`no matching function`, `getCelsius não existe`): está instalada
  a lib da **Adafruit** em vez da do **RobTillaart** 0.3.4. Ver a tabela do passo 4.
- **ESP32 não conecta no Wi-Fi** (quando a rede for portada): o hotspot precisa estar em **2.4 GHz**
  (não 5 GHz), com SSID/senha simples; deixe os dados móveis ligados.
- **quer o relatório com IA de verdade:** preencher `LLM_API_KEY` no `.env` (sem ela a origem fica
  `prompt_apenas`, que é o esperado agora).
