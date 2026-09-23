# Contexto do Projeto — SOMPO (Sprint 3)

> Atualizado em 17/09/2026. A revisão abaixo descreve o modelo atual de frota e
> prevalece sobre observações históricas de bancada.

## Frota, RFID e painel atual

- Cada cliente possui fazendas; cada fazenda possui máquinas. O backend deriva o cliente  
  proprietário da fazenda escolhida, sem confiar em um cliente enviado pelo formulário.  
  `id_equipamento` é o ID cadastral; `dispositivo_id` identifica o ESP32 exclusivo vinculado.
  Fabricação e última manutenção são datas; valor segurado é decimal em reais, opcional.
- Operador não é usuário de login. Nome e UID do crachá são necessários; matrícula é
  opcional: **Código interno do funcionário, se houver.** O UID é o identificador RFID
  do crachá, normalizado em hexadecimal. Vínculos autorizam operadores por equipamento.
- Cada ESP32 recebe token individual, mostrado uma vez no painel e configurado em
  `DISPOSITIVO_TOKEN_CFG`; o banco guarda o hash. A configuração e as autorizações
  sincronizam a cada 60 segundos; o cache LittleFS comporta até **32 operadores**.
  Revogações dependem da próxima sincronização: offline vale o último cache confirmado.
- Eventos/transições usam fila durável de **512 KiB**, limitada pela flash disponível.
  Ao atingir o limite ou falhar a persistência, novos registros não são confirmados.
  Telemetria usa **um slot em RAM**, sobrescrito pela amostra mais recente; não oferece
  histórico completo offline e se perde no reinício. Não existe garantia de retenção infinita.
- Sessões registram presença associada ao crachá, não prova de condução contínua ou culpa.
  Dados legados sem operador continuam consultáveis como não identificados.
- Migração existente: `firmware/sql/frota.sql`, aditiva e idempotente. Não há migração nova
  nesta correção. Não executar `preparar_supabase.sql` em banco existente. A finalização
  `concluir_migracao_dispositivos()` só ocorre após provisionar e sincronizar todas as placas;
  ver [Ativar frota](docs/ATIVAR_FROTA.md). A compatibilidade legada não equivale a token universal.
- Máquinas cadastradas são editáveis pelo botão "Editar" do card (ou pelo modal de
  detalhes), reaproveitando o mesmo formulário do cadastro em modo edição via
  `PATCH /equipamentos/<id>`. Fazenda e ESP32 já vinculado ficam travados na UI, espelhando
  as recusas 409 do backend (`transferencia_nao_permitida`, `remanejamento_nao_permitido`).
- Os `<select>` do painel usam `appearance: base-select` (Chrome/Edge 135+): a lista de
  opções segue o design do painel; navegadores sem suporte mostram a lista nativa.
- Máquinas, Operadores, Histórico, Fazendas, Clientes e Usuários carregam sem máquina.
  Painel da máquina, Risco, Telemetria e Alertas mantêm a aba e solicitam seleção; o atalho
  "Selecionar máquina" abre a lista do seletor do header (`showPicker()`) ou, sem máquinas
  na fazenda, leva para a aba Máquinas.
  O refresh de cinco segundos preserva aba/seleção; mudanças de fazenda limpam dados e
  invalidam respostas pendentes. Menus restritos do gestor continuam ocultos após resize.
- Exportar Word permanece visível, desabilitado com explicação sem máquina. Com seleção,
  usa `/relatorio/risco.docx?equipamento=<id>&dias=7`. O atalho da fazenda seleciona uma
  máquina dessa fazenda; fazendas vazias mostram a solicitação de seleção.
- Carregando, vazio e indisponível são estados distintos. Consultas com falha oferecem
  nova tentativa e não impedem o acesso às outras abas. Histórico vazio não é erro de banco.
- Deploy: painel e API Flask usam a sessão de login. Na Lambda, `PAINEL_SENHA` definida,
  `SECRET_KEY` persistente e **`SOMPO_API_KEY` vazia**. Não colocar chave de API no frontend.
- Testes: `api/tests/test_painel.py` executa fluxos em navegador desktop (1280 px) e mobile
  (390 px), com HTTP simulado. `test_frota.py` valida cadastro completo, operador sem
  matrícula, histórico vazio/502 e conteúdo Word da máquina selecionada. Escritas são
  feitas apenas em fixtures, nunca no Supabase publicado. Instruções em
  [Como testar](docs/COMO_TESTAR.md); o navegador requer `api/requirements-test.txt`.

> Documento de contexto completo do projeto. Reúne, em um só lugar, o propósito, a
> arquitetura, cada camada (firmware, banco, API, painel), o contrato de dados,
> segurança, deploy, testes e os "pega-ratão" da bancada. Serve tanto para retomar o
> desenvolvimento quanto para apresentar o trabalho.

---

## 1. Visão geral

**SOMPO — Monitor de Furto e Incêndio para Máquinas Agrícolas.**

Projeto acadêmico da **FIAP** (Tecnologia em Inteligência Artificial) para a
**Sompo Seguros**, entregue na **Sprint 3**. É um sistema **IoT embarcado** numa máquina
agrícola (trator/escavadeira) que:

1. **Detecta furto/roubo e incêndio** por meio de sensores num ESP32;
2. **Envia telemetria e eventos** para a nuvem (Supabase) via Wi-Fi;
3. **Calcula scores de risco determinísticos** e gera **relatórios** — inclusive um
   relatório **interpretado por IA** — para apoiar a seguradora na análise de risco e sinistro.

### Escopo (e o que ficou de fora, de propósito)

Apenas **furto/roubo** e **incêndio** — os dois riscos que ainda **não têm cobertura
tecnológica** em máquinas agrícolas. Colisão, medição de distância e previsão do tempo
estão **fora de escopo**: máquinas novas já saem de fábrica com esses sensores.

- **Repositório:** `github.com/terrafelipe/sompo-sprint3` (branch principal: `main`)
- **Produção (painel):** **AWS Lambda** (Learner Lab) atrás do **Cloudflare Pages** —
  https://sompo-painel.pages.dev. Deploy manual por script (§9).
- **Banco:** projeto **Supabase** `ljkfuwvkmczpmjupxnxw.supabase.co`.

---

## 2. Arquitetura

```
  Sensores físicos
        │
        ▼
   ESP32 (C++/Arduino)  ──Wi-Fi──►  Supabase (PostgREST + Postgres)
                                          │
                                          ▼
                                   API em Flask (Python)   ◄── login/painel
                                          │
                                          ▼
                                   LLM (Google Gemini)
                                          │
                                          ▼
                   Relatórios:  bruto (factual)  +  risco (interpretado por IA)
```

Pontos-chave da arquitetura:

- **O ESP32 fala DIRETO com o Supabase** (PostgREST), não passa pela API. Logo,
  **publicar/atualizar o painel não mexe no firmware**, e vice-versa.
- **A API Flask lê o Supabase** (com a chave *secret*/service_role), calcula os scores e
  serve o painel + os endpoints JSON + os relatórios.
- **Painel e API são o mesmo app Flask**, na mesma origem. A rota `/` serve o dashboard
  (`static/index.html`), que busca os dados por caminhos **relativos** (`/telemetria`,
  `/scores`, ...). Nada de `localhost` hardcoded, nada para reconfigurar ao subir.
- **Os scores são calculados de forma determinística ANTES da IA.** O LLM só **redige** a
  análise; **nunca** recalcula ou contesta os números.

---

## 3. Estrutura de diretórios

```
sompo-sprint3/
├── README.md                  # Visão geral do projeto
├── contexto.md                # (este arquivo)
├── render.yaml                # Blueprint do Render (plano B de deploy; fica na RAIZ)
├── setup.ps1                  # Setup one-shot (venv + deps + .env + segredos.h)
├── .gitignore                 # Rede de segurança de segredos do monorepo
├── nginx/                     # (vazio — resquício de arquitetura antiga)
│
├── infra/                     # Deploy na AWS Lambda + proxy no Cloudflare Pages
│   ├── deploy-aws.ps1         # Script idempotente (Windows ou AWS CloudShell)
│   ├── .env.aws(.example)     # Envs da Lambda (gitignorado) / molde versionado
│   └── pages/_worker.js       # Proxy da URL limpa (sompo-painel.pages.dev)
│
├── api/                       # API REST em Flask (Python) + painel
│   ├── app.py                 # Rotas, login, API key, perfis (role-based)
│   ├── config.py              # Env vars (.env), headers do Supabase
│   ├── supabase_client.py     # Acesso ao PostgREST (consultas + inserts)
│   ├── scores.py              # Cálculo DETERMINÍSTICO de risco (puro, sem I/O)
│   ├── relatorios.py          # Monta relatório bruto + risco; prompt; fallback
│   ├── llm.py                 # Camada de IA (Google Gemini) + cache + origem
│   ├── documento.py           # Gera o relatório de risco em .docx (python-docx)
│   ├── requirements.txt       # Flask, requests, python-docx, waitress, pytest...
│   ├── Dockerfile             # Imagem de produção (python:3.12-slim + waitress + Lambda Web Adapter)
│   ├── .env / .env.example    # Segredos (gitignorado) / molde versionado
│   ├── static/index.html      # Painel/dashboard (SPA, Tailwind CDN, JS vanilla)
│   ├── templates/login.html   # Página de login do painel
│   └── tests/                 # 56 testes pytest (mockados, sem rede)
│
├── firmware/                  # Código do ESP32 (Arduino IDE)
│   ├── arduino-cli.yaml       # Config do arduino-cli portátil do repo
│   ├── tools/                 # instalar-arduino-cli.ps1 (+ o CLI baixado)
│   ├── sompo_hardware_final/
│   │   ├── sompo_hardware_final.ino   # Sketch principal (~1070 linhas)
│   │   ├── segredos.h / .exemplo.h    # Wi-Fi + chave publishable (gitignorado)
│   │   └── .vscode/                   # Config da extensão Arduino (É entregável)
│   └── sql/                    # Scripts do Supabase (rodar no SQL Editor)
│       ├── preparar_supabase.sql      # Tabelas + view + índices + RLS (1º)
│       ├── dados_exemplo.sql          # Dados de negócio de demonstração
│       ├── fazenda.sql                # Tabela fazenda
│       └── usuarios.sql               # Tabela usuario + logins de teste
│
└── docs/
    ├── COMO_TESTAR.md         # Roteiro completo de teste (API + placa)
    ├── DEPLOY.md              # Deploy na AWS Lambda + Cloudflare (Render = plano B)
    └── SEGURANCA.md           # Endurecimento aplicado + passos manuais
```

---

## 4. Firmware (ESP32)

**Arquivo:** `firmware/sompo_hardware_final/sompo_hardware_final.ino`
**Placa:** ESP32 DevKit V1 · **FQBN** `esp32:esp32:esp32` · Monitor Serial **115200**.

### 4.1 Filosofia do código

- **Bring-up incremental por flags.** No topo do `.ino` há uma flag `USAR_<SENSOR>` por
  sensor. Cada sensor é um **namespace** com a mesma interface
  (`iniciar/ler/imprimir/eventos/telemetria`). Com a flag em `0`, o namespace vira um
  conjunto de **no-ops vazios** — o compilador elimina tudo, nenhum pino é tocado e o
  campo é **omitido do JSON** (coluna fica `NULL`; mandar `0` inventaria uma medição).
  Ordem de ligação sugerida: `MPU → AHT → BUZZER → RFID/TERMOPAR/CHAMA/REED/POT → WIFI`.
- **Agendamento por `millis()`, nunca `delay()`** no `loop()` (sensores rápidos, lentos,
  Serial, saúde do MPU e telemetria têm intervalos próprios).
- **Rede numa tarefa própria (núcleo 0).** O `loop()` (núcleo 1) só **enfileira**, nunca
  fala com a rede. Duas filas com semânticas diferentes (ver 4.5).

### 4.2 Estado atual da bancada (quirks reais)

Todas as flags `USAR_*` estão **ligadas** no arquivo, **inclusive `USAR_WIFI 1`** (envio ao
Supabase em produção). Detalhes de montagem que fugiram do "ideal":

- **Sensor de chama KY-026:** o **D0 (digital) queimou** numa inversão de VCC/GND. Passou a
  ser lido pelo **A0 (analógico) no GPIO35** (ADC1, aguenta o Wi-Fi; o D0 estava no
  GPIO25/ADC2, que morre com o rádio ligado). Limiar por software `LIMIAR_CHAMA` (raw cai
  perto de 0 com chama) — **calibrar** por olho/ouvido no Serial.
- **Termopar MAX6675:** saiu do SPI compartilhado com o RC522 (o módulo não liberava o MISO
  e travava o cartão). Ganhou **pinos próprios (bit-bang): SO=13, SCK=4, CS=15**. Lib do
  **RobTillaart** (API diferente da Adafruit: construtor `(cs, miso, clock)`, exige
  `begin()`, `read()` com `STATUS_OK==0` + `getCelsius()`). Se ler 0 °C fixo → trocar SO↔SCK.
- **Potenciômetro** (simula ignição/motor) montado no **GPIO34** (ADC1).
- **Crachá RFID (RC522)** identifica operadores autorizados por máquina (UID de 4, 7 ou
  10 bytes). O primeiro toque inicia a sessão; o mesmo crachá encerra; outro autorizado
  troca o operador. Reinício interrompe a sessão e exige novo crachá. Não há UID fixo de
  autorização no código. **Fogo sempre soa**, independentemente da sessão.
- **Buzzer (GPIO26):** alarme **contínuo** enquanto a ameaça está presente (não bipe único).
  Tons em `BUZZER_FREQ_CHAMA` (2000 Hz) / `BUZZER_FREQ_FURTO` (3000 Hz). Bipes curtos de
  feedback distintos para crachá autorizado / negado / ímã do reed.
- **Driver USB da placa: CP2102** (Silicon Labs). Sem o driver CP210x o Windows não cria a COM.

> **Observação:** o README traz uma nota histórica dizendo `USAR_CHAMA 0`/`USAR_POT 0`. O
> `.ino` **atual** está com tudo ligado (`1`) — a fonte da verdade é sempre o topo do sketch.

### 4.3 Mapa de pinos (fonte da verdade: cabeçalho do `.ino`)

| Componente | Barramento | Pinos | Notas |
|---|---|---|---|
| **MPU-6050** (acelerômetro/vibração) | I2C | SDA=21 SCL=22 | AD0 no GND (endereço 0x68) |
| **AHT10** (temp/umidade ambiente) | I2C | SDA=21 SCL=22 | 0x38 — divide o barramento com o MPU |
| **RC522** (crachá RFID) | SPI | SCK=18 MISO=19 MOSI=23 SS=5 RST=27 | **3.3V** (5V queima) |
| **MAX6675** (termopar tipo K, escape) | bit-bang | SO=13 SCK=4 CS=15 | **fora** do SPI do RC522 |
| **Reed capô / tanque** | digital | 32 / 33 | HIGH = aberto |
| **KY-026** (chama) | analógico | A0=35 | D0 queimou; A0 = ADC1 |
| **Potenciômetro** (ignição) | analógico | 34 | ADC1 |
| **Buzzer** | digital | 26 | tone() |
| **GPS NEO-6M** | UART2 | TX→16 RX→17 (cruzado) | sem fix indoor |

### 4.4 Lógica de risco (no firmware, coluna `nivel_risco`)

`Risco::calcular()` deriva uma **severidade 0–5** e um nível textual:

- **Incêndio (sempre monitorado, ligado ou não):** chama → sev 5; escape ≥ 550 °C
  (`TEMP_ESCAPE_CRITICO`) → sev 4; escape ≥ 450 °C (`TEMP_ESCAPE_ATENCAO`) → sev 2.
- **Furto (só com o sistema ARMADO — sem crachá):**
  - Parada + vibração confirmada → sev 4; capô aberto → sev 2; tanque aberto → sev 3.
  - Ligada sem crachá → sev 3 (roubo em andamento).
- Nível: `sev ≥ 4` → **CRÍTICO**; `sev ≥ 2` → **ATENÇÃO**; senão **SEGURO**.

**Tipos de evento emitidos** (têm de existir em `api/scores.py`):
`furto_adulteracao` (vibração com a máquina desligada, via MPU — substitui o antigo
`furto_movimento` do HC-SR04), `furto_capo`, `furto_tanque`, `operador_nao_autorizado`
(partida sem crachá), `sensor_falha` (MPU sumiu do barramento = tentativa de burla),
`chama_detectada`, `escape_critico`, `escape_atencao`.

### 4.5 Rede e envio ao Supabase

- Ativado por `USAR_WIFI 1`; exige `segredos.h` preenchido (Wi-Fi 2.4 GHz + Project URL +
  **publishable key** e token individual `DISPOSITIVO_TOKEN_CFG`).
- **Duas filas** consumidas pela tarefa do núcleo 0:
  - **Eventos e transições:** fila durável LittleFS de até **512 KiB**. Não é armazenamento
    ilimitado: cheia ou indisponível, o firmware não confirma novos registros/transições.
    Falhas de envio mantêm registros pendentes; é preciso recuperar a conectividade.
  - **Telemetria:** caixa de **1 slot sobrescrito** (a amostra de agora vale mais que a
    antiga). Enviada a cada `INTERVALO_TELEMETRIA_MS` (10 s).
- **TLS validado sempre** com o CA raiz embutido (**Google Trust Services — GTS Root R4**,
  válido até 2036). Não existe mais `setInsecure()`/`VALIDAR_CERTIFICADO`.
- **NTP** (`pool.ntp.org`, UTC-3) carimba `criado_em`; sem sync, o default `now()` do banco
  assume.
- `Prefer: return=minimal` no POST (não ecoa o registro — poupa RAM).
- **Diagnóstico:** `DIAG_TELEMETRIA 1` imprime o JSON no Serial sem precisar de rede;
  `DIAG_I2C 1` roda um scanner I2C no setup.

### 4.6 Bibliotecas Arduino

Adafruit MPU6050 2.2.9 (+ Unified Sensor + BusIO), Adafruit AHTX0 2.0.6 (AHT10/AHT20),
TinyGPSPlus 1.0.3 (Mikal Hart), MFRC522 1.4.12, **MAX6675 0.3.4 do RobTillaart**.

---

## 5. Banco de dados (Supabase / PostgreSQL + PostgREST)

Scripts em `firmware/sql/`, rodados no **SQL Editor** do Supabase. Ordem:
`preparar_supabase.sql` → `dados_exemplo.sql` → `fazenda.sql` → `usuarios.sql`. Todos
**idempotentes**.

### 5.1 Tabelas do sensor (escritas pelo ESP32, lidas pela API)

**`telemetria`** — amostra periódica:
`id`, `dispositivo_id`, `criado_em`, `temp_escape`, `temp_ambiente`, `umidade_ar`,
`chama_detectada`, `vibracao` (em g), `motor_ligado`, `capo_aberto`, `tanque_aberto`,
`operador_autorizado`, `nivel_risco`.

**`eventos`** — gravado só quando dispara (trilha de evidência, imutável):
`id`, `dispositivo_id`, `criado_em`, `tipo`, `severidade`, `temp_escape`, `detalhes` (jsonb).

**View `resumo_diario`** (`security_invoker = true`) — agrega telemetria por
`dispositivo_id` + dia (America/Sao_Paulo): amostras, médias/máximos de temperatura e
vibração, `houve_chama`, `houve_capo_aberto`. Ninguém escreve; a API lê em `/resumo` e no
relatório bruto.

**Migração histórica:** o HC-SR04 saiu do projeto → `distancia_cm`/`em_movimento` foram
**removidos** e entraram `temp_ambiente`, `capo_aberto`, `tanque_aberto`,
`operador_autorizado`.

### 5.2 Tabelas de negócio (modelo do seguro)

`cliente` ← `fazenda` ← `equipamentos` ← `riscos` (↔ `telemetria`) ↔ `sinistros`; e `usuario`
(logins do painel: `usuario`, `senha` em texto plano, `role`, `fk_fazenda_id_fazenda`).

`dados_exemplo.sql` contém dados de demonstração. O painel atual mostra a frota por fazenda,
operadores, histórico, telemetria, eventos, scores e cadastros conforme o perfil.

### 5.3 Segurança do banco (RLS)

- **RLS ligado** em `telemetria`, `eventos`, `fazenda`, `usuario` (e nas tabelas de negócio,
  se existirem).
- **Chave `anon`/publishable (a que vai no ESP32):** só tem policy de **INSERT** em
  telemetria/eventos. Sem policy de select/update/delete → **negado por padrão**. `UPDATE`/
  `DELETE` em `eventos` são **revogados** (a evidência não pode ser reescrita nem apagada).
- **Chave `secret`/service_role (só na API):** ignora RLS, lê/escreve tudo.
- Assim, a chave extraível da flash do ESP32 **não** vira chave de administrador.

---

## 6. API (Flask)

Arquivo central: `api/app.py`. Servida por **waitress** em produção; `python app.py` em dev.

### 6.1 Endpoints

| Rota | O que faz |
|---|---|
| `GET /` | Painel visual (dashboard) — pede login se `PAINEL_SENHA` definida |
| `GET /saude` | Health check (API + banco). Única rota liberada da API key |
| `GET /me` | Perfil do usuário logado (role + fazenda vinculada) |
| `GET /telemetria` | Últimas leituras (`?dispositivo=`, `?limite=`) |
| `GET /eventos` | Eventos do período (`?dias=`) |
| `GET /resumo` | Resumo diário (view `resumo_diario`) |
| `GET /scores` | Scores de risco determinísticos por eixo |
| `GET /relatorio/bruto` | Relatório factual |
| `GET /relatorio/risco` | Relatório interpretado por IA (fallback gracioso, sempre 200) |
| `GET /relatorio/risco.docx` | O mesmo relatório como documento Word para download |
| `GET/POST /clientes` | Lista/cadastra clientes — **só perfil Sompo** (403 p/ gestor) |
| `GET/POST /fazendas` | Lista/cadastra fazendas — **só perfil Sompo** |
| `GET/POST /usuarios` | Lista/cadastra logins do painel — **só perfil Sompo** |

Padrão de dispositivo: `SOMPO-ESP32` (tem de bater com o `DISPOSITIVO_ID` do firmware).

### 6.2 Perfis de acesso (role-based)

Dois perfis logam no mesmo sistema (demo acadêmica — senha em texto plano, sem hashing):

- **Sompo** (subscritor): vê o **portfólio inteiro**, cadastra fazendas/clientes/usuários e
  troca de fazenda por um seletor no topo.
- **Gestor de Fazenda**: vê **só** a telemetria/risco da própria fazenda; abas de cadastro
  ocultas. O **backend força** o filtro por dispositivo (`_dispositivo_para`): nem passando
  `?dispositivo=` na URL o gestor lê outra fazenda; as rotas de cadastro respondem **403**
  (`@somente_sompo`).

O perfil vem da tabela `usuario` (com a fazenda vinculada embutida via PostgREST). Sem
sessão (modo demo, `PAINEL_SENHA` vazia) o padrão é `sompo`, preservando o comportamento
aberto.

### 6.3 Camada de risco + IA (a regra de ouro do projeto)

1. **`scores.py`** (módulo **puro**, sem rede) calcula, a partir dos eventos:
   - Cada tipo mapeia um eixo (`EIXO_POR_TIPO`): `furto` ou `incendio`.
   - Severidade → pontos (`{1:5, 2:10, 3:20, 4:40, 5:70}`), somados por eixo, **saturados em
     100**.
   - Classificação: `≥67` ALTO, `≥34` MÉDIO, senão BAIXO.
   - Saída **determinística** (detalhamento ordenado por tipo).
2. **`relatorios.py`** monta o prompt com os **scores já calculados como FATO DADO** e manda
   para o LLM. O prompt proíbe explicitamente recalcular/contestar os números.
3. **`llm.py`** chama o **Google Gemini** (`gemini-flash-lite-latest`), decide a **origem**:
   - `prompt_apenas` — sem `LLM_API_KEY`: não chama ninguém, usa template.
   - `llm` — chave presente e Gemini respondeu JSON válido.
   - `fallback` — chave presente mas provedor falhou (timeout/429/JSON inválido) → template.
   - **Cache em memória por prompt** (TTL 5 min sucesso / 2 min erro) para não estourar o
     limite gratuito (429).
   - **Nunca lança** para a rota → o endpoint responde **sempre HTTP 200**.
   - Os **scores no relatório vêm SEMPRE do cálculo determinístico**, jamais do LLM.
4. **`documento.py`** transforma o relatório de risco em `.docx` (python-docx), com horários
   convertidos para **Brasília (UTC-3 fixo)**, tabela de eventos e cores por classificação.

---

## 7. Painel / Frontend

**Arquivo:** `api/static/index.html` (SPA de arquivo único, ~1090 linhas).

- **TailwindCSS via CDN** (`cdn.tailwindcss.com`) + ícones **Material Symbols**. JS
  **vanilla** (sem framework/build).
- Busca dados com `getJSON()` em caminhos **relativos**; **auto-refresh a cada 5 s**
  (`setInterval(carregarTudo, 5000)`).
- **Abas:** Visão Geral (scores, telemetria atual, feed de alertas, últimas leituras, gráfico
  de temperatura em SVG estilo *line chart*), Fazendas, Clientes, Usuários (as três últimas
  só para o perfil Sompo).
- **Alerta clicável** (modal de detalhe) e efeito *border beam* no card de risco (CSS puro,
  inspirado no 21st.dev).
- Botão **📄 Exportar Word** → baixa `/relatorio/risco.docx`.
- Seletor de fazendas no topo (perfil Sompo) que troca o `dispositivo` consultado.
- **Login:** `templates/login.html` (self-contained), com "manter conectado".

---

## 8. Segurança (resumo)

Princípio: **seguro por padrão, sem quebrar a demo** — tudo que afetaria a demo fica atrás de
uma flag/env desligada por padrão.

- **Segredos nunca no repositório:** `api/.env` e `firmware/.../segredos.h` são gitignorados;
  o repo traz só `.env.example` e `segredos.exemplo.h`. `.dockerignore` mantém o `.env` fora
  da imagem.
- **Login do painel** (opt-in por `PAINEL_SENHA`): cobre **todo o site**; página `/login` +
  sessão assinada (`SECRET_KEY`), timeout absoluto de `SESSAO_HORAS` (24). Comparações em
  tempo constante (`hmac.compare_digest`). Navegador → redirect; fetch/JSON → 401.
- **API key** (opt-in por `SOMPO_API_KEY`): definida → toda rota (menos `/saude`) exige
  header `X-API-Key`.
- **CORS restrito** por `CORS_ORIGINS` (vazio = nenhuma origem cross-origin).
- `FLASK_DEBUG=false` e `FLASK_HOST=127.0.0.1` por padrão. Erros internos só no log do
  servidor (não vazam schema do Supabase para o cliente).
- **TLS validado** no ESP32 (CA raiz embutido). **RLS** limita a chave do ESP32 a INSERT.
- Detalhes e passos manuais em `docs/SEGURANCA.md`.

---

## 9. Deploy (AWS Lambda + Cloudflare Pages)

- **Onde:** AWS Lambda (imagem Docker em ECR, `us-east-1`, role `LabRole`) no **AWS Academy
  Learner Lab**, exposta por **Function URL**; um proxy no **Cloudflare Pages** dá a URL limpa
  `https://sompo-painel.pages.dev`. Escala a zero (~US$ 0), cold start ~1–2 s.
- **Imagem:** o mesmo `api/Dockerfile`, com a extensão **Lambda Web Adapter** (repassa os
  eventos para o waitress na porta 8080; inerte fora da Lambda).
- **Deploy manual** (credenciais do lab são temporárias → sem CI): `pwsh infra/deploy-aws.ps1`
  no **AWS CloudShell** (já tem Docker) ou no Windows. Idempotente: cria/atualiza ECR, função,
  Function URL + 2 permissões, logs com retenção de 7 dias.
- **Variáveis** em `infra/.env.aws` (gitignorado): `SUPABASE_URL`, `SUPABASE_SECRET_KEY`,
  `LLM_API_KEY`, `LLM_MODEL`, `PAINEL_USUARIO`, `PAINEL_SENHA`, **`SECRET_KEY` fixa**,
  `SESSAO_HORAS`. O script injeta `PORT=8080`, `AWS_LWA_READINESS_CHECK_PATH=/login` e
  `COOKIE_SEGURO=true`.
- ⚠️ **`SOMPO_API_KEY` DEVE ficar VAZIA** (o script recusa rodar se não estiver). Se
  preenchida, o `before_request` passa a exigir `X-API-Key` em toda rota de dados, e o painel
  embutido (que usa a sessão de login, não o header) leva **401 → dashboard vazio**.
- A Lambda **segue no ar com o lab encerrado**; a conta **some no fim do curso**.
- **Plano B:** `render.yaml` (Render free, hiberna ~50 s). `docs/DEPLOY.md` tem o passo a passo
  de tudo. (A pasta `nginx/` está vazia — resquício de uma arquitetura EC2 antiga.)

---

## 10. Testes

`api/tests/` — **pytest**, **56 funções de teste**, todas mockadas (sem rede, sem `.env`,
sem hardware). Cobrem:

- `test_scores.py` — cálculo determinístico de risco.
- `test_auth.py`, `test_perfis.py` — login, API key, escopo por perfil (gestor não vê outra
  fazenda; cadastro dá 403).
- `test_relatorios.py`, `test_relatorio_risco_origens.py` — os 3 cenários de origem
  (llm/prompt_apenas/fallback).
- `test_documento.py` — geração do `.docx`.
- `test_telemetria.py`, `test_eventos.py`, `test_fazendas.py`, `test_usuarios.py`,
  `test_health.py` — rotas.
- **`test_contrato_firmware.py`** — lê o `.ino` e o `.sql` **como texto** e garante o
  **contrato**: uma chave nova no firmware sem coluna no SQL, ou um evento que não pontua no
  `scores.py`, **quebra o pytest**.

> Nota: `README.md` cita "46 testes" e `COMO_TESTAR.md` cita "32 passed" — números
> **históricos**. A contagem atual de funções `def test_` é **56**.

---

## 11. Como rodar

### Setup (uma vez por máquina)

```powershell
.\setup.ps1     # cria api\venv, instala deps, gera .env e segredos.h dos exemplos
```

Depois preencher: `api/.env` (`SUPABASE_URL`, `SUPABASE_SECRET_KEY`, e opcional
`LLM_API_KEY`) e `firmware/.../segredos.h` (Wi-Fi 2.4 GHz, Project URL, publishable key).

### API

```powershell
cd api
.\venv\Scripts\python.exe -m pytest      # testes offline
.\venv\Scripts\python.exe app.py         # sobe em http://localhost:5000
```

### Firmware

Compilar pelo **arduino-cli portátil do repo** (sem instalação global, sem PlatformIO):

```powershell
.\firmware\tools\instalar-arduino-cli.ps1   # 1ª vez: baixa o CLI + core ESP32
.\firmware\tools\arduino-cli.exe --config-file firmware\arduino-cli.yaml `
  compile --fqbn esp32:esp32:esp32 firmware\sompo_hardware_final
```

Ou pela **Arduino IDE / VS Code** (extensão *Arduino Community Edition*, já configurada em
`.vscode/`). Roteiro completo em `docs/COMO_TESTAR.md`.

---

## 12. Contrato de dados (não mudar de um lado só)

O elo firmware ↔ banco ↔ API é rígido e **verificado por teste**:

| Elemento | Fonte da verdade |
|---|---|
| **Colunas** de telemetria/eventos | `firmware/sql/preparar_supabase.sql` |
| **Tipos de evento** e seus eixos | `api/scores.py` (`EIXO_POR_TIPO`) |
| **`dispositivo_id`** | tem de ser `"SOMPO-ESP32"` (default das rotas em `api/app.py`) |
| Campos enviados pelo firmware | telemetria de cada namespace `::telemetria(Json&)` no `.ino` |

Campo cujo sensor está desligado é **omitido** do JSON (coluna NULL) — mandar `0`
estragaria as médias da view `resumo_diario`.

---

## 13. Credenciais de teste (demo — senha em texto plano)

| Usuário | Senha | Perfil | Enxerga |
|---|---|---|---|
| `sompo` | `sompo123` | Sompo | todas as fazendas + abas de cadastro |
| `gestor.santarita` | `santarita123` | Gestor de Fazenda | só a Fazenda Santa Rita (`SOMPO-ESP32`) |
| `gestor.valeverde` | `valeverde123` | Gestor de Fazenda | só a Fazenda Vale Verde (`SOMPO-ESP32-SIM`) |

A credencial de env (`PAINEL_USUARIO`/`PAINEL_SENHA`) continua valendo como um login Sompo
de reserva. Os perfis só funcionam com o **login ligado** (`PAINEL_SENHA` definida).

---

## 14. Pontos de atenção (o que já custou debug)

- **`SOMPO_API_KEY` vazia na Lambda** (senão dashboard vazio — ver §9).
- **Duas chaves Supabase, papéis diferentes:** API usa a **secret** (service_role, ignora
  RLS); ESP32 usa a **publishable/anon** (só INSERT). Erro numa não aparece na outra.
- **`api/.env` não vai pra Lambda** (gitignorado) — as envs de produção ficam em
  `infra/.env.aws` (também gitignorado) e o script as envia.
- **ESP32 só enxerga Wi-Fi 2.4 GHz** (use hotspot do celular em 2.4).
- **Sem driver CP2102** o Windows não cria a porta COM.
- **KY-026 lido pelo A0 (GPIO35)** — D0 queimado; calibrar `LIMIAR_CHAMA` no Serial.
- **MAX6675 lendo 0 °C fixo** → fiação; trocar SO↔SCK.
- **Learner Lab expira no fim do curso** — a Lambda some junto; plano B no Render (§9).
- **Docker local exige SVM Mode ligado na BIOS** (sem ele o Docker Desktop mostra
  "Virtualization support not detected"); o CloudShell dispensa o Docker local.
- **No `pwsh` do Linux, `*` solto vira glob** — por isso o script usa `--principal=*`.

---

## 15. Stack

**Hardware/Firmware:** ESP32 DevKit V1 · C++/Arduino (Arduino IDE / arduino-cli) · sensores
MPU-6050, AHT10, MAX6675, KY-026, RC522, reed switches, GPS NEO-6M, buzzer, potenciômetro.
**Nuvem:** Supabase (PostgreSQL + PostgREST + RLS).
**Backend:** Python 3.12 · Flask · waitress · requests · python-docx · pytest.
**IA:** Google Gemini (Generative Language API).
**Frontend:** HTML + TailwindCSS (CDN) + JavaScript vanilla + Material Symbols.
**Infra:** Docker · AWS Lambda + ECR (Learner Lab) · Cloudflare Pages · Render (plano B) ·
Git/GitHub.
