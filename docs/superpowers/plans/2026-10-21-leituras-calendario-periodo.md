# Aba Leituras, calendário próprio e período livre: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** aba "Leituras" com total de páginas e salto de página, calendário próprio no visual do painel e botão "Período" em Atividade de alertas, Temperatura por dia e Histórico, mais calendário de dia único no cadastro de máquina (Issue #4).

**Architecture:** o calendário é um componente de página única (`api/static/calendario.js` + `calendario.css`) que troca datas como texto `AAAA-MM-DD`, sem `Date` no meio, para não haver erro de fuso. No backend, um helper `frota.janela()` lê `de`/`ate` (e `corte`) para todas as rotas e as consultas aceitam uma `janela` (início, fim exclusivo) além de `dias`. A contagem de leituras é feita só na página 1.

**Tech Stack:** Flask + PostgREST (`supabase_client.py`), HTML/JS puro em `api/static/index.html`, Tailwind local (CLI 3.4.17), pytest + Playwright (Chromium).

**Spec:** `docs/superpowers/specs/2026-10-21-leituras-calendario-periodo-design.md` (mockup: `2026-10-21-leituras-calendario-mockup.html`, ao lado).

## Global Constraints

- CSP do painel: sem `unsafe-eval`, sem biblioteca externa nova; script e CSS próprios vêm de `/static/` (`script-src 'self'`).
- Datas em horário de Brasília (UTC-3 fixo); `de`/`ate` inclusivos; fim da janela exclusivo (00:00 do dia seguinte ao `ate`); no máximo 365 dias de diferença; sem dias futuros no calendário.
- Erro de período é sempre `400` com `{"erro": "periodo_invalido"}` (`frota.FrotaErro`); `dias` junto com `de`/`ate` também é `400`.
- Página de leituras: 50 linhas; caixa `select` até 200 páginas, campo numérico acima disso; contagem com tempo limite de 3 s, e falha da contagem nunca derruba a tabela.
- Comparação com o período anterior só na Atividade de alertas e só quando `2n <= 365`; Temperatura e Histórico não comparam. `/scores` e `/relatorio/risco` continuam só com `dias`.
- Clique no filtro global 7/30/90 do topo apaga o período livre de Atividade de alertas e de Temperatura por dia; Histórico e Leituras não mudam com ele.
- Classe Tailwind nova no HTML exige rebuild: de dentro de `api\`, `C:\dev\_tools\tailwindcss-windows-x64.exe -c tailwind\painel.config.js -i tailwind\entrada.css -o static\painel.css --minify`, e `static/painel.css` entra no commit.
- Testes (PC de casa, RAM curta): Python em `C:\dev\sompo-preview\.venv\Scripts\python.exe`, rodado de dentro de `api\`; Playwright em blocos (`tests/test_painel*.py` em grupos de ~10 arquivos).
- Commits pequenos, só dos arquivos da tarefa (outras sessões mexem neste clone), mensagem em arquivo sem BOM, com `Refs #4` (o último leva `Closes #4`). `git push` só com autorização do Felipe e enviando só os commits desta Issue.
- Tema claro e escuro: o CSS novo usa só as variáveis `--v-*` que o `index.html` já define.

## Review Focus

Entradas e falhas que o spec implica e que as tarefas abaixo fixam com teste:

1. "Hoje" do calendário é o dia de Brasília mesmo com o navegador em outro fuso (Task 3).
2. Período que atravessa virada de mês/ano e 29 de fevereiro (Task 1, e o mês de fevereiro bissexto no calendário, Task 3).
3. Trocar de máquina ou fazenda com o calendário aberto: o calendário fecha sozinho (Task 3).
4. Campo de página com vazio, 0, texto, decimal e número maior que o total (Task 4).
5. Contagem de leituras que falha ou demora: a tabela e a navegação Anterior/Próxima continuam (Tasks 2 e 4).
6. Período livre ativo e depois clique no filtro global 7/30/90 (Task 5).

## File Structure

- Create `api/static/calendario.js`: componente `window.Calendario` (um só calendário reaproveitado). Responsabilidade: abrir, desenhar, teclado, fechar.
- Create `api/static/calendario.css`: estilos do calendário e do botão "Período".
- Modify `api/frota.py`: `janela()`; `/operacoes` aceita `de/ate`.
- Modify `api/supabase_client.py`: `janela` em `consultar_periodo`, `consultar_eventos`, `consultar_resumo`; `contar_telemetria_periodo`.
- Modify `api/app.py`: `/telemetria` usa `frota.janela` e devolve totais; `/eventos` e `/resumo` aceitam `de/ate`; remove `_periodo_de_ate`.
- Modify `api/static/index.html`: atalhos, seções, JS de integração, bloco CSS dos selects.
- Tests: create `api/tests/test_janela_periodo.py`, `api/tests/test_painel_calendario.py`; modify `test_leituras_periodo.py`, `test_painel_leituras_periodo.py`, `test_painel_periodo_secao.py`, `test_painel.py`.
- Docs: `contexto.md`, `README.md`.

---

### Task 1: Janela de período no backend (`de/ate` em /eventos, /resumo, /operacoes)

**Files:**
- Modify: `api/frota.py` (junto de `periodo()`, e `listar_operacoes`), `api/supabase_client.py`, `api/app.py` (`/telemetria`, `/eventos`, `/resumo`; apagar `_periodo_de_ate`, `_BRT`)
- Test: `api/tests/test_janela_periodo.py` (novo); `api/tests/test_leituras_periodo.py` deve continuar verde sem mudanças de comportamento

**Interfaces:**
- Produces: `frota.janela(com_corte: bool = False) -> tuple[datetime, datetime] | None`: lê `?de=&ate=` (e `?corte=` se `com_corte`), devolve `(inicio, fim)` com fuso -03:00, `fim` exclusivo e, com corte, `min(fim, corte ou agora UTC)`; `None` sem `de` e sem `ate`; levanta `FrotaErro('periodo_invalido')` para formato, dia inexistente, invertido, mais de 365 dias de diferença, estouro do calendário (ano 9999), `corte` inválido ou sem fuso, e `dias` junto.
- Produces: `db.consultar_periodo(tabela, filtros, dias=None, campo='criado_em', order='criado_em.desc,id.desc', janela=None)`; com `janela` filtra `campo >= inicio` e `campo < fim`; `db.consultar_eventos(dispositivo, dias=7, equipamento=None, janela=None)`; `db.consultar_resumo(dispositivo, dias=7, equipamento=None, janela=None)` filtrando `dia >= inicio.date()` e `dia <= (fim - 1 dia).date()`.

- [ ] **Step 1: Testes que falham** em `test_janela_periodo.py` (fixture `banco` e `gestor` de `tests.test_frota`):
  - `test_eventos_com_de_ate_passa_a_janela_em_brasilia`: `GET /eventos?equipamento=1&de=2026-09-21&ate=2026-10-01` chama `consultar_eventos(..., janela=(datetime(2026,9,21,tzinfo=BRT), datetime(2026,10,2,tzinfo=BRT)))` e não passa `dias`.
  - `test_resumo_com_de_ate_passa_a_janela`; `test_operacoes_com_de_ate_filtra_recebido_em_pela_janela` (verifica `campo='recebido_em'` e a `janela`).
  - `test_janela_atravessa_29_de_fevereiro_e_virada_de_ano`: `de=2028-02-28&ate=2028-03-01` → fim `2028-03-02`; `de=2026-12-30&ate=2027-01-02` → fim `2027-01-03`.
  - `test_de_ate_invalidos_dao_400` (os mesmos casos de `test_periodos_invalidos_dao_400`, sem `pagina`) e `test_dias_junto_com_de_ate_da_400`, nas três rotas.
  - `test_consultar_periodo_com_janela_filtra_gte_e_lt` e `test_consultar_resumo_com_janela_usa_dia_do_primeiro_ao_ultimo_dia` (com `patch.object(db, '_request_json')`, como em `test_consultas_periodo.py`).
  - `test_sem_de_ate_o_comportamento_por_dias_continua` nas três rotas.
- [ ] **Step 2: Rodar e ver falhar** — `pytest tests/test_janela_periodo.py -q` → FAIL (`janela` não existe).
- [ ] **Step 3: Implementar** `frota.janela` (mover para lá a lógica de `_periodo_de_ate` e do `corte`, mantendo `_BRT`), os parâmetros `janela` nas três funções do cliente, e fazer `/eventos`, `/resumo`, `/operacoes` chamarem `janela = frota.janela()` e, quando houver, usá-la em vez de `periodo()`. Fazer `/telemetria` usar `frota.janela(com_corte=True)` e apagar `_periodo_de_ate` do `app.py`.
- [ ] **Step 4: Verde** — `pytest tests/test_janela_periodo.py tests/test_leituras_periodo.py tests/test_consultas_periodo.py tests/test_dias_limite.py -q` → PASS.
- [ ] **Step 5: Documentar** em `contexto.md` (tabela de rotas: `de/ate` em `/eventos`, `/resumo`, `/operacoes`) e commitar: `git add api/frota.py api/supabase_client.py api/app.py api/tests/test_janela_periodo.py contexto.md` → `backend: janela de periodo (de/ate) nas rotas de eventos, resumo e operacoes (#4)`.

---

### Task 2: Total de leituras e de páginas (só na página 1)

**Files:**
- Modify: `api/supabase_client.py`, `api/app.py` (ramo de período de `/telemetria`)
- Test: `api/tests/test_leituras_periodo.py`

**Interfaces:**
- Consumes: `frota.janela(com_corte=True)` (Task 1).
- Produces: `db.contar_telemetria_periodo(dispositivo, inicio: datetime, fim: datetime, equipamento=None) -> int` com `Prefer: count=exact`, `Range: 0-0`, `timeout=3`, lendo o total do cabeçalho `Content-Range` (`0-0/268000` ou `*/0`); levanta a exceção da requisição se falhar. Resposta de `/telemetria` com período e `pagina == 1` ganha `total_leituras: int | None` e `total_paginas: int | None` (`max(1, ceil(total/50))`); `None` nos dois se a contagem levantar; as outras páginas não trazem esses campos nem contam.

- [ ] **Step 1: Testes que falham:** `test_contar_le_o_total_do_content_range` (`0-0/268000` → 268000; `*/0` → 0; confere os cabeçalhos e o `timeout`), `test_pagina_1_traz_total_leituras_e_total_paginas` (8.928 → 179), `test_pagina_2_nao_conta_nem_traz_totais`, `test_falha_da_contagem_vira_none_e_a_tabela_segue` (200 com `dados` e totais `None`).
- [ ] **Step 2: Rodar e ver falhar** — `pytest tests/test_leituras_periodo.py -q`.
- [ ] **Step 3: Implementar** `contar_telemetria_periodo` com a sessão `_sessao` e `get_supabase_headers()` de `supabase_client.py`, e a chamada no ramo de período (só `pagina == 1`, dentro de `try` próprio).
- [ ] **Step 4: Verde** — mesmo comando → PASS.
- [ ] **Step 5: Commit** — `git add api/supabase_client.py api/app.py api/tests/test_leituras_periodo.py` → `backend: total de leituras e de paginas na pagina 1 do periodo (#4)`.

---

### Task 3: Componente Calendário + período das Leituras

**Files:**
- Create: `api/static/calendario.js`, `api/static/calendario.css`
- Modify: `api/static/index.html` (links no `<head>`; seção das leituras: trocar `#leiturasDe`, `#leiturasAte` e o botão "Ver leituras" por `#leiturasPeriodoBtn`; `limparMaquina` chama `Calendario.fechar()`), `api/static/painel.css` (rebuild)
- Test: `api/tests/test_painel_calendario.py` (novo), `api/tests/test_painel_leituras_periodo.py` (ajustar `_escolher`)

**Interfaces:**
- Produces (`window.Calendario`, datas sempre texto `AAAA-MM-DD`):
  `abrir({ancora: HTMLElement, modo: 'intervalo' | 'dia', inicio?: string, fim?: string, aoAplicar: (inicio: string, fim: string) => void}): void`; `fechar(): void`; `hoje(): string` (dia de `America/Sao_Paulo`); `formatar(iso: string): string` (`dd/mm/aaaa`).
- Produces (index.html): `leiturasPeriodo` continua `{de, ate, pagina, corte}`; `#leiturasPeriodoBtn` mostra `dd/mm/aaaa até dd/mm/aaaa` (ou "Escolher período") e tem `aria-haspopup="dialog"`.

- [ ] **Step 1: Testes que falham** em `test_painel_calendario.py`, usando o botão das Leituras (`_abrir` de `test_painel_leituras_periodo.py`): `test_hoje_e_o_dia_de_brasilia` (`Calendario.hoje()` igual a `Intl` com `timeZone: 'America/Sao_Paulo'`); `test_dois_cliques_escolhem_o_intervalo_e_aplicar_envia_as_datas`; `test_clique_antes_do_inicio_troca_a_ordem`; `test_atalhos_hoje_ontem_7_30_90_este_mes_mes_passado` (cada atalho preenche o intervalo esperado a partir de `hoje()`); `test_dias_futuros_ficam_desabilitados`; `test_aplicar_desabilitado_sem_inicio_e_com_so_o_inicio_vale_um_dia`; `test_limpar_apaga_a_selecao_sem_fechar`; `test_setas_de_mes_e_ano_e_fevereiro_bissexto` (2028 tem o dia 29); `test_esc_fecha_e_devolve_o_foco_ao_botao`; `test_clique_fora_fecha`; `test_teclado_setas_pageup_pagedown_enter`; `test_trocar_de_maquina_fecha_o_calendario`; `test_tema_escuro_usa_as_variaveis_do_painel` (fundo do `#calendario` igual a `--v-card`).
- [ ] **Step 2: Rodar e ver falhar** — `pytest tests/test_painel_calendario.py -q -x`.
- [ ] **Step 3: Implementar** `calendario.js`/`.css` a partir do protótipo aprovado (`2026-10-21-leituras-calendario-mockup.html`: mesmas classes `dia`, `ini`, `fim`, `meio`, atalhos laterais, rodapé com resumo, Limpar e Aplicar), trocando `Date` local por aritmética sobre `AAAA-MM-DD`, desabilitando dias após `hoje()`, com `role="dialog"`, foco no dia selecionado ao abrir, animação 150 ms com `cubic-bezier(0.23,1,0.32,1)` e `prefers-reduced-motion`; no celular os atalhos viram fileira rolável acima do mês. No `index.html`: `<link rel="stylesheet" href="/static/calendario.css"/>` e `<script src="/static/calendario.js"></script>` antes do script principal, `#leiturasPeriodoBtn` abre o calendário em modo `intervalo` e, ao aplicar, faz `leiturasPeriodo = {de, ate, pagina: 1, corte: null}` e chama `carregarLeiturasPeriodo()`; remover a validação de datas invertidas e o submit do formulário que deixaram de existir.
- [ ] **Step 4: Ajustar `test_painel_leituras_periodo.py`** (`_escolher` passa a abrir o calendário, clicar nos dois dias e Aplicar; `leiturasDe` some das asserções) e rodar: `pytest tests/test_painel_calendario.py tests/test_painel_leituras_periodo.py -q` → PASS.
- [ ] **Step 5: Rebuild do Tailwind** (comando em Global Constraints) e commit — `git add api/static/calendario.js api/static/calendario.css api/static/index.html api/static/painel.css api/tests/test_painel_calendario.py api/tests/test_painel_leituras_periodo.py` → `painel: calendario proprio e periodo das leituras por ele (#4)`.

---

### Task 4: Aba "Leituras", rodapé com total e salto de página, rolagem dos selects

**Files:**
- Modify: `api/static/index.html` (nav `#atalhosPainel`, seção das leituras, `carregarLeiturasPeriodo`, bloco `@supports (appearance: base-select)` ~linha 355), `api/static/painel.css` (rebuild)
- Test: `api/tests/test_painel_leituras_periodo.py`

**Interfaces:**
- Consumes: `total_leituras`, `total_paginas` da página 1 (Task 2); `Calendario` (Task 3).
- Produces: `#secLeituras` (id da seção, `data-ancora`), botão `data-ir="secLeituras"` com o texto "Leituras" depois de "Telemetria"; `#leiturasResumo` ("Mostrando 1 a 50 de 8.928 leituras", ou "Mostrando 1 a 50" sem total); `#leiturasIrPara` (`<select>` se `total_paginas <= 200`, senão `<input inputmode="numeric">`), `leiturasPeriodo.total_leituras` e `.total_paginas` guardados na página 1.

- [ ] **Step 1: Testes que falham:** `test_aba_leituras_aparece_e_rola_ate_a_secao` (botão presente, clique marca `aria-pressed` e a seção entra na tela); `test_rodape_mostra_total_e_paginas` (stub com `total_leituras=8928`, `total_paginas=179`: "Mostrando 1 a 50 de 8.928 leituras" e "de 179"); `test_select_de_pagina_ate_200_paginas_salta_para_a_escolhida`; `test_campo_numerico_acima_de_200_paginas_salta_com_enter_e_ao_sair`; `test_campo_de_pagina_invalido_volta_para_a_atual` (vazio, `0`, `abc`, `3.5`) e `test_numero_maior_que_o_total_vai_para_a_ultima`; `test_sem_total_o_rodape_nao_mostra_de_n_e_a_navegacao_segue` (totais `None`); `test_lista_aberta_dos_selects_tem_rolagem_fina` (o bloco `::picker(select)` de `index.html` contém `scrollbar-width:thin`).
- [ ] **Step 2: Rodar e ver falhar** — `pytest tests/test_painel_leituras_periodo.py -q -x`.
- [ ] **Step 3: Implementar:** botão e id da seção; guardar os totais da resposta da página 1 em `leiturasPeriodo`; desenhar o rodapé e o controle de página (campo: `Enter` e `blur` chamam o salto com valor limitado a `[1, total_paginas]`, entrada inválida restaura o número atual); título da seção passa a "Leituras" e o subtítulo sem período continua "As 10 leituras mais recentes da máquina"; em `::picker(select)` acrescentar `scrollbar-width: thin; scrollbar-color: var(--v-borda-forte) transparent; overscroll-behavior: contain` e esconder os botões da barra no WebKit.
- [ ] **Step 4: Verde** — `pytest tests/test_painel_leituras_periodo.py tests/test_painel_atalhos_fixos.py -q` → PASS.
- [ ] **Step 5: Rebuild do Tailwind e commit** — `git add api/static/index.html api/static/painel.css api/tests/test_painel_leituras_periodo.py` → `painel: aba Leituras, total e salto de pagina, rolagem fina nos selects (#4)`.

---

### Task 5: Período livre na Atividade de alertas

**Files:**
- Modify: `api/static/index.html` (substituir `#alertasDias` pelos botões 7/30/90/"Período"; `carregarEventos`, `diasDoPeriodo`, textos de `atividadeSub`/`tiposSub`/`feedSub`/`kpiAlertasPill`, handler global `[data-periodo]`, e a linha que faz `$('alertasDias').value = periodo`), `api/static/painel.css` (rebuild)
- Test: `api/tests/test_painel_periodo_secao.py`, `api/tests/test_painel_calendario.py`

**Interfaces:**
- Consumes: `Calendario.abrir` (Task 3), `/eventos?de=&ate=` (Task 1).
- Produces: `alertasLivre: null | {de: string, ate: string}` ao lado do `periodoAlertas` numérico; `diasEntre(de: string, ate: string): string[]` (lista de dias `AAAA-MM-DD`, usada no eixo do gráfico de atividade no lugar de `diasDoPeriodo(n)` quando há período livre); botões `#alertasPeriodoBtn` e `[data-seg="alertas"] [data-dias]` com `aria-pressed`.

- [ ] **Step 1: Testes que falham** (ajustando os de `test_painel_periodo_secao.py` de `select_option('#alertasDias', …)` para clicar os botões): `test_botoes_7_30_90_da_atividade_mudam_o_periodo_como_antes`; `test_periodo_livre_pede_a_janela_anterior_junto` (período de 20 dias pede `de` 20 dias antes até `ate`; o KPI mostra "vs. 20 dias anteriores"); `test_periodo_livre_acima_de_182_dias_nao_compara` (pede só `de/ate`; sem texto "vs."); `test_eixo_do_grafico_vai_do_de_ao_ate`; `test_rotulos_mostram_o_intervalo` (`atividadeSub`, `tiposSub`, `feedSub`, pílula do KPI); `test_clique_global_7_30_90_apaga_o_periodo_livre` (botão "Período" volta ao rótulo "Período").
- [ ] **Step 2: Rodar e ver falhar** — `pytest tests/test_painel_periodo_secao.py -q -x`.
- [ ] **Step 3: Implementar** o HTML dos botões (mesmo padrão do `#periodoWrap`), `alertasLivre` com `de`/`ate` do calendário (modo `intervalo`); em `carregarEventos`, com período livre pedir `/eventos?<seletor>&de=<de - n dias>&ate=<ate>` quando `2n <= 365` (senão `de/ate` do período) e separar atual/anterior pela data do evento no horário de Brasília; `variacao()` só quando há anterior (`rotuloPeriodo` = `${n} dias`); o handler global zera `alertasLivre` e o rótulo; `animados.delete` e `filtroDia = null` ao mudar o período, como já ocorre.
- [ ] **Step 4: Verde** — `pytest tests/test_painel_periodo_secao.py tests/test_painel_calendario.py tests/test_painel_ia_periodo.py tests/test_painel_sem_piscar.py -q` → PASS.
- [ ] **Step 5: Rebuild e commit** — arquivos da tarefa → `painel: periodo livre na atividade de alertas (#4)`.

---

### Task 6: Período livre na Temperatura por dia

**Files:**
- Modify: `api/static/index.html` (substituir `#tempDiaDias`; `carregarTempDia`; handler global), `api/static/painel.css` (rebuild)
- Test: `api/tests/test_painel_periodo_secao.py`

**Interfaces:**
- Consumes: `Calendario.abrir` (Task 3), `/resumo?de=&ate=` (Task 1).
- Produces: `tempLivre: null | {de: string, ate: string}`; `#tempPeriodoBtn` e `[data-seg="temp"] [data-dias]`.

- [ ] **Step 1: Testes que falham:** `test_botoes_7_30_90_da_temperatura_continuam`; `test_periodo_livre_pede_resumo_de_ate_sem_comparacao` (uma só chamada a `/resumo` com `de`/`ate`; `tempDiaSub` = "Escape e ambiente de dd/mm/aaaa a dd/mm/aaaa (N dias com leituras)"); `test_clique_global_apaga_o_periodo_livre_da_temperatura`; `test_periodo_sem_leituras_mostra_a_frase_de_sempre` ("Sem leituras no período.").
- [ ] **Step 2: Rodar e ver falhar** — `pytest tests/test_painel_periodo_secao.py -q -x`.
- [ ] **Step 3: Implementar** `tempLivre`, a chave de `mudou('tempdia', …)` passa a incluir o intervalo, e `animados.delete('tempdia')` ao trocar.
- [ ] **Step 4: Verde** — `pytest tests/test_painel_periodo_secao.py tests/test_painel_animacoes.py -q` → PASS.
- [ ] **Step 5: Rebuild e commit** → `painel: periodo livre na temperatura por dia (#4)`.

---

### Task 7: Período livre no Histórico

**Files:**
- Modify: `api/static/index.html` (substituir `#historicoDias`; `carregarHistorico`, o `addEventListener('change')` do seletor, `historicoPagina`), `api/static/painel.css` (rebuild)
- Test: `api/tests/test_painel_historico_fazenda.py` (ou novo `test_painel_historico_periodo.py`), `api/tests/test_painel.py` (a lista de selects com `picker-icon` perde `historicoDias`)

**Interfaces:**
- Consumes: `Calendario.abrir` (Task 3), `/operacoes?de=&ate=` (Task 1).
- Produces: `historicoLivre: null | {de: string, ate: string}`; `#historicoPeriodoBtn` e `[data-seg="historico"] [data-dias]`.

- [ ] **Step 1: Testes que falham:** `test_historico_7_30_90_continuam_pedindo_dias`; `test_historico_periodo_livre_pede_de_ate_e_volta_para_a_pagina_1`; `test_historico_periodo_livre_nao_mexe_nas_outras_secoes`; ajustar `test_painel.py` (linhas que citam `historicoDias`).
- [ ] **Step 2: Rodar e ver falhar** — `pytest tests/test_painel_historico_fazenda.py -q -x`.
- [ ] **Step 3: Implementar:** `carregarHistorico` monta `URLSearchParams` com `dias` ou `de`/`ate`; clique em 7/30/90 limpa `historicoLivre`; `historicoPagina = 0` em toda troca.
- [ ] **Step 4: Verde** — `pytest tests/test_painel_historico_fazenda.py tests/test_painel.py -q` → PASS (arquivo grande: rodar sozinho).
- [ ] **Step 5: Rebuild e commit** → `painel: periodo livre no historico (#4)`.

---

### Task 8: Calendário de dia único no cadastro de máquina

**Files:**
- Modify: `api/static/index.html` (campos `maqFabricacao` e `maqManutencao` ~linha 948 e o JS que lê/grava `.value` ~linhas 4211 e 4226), `api/static/painel.css` (rebuild)
- Test: `api/tests/test_painel.py` (linhas que preenchem `maqFabricacao`), `api/tests/test_painel_calendario.py`

**Interfaces:**
- Consumes: `Calendario.abrir({modo: 'dia'})` (Task 3).
- Produces: `#maqFabricacao` e `#maqManutencao` viram `<input type="hidden">` (mesmo `id`, valor `AAAA-MM-DD`, para o JS de leitura/gravação não mudar) e ganham os botões visíveis `#maqFabricacaoBtn` e `#maqManutencaoBtn` com o texto `dd/mm/aaaa` (ou "Escolher data").

- [ ] **Step 1: Testes que falham:** `test_dia_unico_escolhe_com_um_clique_e_fecha` (grava o `AAAA-MM-DD` no campo oculto e o texto do botão); `test_dia_unico_nao_aceita_data_futura`; `test_editar_maquina_mostra_as_datas_gravadas` (o texto do botão acompanha `m.fabricacao`); ajustar `test_painel.py` para escolher as datas pelo calendário em vez de `fill`.
- [ ] **Step 2: Rodar e ver falhar** — `pytest tests/test_painel_calendario.py -q -k dia_unico`.
- [ ] **Step 3: Implementar** o HTML, uma função pequena que mantém botão e campo oculto em sincronia (também ao abrir a edição e ao limpar o formulário) e conferir que o modo `dia` também bloqueia dias depois de `hoje()`, como o modo `intervalo`.
- [ ] **Step 4: Verde** — `pytest tests/test_painel_calendario.py tests/test_painel.py -q` → PASS.
- [ ] **Step 5: Rebuild e commit** → `painel: calendario de dia unico no cadastro de maquina (#4)`.

---

### Task 9: Fechamento (documentação, suíte inteira, revisão)

**Files:**
- Modify: `README.md`, `contexto.md`, `docs/COMO_TESTAR.md` (seção do calendário e de `static/calendario.*`)

- [ ] **Step 1:** documentar as rotas e o componente nos três arquivos; conferir que `docs/COMO_TESTAR.md` §8 continua certo (CSS gerado).
- [ ] **Step 2: Suíte inteira** — backend: `pytest` dos arquivos que não começam com `test_painel`; navegador em três blocos (`ls tests/test_painel*.py | split -l 10`). Mostrar a saída; qualquer vermelho é corrigido antes de seguir.
- [ ] **Step 3: Revisão do Codex** com `/revisar` (modelo e esforço perguntados ao Felipe na hora), corrigir os achados sustentados, repetir a suíte afetada.
- [ ] **Step 4: Commit final** com `Closes #4` e pedir ao Felipe o `git push` (só os commits desta Issue); depois do push, conferir `gh issue view 4` e avisar do `sompo-deploy`. Não precisa de SQL novo.
