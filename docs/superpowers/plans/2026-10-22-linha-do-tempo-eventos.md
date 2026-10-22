# Linha do tempo com eventos em primeiro lugar — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** trocar a seção "Linha do tempo" do Painel da máquina pela versão do mockup aprovado (resumo, um gráfico só, lista de eventos agrupada, filtros, 24 h / 7 dias / Período).

**Architecture:** uma função SQL agrega a telemetria por faixa no banco; a rota `/telemetria/linha-do-tempo` faz em paralelo faixas, alarmes, sessões e crachás recusados, calcula os eventos de rotina em Python (módulo puro `linha_do_tempo.py`) e devolve tudo numa resposta. O front ganha um arquivo próprio `static/linha_do_tempo.js` (desenho e interação, sem rede) e o `index.html` só busca os dados e chama o módulo.

**Tech Stack:** Flask, PostgREST/Supabase (RPC), PostgreSQL (PGlite nos testes), JS puro + SVG, pytest + Playwright.

**Spec:** `docs/superpowers/specs/2026-10-22-linha-do-tempo-eventos-design.md` (manda). Mockup: `docs/superpowers/specs/2026-10-22-linha-do-tempo-eventos-mockup.html` — o visual, os textos, as classes CSS e a lógica de desenho/grupos/filtros do front saem dele (copiar e adaptar, não reinventar).

## Global Constraints

- Python: `C:\dev\sompo-preview\.venv\Scripts\python.exe`; testes de dentro de `api\`. PowerShell 5.1 (sem `&&`). Código Python com `\` não vai em heredoc do Bash.
- Arquivos da worktree em CRLF: scripts de edição gravam com `newline='\r\n'`.
- CSP: sem `eval`, sem recurso de outro domínio; `wait_for_function` com função de seta.
- Classe Tailwind nova no HTML exige rebuild (de `api\`): `C:\dev\_tools\tailwindcss-windows-x64.exe -c tailwind\painel.config.js -i tailwind\entrada.css -o static\painel.css --minify`. Preferir CSS próprio em `static/linha_do_tempo.css` (como `calendario.css`).
- Tokens do painel (`--v-card`, `--v-borda`, `--v-texto2`, `--s-furto`, `--s-incendio`, `COR`), Material Symbols, tema escuro (`data-tema="escuro"`), `prefers-reduced-motion`.
- A seção mantém `data-section="linhaTempo"` e o container `#linhaTempo` (testes existentes em `test_painel_fila.py` usam "Sem leituras desta máquina" e "Linha do tempo indisponível").
- Valores fixados pela spec: faixa C1 `{5,10,15,30,60,120,180,360,720,1440}` min e no máximo 400 faixas (24 h → 5, 7 dias → 30); lacuna C2 ≥ 15 min e ≥ 2 faixas; grupo de alarmes ≤ 30 min, mesmo tipo, mesmo dia; limites padrão 450/550 °C; limite só no eixo se ≤ 1,5× a máxima; severidade ≥ 3 crítico; máximo 1.000 eventos (todos os alarmes ficam); atualização 60 s em 24 h/7 dias, nunca no Período.
- Commits pequenos com `Refs #5`; o último leva `Closes #5`. Mensagem em arquivo sem BOM (`git commit -F`).
- Sem push sem o OK do Felipe.

## Review Focus

1. Período longo (até 1 ano) com milhares de eventos: a resposta corta a rotina e o front avisa; a tela não trava (teste na Task 3 e na Task 6).
2. Máquina com lacunas de envio que cortam um trecho de motor ligado: não gera "Motor parou/ligou" falso (teste na Task 2).
3. Função SQL ainda não instalada em produção: 24 h continua funcionando (Python) e 7 dias mostra o aviso `sql_pendente` (testes nas Tasks 3 e 7).
4. Toque no celular (400 px): marcadores com alvo de 22 px, arrastar o dedo atualiza a leitura sem rolar a página na horizontal (teste na Task 5).
5. Resposta atrasada de outra janela/máquina chegando depois da troca não sobrescreve a seção (teste na Task 7).

---

### Task 1: Função SQL `linha_do_tempo_faixas`

**Files:**
- Create: `firmware/sql/linha_do_tempo.sql`
- Create: `firmware/sql/tests/linha_do_tempo.sql`
- Modify: `firmware/sql/tests/run.mjs` (aplicar 2× o `.sql` depois do `ao_vivo.sql` e imprimir o resultado do teste novo)

**Interfaces:**
- Produces: `public.linha_do_tempo_faixas(p_equipamento bigint, p_dispositivo text, p_inicio timestamptz, p_fim timestamptz, p_minutos int) returns table(inicio timestamptz, leituras int, motor_ligado boolean, temp_max real, risco text)` — uma linha por faixa, em ordem, inclusive as vazias (`leituras=0, motor_ligado=false, temp_max=null, risco=null`). Leitura em `(p_inicio, p_fim]` (mesma regra do `agregar` em Python: a leitura exatamente em `p_fim` cai na última faixa). Com `p_equipamento` filtra `equipamento_id`, senão `dispositivo_id`. `risco` = pior nível pela ordem do `ORDEM_RISCO` de `linha_do_tempo.py`.

- [ ] **Step 1: Preparar o runner.** Se `firmware/sql/tests/.runtime` não existir na worktree, copiar de `C:\dev\sompo-preview\firmware\sql\tests\.runtime` (é ignorado pelo git). Rodar `node firmware/sql/tests/run.mjs` → as linhas `ALL ... PASSED` de hoje.
- [ ] **Step 2: Escrever o teste** `firmware/sql/tests/linha_do_tempo.sql` no estilo de `tests/ao_vivo.sql` (`pg_temp.check_true`, `pg_temp.rejects`), com uma máquina própria (`dispositivo_id='LDT-1'`) e telemetria inserida direto:
  - 3 leituras em 24 h com faixa de 5 min → `count(*)=288`, `sum(leituras)=3`;
  - leitura exatamente em `p_fim` conta na última faixa; leitura em `p_inicio` não conta;
  - `temp_max` = maior `temp_escape` da faixa; `motor_ligado` = true se alguma leitura ligada; `risco` = 'CRITICO' quando a faixa tem 'ATENCAO' e 'CRITICO';
  - leitura de outra máquina não entra; sem `p_equipamento`, filtra por `p_dispositivo`;
  - `rejects` para `p_minutos` 0 e 1441, para `p_fim <= p_inicio` e para mais de 2.000 faixas (errcode 22023);
  - `has_function_privilege('anon', ...)` e `('authenticated', ...)` falsos, `service_role` verdadeiro;
  - termina com `select 'ALL LINHA DO TEMPO SQL ASSERTIONS PASSED' result;`.
- [ ] **Step 3: Rodar** `node firmware/sql/tests/run.mjs` → falha com "function linha_do_tempo_faixas ... does not exist".
- [ ] **Step 4: Implementar** `firmware/sql/linha_do_tempo.sql`: cabeçalho de comentário no estilo do `ao_vivo.sql` ("Apply after frota.sql. Idempotente."), `begin; ... commit;`, `create or replace function ... language sql stable security invoker set search_path=pg_catalog,public` (ou plpgsql para as validações), `generate_series` das faixas + `left join` da agregação por `floor(extract(epoch from (criado_em - p_inicio - interval '1 microsecond')) / (p_minutos*60))`; `revoke all ... from public, anon, authenticated; grant execute ... to service_role;`.
- [ ] **Step 5: Rodar** `node firmware/sql/tests/run.mjs` → todas as linhas `PASSED`, inclusive a nova.
- [ ] **Step 6: Commit** `sql: linha_do_tempo_faixas agrega a telemetria por faixa no banco (#5)`.

### Task 2: Cálculos da linha do tempo em Python

**Files:**
- Modify: `api/linha_do_tempo.py`
- Test: `api/tests/test_linha_do_tempo.py`

**Interfaces:**
- Consumes: faixas no formato da Task 1 (dicts com `inicio` ISO, `leituras`, `motor_ligado`, `temp_max`, `risco`).
- Produces:
  - `minutos_para(inicio: datetime, fim: datetime) -> int` (C1).
  - `agregar(linhas, fim, horas=24, minutos=15, inicio=None)` — o atual, agora com `temp_max` (maior `temp_escape` da faixa) e `inicio` opcional (janela do Período); continua sendo o plano B.
  - `severidade(evento: dict) -> str` → `'critico' | 'atencao'` (C6).
  - `eixo(tipo: str) -> str` → `'incendio' | 'furto'` (`chama_detectada`, `escape_*` → incêndio; o resto → furto).
  - `limites(alarmes: list[dict]) -> dict` → `{'atencao': float, 'critico': float}` (C4: `detalhes.limiar_c` do último `escape_atencao` / `escape_critico`; padrão 450/550).
  - `eventos_rotina(faixas: list[dict], minutos: int, sessoes: list[dict], alarmes: list[dict], lim: dict) -> list[dict]` — os calculados: `motor_ligou` (com `com_cracha: bool|None`), `motor_parou` (com `duracao_min`), `envio_parou` (com `duracao_min`), `envio_voltou`, `temp_normal` (com `temp`). Cada item: `{'tipo', 'em' (ISO), ...campos}`.
  - `cortar(eventos: list[dict], maximo=1000) -> tuple[list[dict], int]` — mantém todos com `eixo != 'rotina'`, corta a rotina mais antiga; devolve `(eventos_em_ordem, omitidos)`.
  - `resumo(alarmes, faixas, minutos) -> dict` → `{'incendio': int, 'furto': int, 'motor_min': int, 'sem_envio_min': int}`.

- [ ] **Step 1: Escrever os testes** (todos com `FIM` fixo como hoje):
  - `test_minutos_para_escolhe_a_faixa_pela_janela`: 24 h → 5; 168 h → 30; 31 dias → 120; 365 dias → 1440; 2 h → 5.
  - `test_agregar_traz_a_temperatura_maxima_da_faixa`: duas leituras 40 e 63 na mesma faixa → `temp_max == 63`; faixa vazia → `None`.
  - `test_severidade_pelo_numero_e_pelo_tipo`: `{'severidade': 4}` → critico; `2` → atencao; sem número e `tipo='sensor_falha'` → critico; sem número e `furto_capo` → atencao.
  - `test_limites_do_ultimo_alarme_de_cada_tipo_e_padrao`: `escape_atencao` com `limiar_c` 40 e `escape_critico` com 60 → `{'atencao': 40, 'critico': 60}`; sem alarmes → `{'atencao': 450, 'critico': 550}`; só atenção → `{'atencao': 40, 'critico': 550}`.
  - `test_motor_liga_e_para_nas_bordas_dos_trechos`: faixas de 5 min com motor ligado de 07:00 a 11:40 → um `motor_ligou` em 07:00 e um `motor_parou` em 11:40 com `duracao_min == 280`; `com_cracha` True quando uma sessão cobre 07:00, False quando não há sessão, None quando `sessoes is None` (C12).
  - `test_lacuna_de_envio_nao_quebra_o_trecho_de_motor`: motor ligado, 4 faixas sem leitura (20 min), motor ligado de novo → **um** `motor_ligou`, **um** `motor_parou`, mais `envio_parou`/`envio_voltou` com `duracao_min == 20`.
  - `test_lacuna_curta_nao_vira_evento`: 2 faixas vazias de 5 min (10 min) → nenhum `envio_parou`; 1 faixa vazia de 30 min → nenhum (C2: ≥ 2 faixas); faixas vazias antes da primeira leitura e depois da última → nenhum.
  - `test_temperatura_volta_ao_normal_depois_do_alarme`: `escape_critico` em 09:31 com `limiar_c` 60, `escape_atencao` anterior com `limiar_c` 40, faixas com `temp_max` 63, 55, 45, 38 → `temp_normal` na faixa do 38 com `temp == 38`; sem faixa abaixo do limite até o fim → nenhum.
  - `test_cortar_mantem_todos_os_alarmes`: 5 alarmes + 2.000 rotinas (total 2.005), `maximo=1000` → 1.000 itens (os 5 alarmes + as 995 rotinas mais recentes), `omitidos == 1005`, ordem final por `em`.
  - `test_resumo_conta_alarmes_motor_e_lacuna`.
- [ ] **Step 2: Rodar** `python -m pytest tests/test_linha_do_tempo.py -q` → falham por `ImportError`/asserção.
- [ ] **Step 3: Implementar** as funções acima em `api/linha_do_tempo.py` (módulo puro, sem I/O, comentários curtos em português sem acento como o resto do arquivo).
- [ ] **Step 4: Rodar** o mesmo comando → verde, incluindo os 3 testes antigos.
- [ ] **Step 5: Commit** `backend: eventos de rotina, limites e resumo da linha do tempo (#5)`.

### Task 3: Rota `/telemetria/linha-do-tempo` nova

**Files:**
- Modify: `api/supabase_client.py` (duas consultas novas), `api/app.py:547-563`
- Test: `api/tests/test_linha_do_tempo.py`

**Interfaces:**
- Consumes: Task 1 (RPC), Task 2 (funções), `frota.janela()` (`(inicio, fim)` com fim exclusivo, ou `None`), `frota.id_selecionado()`, `consultar_eventos(dispositivo, equipamento=eq, janela=(inicio, fim))`.
- Produces (`supabase_client.py`):
  - `consultar_faixas(dispositivo, equipamento, inicio, fim, minutos) -> list[dict]` via `chamar_rpc('linha_do_tempo_faixas', {...})`; se o Supabase responder `SupabaseError` com `codigo == 'PGRST202'` (função não existe), levanta `FuncaoAusente` (classe nova no mesmo arquivo).
  - `consultar_sessoes_janela(equipamento, inicio, fim) -> list[dict]` em `sessoes_operacao`: `equipamento_id=eq`, `inicio_em` entre `inicio - 1 dia` e `fim` **ou** `fim_em` dentro da janela (`or=(and(inicio_em.gte.X,inicio_em.lte.Y),and(fim_em.gte.A,fim_em.lte.B))`).
  - `consultar_negadas(equipamento, inicio, fim) -> list[dict]` em `registros_operacao` com `tipo=eq.tentativa_negada`, `select=registro_id,ocorrido_em,recebido_em,uid,motivo`, filtro por `recebido_em` na janela.
- Produces (rota): `GET /telemetria/linha-do-tempo?equipamento=&horas=24|168` ou `?equipamento=&de=AAAA-MM-DD&ate=AAAA-MM-DD`. Resposta 200:
  ```
  {janela: {inicio, fim, minutos, tipo: 'horas'|'periodo'},
   faixas: [{inicio, leituras, motor_ligado, temp_max, risco}],
   sessoes: [{inicio, fim, operador_nome, status}],
   eventos: [{id, tipo, eixo: 'incendio'|'furto'|'rotina', sev: 'critico'|'atencao'|'rotina', em,
              temp?, limiar_c?, operador_nome?, duracao_min?, com_cracha?, uid?}],
   omitidos: int, resumo: {incendio, furto, motor_min, sem_envio_min}, limites: {atencao, critico},
   ...frota.contexto()}
  ```
  Sem nenhuma leitura em `horas`: `{faixas: [], janela: null, ...}` como hoje. No Período sem leituras: `janela` preenchida, faixas todas vazias. `cracha_inicio`/`cracha_fim` saem das sessões (`em` = `inicio`/`fim`), `cracha_negado` das negadas (`em` = `ocorrido_em` ou `recebido_em`, C9; eixo furto, sev atencao). Sessões, eventos e negadas e as faixas vão em paralelo (`ThreadPoolExecutor(max_workers=4)`, como `_resumos` em `frota.py`).
  Sem a função: `horas <= 72` → `agregar` em Python (com `temp_max`); acima → `409 {'erro': 'sql_pendente'}`.

- [ ] **Step 1: Escrever os testes** (com `patch` das funções de `app`, como os atuais):
  - `test_rota_24h_usa_a_funcao_com_faixas_de_5_min`: `consultar_faixas` recebe `minutos=5`, janela `(fim-24h, fim)`; resposta com 288 faixas mockadas, `janela.minutos == 5`, `janela.tipo == 'horas'`.
  - `test_rota_7_dias_usa_faixas_de_30_min`.
  - `test_rota_periodo_usa_dias_de_brasilia`: `?de=2026-09-21&ate=2026-10-21` → `consultar_faixas` com `inicio = 2026-09-21T00:00-03:00`, `fim = min(2026-10-22T00:00-03:00, agora)`, `minutos == 120`.
  - `test_rota_junta_alarmes_sessoes_negadas_e_rotina_em_ordem`: eventos ordenados por `em`, cada um com `eixo`/`sev`; `cracha_inicio` traz `operador_nome`; `cracha_negado` com `recebido_em` quando `ocorrido_em` é nulo.
  - `test_rota_corta_rotina_e_conta_omitidos`: 3.000 sessões mockadas → `len(eventos) == 1000`, todos os alarmes presentes, `omitidos > 0`, `resumo` conta todos os alarmes.
  - `test_sem_funcao_24h_cai_no_python`: `consultar_faixas` levanta `FuncaoAusente` → usa `consultar_telemetria_intervalo` + `agregar`, 200.
  - `test_sem_funcao_7_dias_devolve_sql_pendente`: 409 `{'erro': 'sql_pendente'}`.
  - `test_horas_fora_do_limite_e_periodo_invalido`: `horas=169` → 168 (clamp, como `_parse_int` hoje); `de` sem `ate` → 400 `periodo_invalido` (handler de `FrotaErro`).
  - Os 2 testes atuais da rota passam a mockar `consultar_faixas` (o de "sem nenhuma leitura" continua igual).
- [ ] **Step 2: Rodar** `python -m pytest tests/test_linha_do_tempo.py -q` → os novos falham.
- [ ] **Step 3: Implementar** as consultas em `supabase_client.py` e a rota em `app.py` (importar as novas funções no topo como as outras `consultar_*`, para o `patch('app....')` funcionar).
- [ ] **Step 4: Rodar** `python -m pytest tests/test_linha_do_tempo.py tests/test_janela_periodo.py tests/test_consultas_periodo.py -q` → verde.
- [ ] **Step 5: Commit** `backend: linha do tempo com eventos, sessoes e periodo numa resposta so (#5)`.

### Task 4: Dados de teste do navegador

**Files:**
- Create: `api/tests/ajuda_linha_tempo.py`

**Interfaces:**
- Produces: `resposta_exemplo(fim_iso='2026-10-22T22:20:00-03:00', horas=24) -> dict` no formato da Task 3, com os dados do mockup do dia 22/10 (capô 02:14; crachá João 06:58–11:42; motor 07:01–11:40; escape atenção 09:12/09:18/09:25 44/47/53 °C; escape crítico 09:31/09:38 61/63 °C; voltou ao normal; partida sem crachá 13:05 + crachá recusado 13:04 + movimento 13:06; motor 13:05–13:09; Maria 14:10–16:31; motor 14:12–16:30; placa sem enviar 17:29–22:15); `vazia(fim_iso) -> dict` (janela sem eventos, faixas com leituras e motor desligado); `servir(page, respostas: list|callable) -> dict` que registra `page.route('**/telemetria/linha-do-tempo*', ...)` e guarda as URLs pedidas em `st['urls']`.

- [ ] **Step 1:** escrever o módulo (sem testes próprios; os testes das Tasks 5–7 o exercitam) e conferir com `python -c "from tests.ajuda_linha_tempo import resposta_exemplo; d=resposta_exemplo(); print(len(d['faixas']), len(d['eventos']))"` → `288` e o número de eventos do mockup.
- [ ] **Step 2:** sem commit separado — entra no commit da Task 5.

### Task 5: Módulo `linha_do_tempo.js`: resumo, gráfico e leitura

**Files:**
- Create: `api/static/linha_do_tempo.js`, `api/static/linha_do_tempo.css`
- Modify: `api/static/index.html` — `<link>` do CSS ao lado do `calendario.css` (linha ~436), `<script>` ao lado do `calendario.js` (linha ~1255); HTML da seção (linhas 640-652); `carregarLinhaTempo`/`desenharLinhaTempo` (linhas 3554-3640) passam a buscar e chamar o módulo
- Test: `api/tests/test_painel_linha_tempo.py`

**Interfaces:**
- Consumes: Task 3 (formato), Task 4 (dados), `TITULO_TIPO`, `COR`, `escapar` do painel (passados em `opcoes`, o módulo não lê globais do painel).
- Produces: `window.LinhaDoTempo.montar(container: HTMLElement, dados: object, opcoes: {titulos, cores, filtro?, aoFiltrar?(f), animar: bool}) -> {destruir(), selecionar(id|null)}`; `window.LinhaDoTempo.grupos(eventos) -> [{id, tipo, itens}]` (regra da spec, exposta para teste). IDs usados nos testes: `#ltResumo`, `#ltGrafico svg`, `#ltLeitura`, `[data-lt-marca="<grupo>"]`.

- [ ] **Step 1: Escrever os testes** (desktop e mobile pelo fixture `painel`; abrir com `nav(page, 'visao')` + `select_option('#equipamentoSel', '1')` como `test_painel_fila.py`):
  - `test_resumo_mostra_alarmes_motor_e_lacuna`: `#ltResumo` contém "5 alarmes de incêndio", "4 alarmes de furto", "de motor ligado", "4 h 46 sem enviar".
  - `test_grafico_tem_temperatura_limites_motor_cracha_e_lacuna`: no SVG, um `path` da temperatura, textos "40 °C" e "60 °C", retângulos de motor e crachá, um retângulo com `fill="url(#…)"` da lacuna, um `[data-lt-marca]` por grupo de alarmes (6 no exemplo) com "×3" e "×2".
  - `test_limite_fora_da_escala_vira_rotulo`: resposta com `limites={atencao:450, critico:550}` e temperatura máxima 70 → sem linha de 550 e o texto "crítico: 550 °C".
  - `test_arrastar_mostra_hora_temperatura_motor_e_operador`: `page.mouse.move` sobre ~09:31 → `#ltLeitura` com "09:3", "°C", "Motor ligado", "João Silva"; sobre 18:00 → "Sem leituras".
  - `test_celular_sem_rolagem_horizontal` (só mobile): `document.documentElement.scrollWidth <= innerWidth`, e o alvo de toque do marcador tem largura ≥ 22 px.
  - `test_tema_escuro_sem_cor_fixa_clara`: com `data-tema="escuro"`, nenhum elemento do `#linhaTempo` tem `fill` ou `color` `#ffffff`/`rgb(255, 255, 255)` computado no fundo.
  - Os 6 testes de `test_painel_fila.py` continuam passando sem mudança.
- [ ] **Step 2: Rodar** `python -m pytest tests/test_painel_linha_tempo.py -q` → falham.
- [ ] **Step 3: Implementar** a parte de cabeçalho/resumo/legenda/gráfico/leitura do mockup no módulo (mesmas medidas do SVG; altura do gráfico um pouco maior que no mockup — a curva ficou achatada — p.ex. área da temperatura de 110 px), CSS do mockup traduzido para os tokens do painel em `linha_do_tempo.css`, e o `index.html` buscando `/telemetria/linha-do-tempo?${seletorEquipamento()}&horas=24` e chamando `LinhaDoTempo.montar`. Conservar: `mudou('linhaTempo', ...)` com a assinatura `fim|soma das leituras|n eventos`, a verificação de resposta obsoleta (`eq !== equipamentoSelecionado`), o texto "Sem leituras desta máquina para montar a linha do tempo." e o erro: a spec (G6) pede "Não deu para carregar a linha do tempo." com "Tentar de novo", e `test_painel_fila.py` espera "Linha do tempo indisponível" → usar "Linha do tempo indisponível. Não deu para carregar os dados." + botão "Tentar de novo" (chama `carregarLinhaTempo()`), e acrescentar ao teste de erro de `test_painel_fila.py` a checagem do botão. Conservar também o redesenho no resize (linha 4586).
- [ ] **Step 4: Rodar** `python -m pytest tests/test_painel_linha_tempo.py tests/test_painel_fila.py -q` → verde.
- [ ] **Step 5: Commit** `painel: linha do tempo com resumo e grafico unico (#5)` (inclui `tests/ajuda_linha_tempo.py`).

### Task 6: Lista de eventos, grupos, filtros e ligação com o gráfico

**Files:**
- Modify: `api/static/linha_do_tempo.js`, `api/static/linha_do_tempo.css`
- Test: `api/tests/test_painel_linha_tempo.py`

**Interfaces:**
- Consumes: Task 5 (`montar`, `grupos`).
- Produces: IDs `#ltFiltros [data-f]`, `#ltCont`, `#ltLista`, `.lt-ev[data-lt-alvo]`, `.lt-dia`.

- [ ] **Step 1: Escrever os testes:**
  - `test_lista_por_dia_mais_recente_primeiro_e_hora_crescente_no_dia`: com `resposta_exemplo(horas=168)` de dois dias, o primeiro `.lt-dia` é o de 22/10; dentro dele as horas crescem.
  - `test_alarmes_repetidos_viram_uma_linha_que_abre`: "Escape em atenção" com "3 vezes entre 09:12 e 09:25 · até 53 °C"; clicar abre os 3 horários; `aria-expanded` muda.
  - `test_grupos_respeitam_30_min_mesmo_tipo_e_mesmo_dia`: `page.evaluate('LinhaDoTempo.grupos(...)')` com alarmes a 29 min (agrupa), 31 min (não), tipos diferentes (não), 23:50 e 00:10 (não).
  - `test_filtros_e_contagem`: "Só alarmes" esconde "Motor ligou"; "Incêndio" só tem eixo incêndio; "Rotina" só rotina; `#ltCont` "22 eventos · 9 alarmes" em Tudo; chip "alarmes de furto" aplica o filtro Furto e, clicado de novo, volta a Tudo.
  - `test_tocar_no_marcador_rola_e_seleciona_na_lista`: clicar `[data-lt-marca]` de 09:31 → a linha "Escape crítico" fica `.sel` e visível; `#ltLeitura` mostra "Escape crítico".
  - `test_tocar_na_lista_marca_o_grafico_e_tocar_de_novo_desmarca`: o marcador ganha o anel; segundo clique remove.
  - `test_estados_vazio_filtro_sem_resultado_e_corte`: `vazia()` → "Nenhum evento neste período" e a frase da máquina parada; filtro sem resultado → "Nenhum evento com este filtro" + "Ver tudo" volta a Tudo; resposta com `omitidos=1234` → "1.234 eventos de rotina mais antigos não aparecem; escolha um período menor."
  - `test_reduced_motion_sem_animacao`: com `page.emulate_media(reduced_motion='reduce')`, nenhuma linha da lista tem `animation-name` diferente de `none`.
- [ ] **Step 2: Rodar** → falham.
- [ ] **Step 3: Implementar** a lista, os grupos, os filtros, a ligação marcador↔lista e os estados como no mockup (textos iguais; `textContent`/`escapar` para tudo que vem da API).
- [ ] **Step 4: Rodar** `python -m pytest tests/test_painel_linha_tempo.py -q` → verde.
- [ ] **Step 5: Commit** `painel: lista de eventos agrupada, filtros e ligacao com o grafico (#5)`.

### Task 7: Seletor 24 h | 7 dias | Período e atualização

**Files:**
- Modify: `api/static/index.html` (cabeçalho da seção, `carregarLinhaTempo`, `carregarTudo` linha ~4546, troca de máquina/`limparMaquina`)
- Test: `api/tests/test_painel_linha_tempo.py`

**Interfaces:**
- Consumes: `Calendario.abrir({ancora, modo:'intervalo', inicio, fim, aoAplicar(de, ate)})`, estado novo `linhaTempoJanela = {horas: 24} | {horas: 168} | {de, ate}`.

- [ ] **Step 1: Escrever os testes:**
  - `test_7_dias_pede_horas_168`: clicar "7 dias" → URL com `horas=168`; subtítulo "7 dias até a última leitura".
  - `test_periodo_abre_calendario_e_pede_de_ate`: "Período" → calendário; escolher 21/09 a 21/10 → URL com `de=2026-09-21&ate=2026-10-21` e subtítulo "21/09/2026 até 21/10/2026" (usar `tests/ajuda_calendario.py`).
  - `test_trocar_de_maquina_volta_para_24h`.
  - `test_atualiza_a_cada_60_s_e_nao_no_periodo`: com `page.clock` (ou `page.evaluate` chamando `carregarTudo()` várias vezes), em 24 h a rota só é pedida de novo depois de 60 s; no Período nunca.
  - `test_sql_pendente_mostra_o_aviso`: 409 `{'erro':'sql_pendente'}` em 7 dias → "Falta rodar linha_do_tempo.sql no Supabase para períodos longos."; voltar para 24 h funciona.
  - `test_resposta_atrasada_nao_sobrescreve`: segurar a resposta de 7 dias (`state['hold']` ou rota que espera), clicar 24 h, soltar → a seção mostra 24 h.
- [ ] **Step 2: Rodar** → falham.
- [ ] **Step 3: Implementar** (o seletor usa `.seg` do painel; guarda a hora do último carregamento para os 60 s; ignora resposta cuja janela/máquina não é mais a atual).
- [ ] **Step 4: Rodar** `python -m pytest tests/test_painel_linha_tempo.py tests/test_painel_fila.py tests/test_painel_calendario.py -q` → verde.
- [ ] **Step 5: Commit** `painel: linha do tempo com 24 h, 7 dias e periodo proprio (#5)`.

### Task 8: Documentação e suíte completa

**Files:**
- Modify: `README.md`, `contexto.md`, `docs/COMO_TESTAR.md`, `docs/DEPLOY.md` (passo do SQL novo, na ordem: rodar `firmware/sql/linha_do_tempo.sql` no SQL Editor do Supabase **antes** do `sompo-deploy`; sem ele só 24 h funciona)

- [ ] **Step 1:** atualizar a rota na tabela de rotas do `contexto.md`, a seção do Painel da máquina no README e o roteiro de teste manual no `COMO_TESTAR.md` (abrir a máquina, ver resumo/gráfico/lista, filtros, tocar marcador, 7 dias, Período, tema escuro, celular).
- [ ] **Step 2: Suíte completa em blocos** (PC com pouca RAM), de `api\`: backend = `tests/test_*.py` que não começam com `test_painel`; navegador = `ls tests/test_painel*.py | split -l 10`, um `pytest` por bloco; SQL = `node firmware/sql/tests/run.mjs` da raiz. Tudo verde.
- [ ] **Step 3: Commit** `docs: linha do tempo nova, SQL e roteiro de teste (#5)`.
