# Linha do tempo com eventos em primeiro lugar

Data: 2026-10-22. Issue #5. Mockup aprovado pelo Felipe ("gostei de como ficou, faça exatamente
desse jeito"): `2026-10-22-linha-do-tempo-eventos-mockup.html` (interativo; abrir no navegador).
Código de partida: `main` = `7410c7f` (Issue #4: calendário próprio e período livre já no `main`).

## Intenção

A seção "Linha do tempo" do Painel da máquina (visão) hoje mostra 4 faixas (Máquina, Risco, Crachá,
Alertas) em 96 blocos de 15 min, sempre nas 24 h até a última leitura, com o detalhe só no hover.
O Felipe achou difícil analisar: informação mal distribuída e poluída, não diz o que aconteceu,
difícil de navegar. A pergunta que a seção precisa responder primeiro, nas palavras dele:
**"quais eventos aconteceram"**.

Referências usadas no mockup: Samsara (lista de eventos com hora, tipo e status ao lado da linha do
tempo; seletor de período), Datadog (eventos marcados sobre o gráfico da métrica), Grafana state
timeline (trechos contínuos em vez de blocos), John Deere Operations Center (resumo antes do gráfico).

## O que será entregue (igual ao mockup)

**G1. Cabeçalho.** Título "Linha do tempo", subtítulo com a janela ("24 horas até a última leitura
(22/10, 22:20)"; "7 dias até…"; no Período, "21/09/2026 até 21/10/2026") e o seletor
**24 h | 7 dias | Período**. 24 h e 7 dias terminam na última leitura da máquina (como hoje).
Período abre o calendário próprio (`Calendario.abrir`, modo intervalo, máximo de 1 ano, o mesmo da
Issue #4) e usa dias inteiros de Brasília.

**G2. Resumo em chips.** Número de alarmes de incêndio, número de alarmes de furto, tempo de motor
ligado e, se houver, tempo sem enviar. Os dois chips de alarme são botões que filtram a lista
(tocar de novo volta para "Tudo"); os outros dois são só informação.

**G3. Um gráfico só** (SVG, largura total), de cima para baixo:
- um marcador por alarme (ou por grupo de alarmes repetidos, com "×N"), linha vertical fina até o pé
  do gráfico, vermelho para incêndio e azul para furto, maior quando crítico;
- a linha da **temperatura do escape** com área suave, as linhas tracejadas dos limites de
  atenção e crítico com o rótulo em °C;
- faixa **Motor** (trechos contínuos verdes onde ligado);
- faixa **Crachá** (trechos azuis das sessões);
- **hachurado** na altura toda onde a placa não enviou;
- eixo do tempo (5 marcas em 24 h; um rótulo por dia em 7 dias; no Período, marcas espaçadas que
  caibam).
Legenda acima do gráfico. Abaixo, uma **caixa de leitura**: sem nada escolhido, uma dica ("Toque ou
arraste no gráfico…"); ao passar o mouse ou arrastar o dedo, "22/10 09:31 · Escape 63 °C · Motor
ligado · João Silva" (ou "Sem leituras").

**G4. Lista de eventos**, logo abaixo, com os filtros **Tudo | Só alarmes | Incêndio | Furto |
Rotina** e a contagem ("22 eventos · 9 alarmes").
- Agrupada por dia (cabeçalho fixo "Quinta-feira, 22 de outubro" + "N alarmes"/"sem alarmes"); dias
  do mais recente para o mais antigo; dentro do dia, em ordem de hora.
- Cada linha: hora, ícone no tom do eixo, título, detalhe, selo **Crítico** / **Atenção** / Rotina.
- Alarmes do mesmo tipo seguidos, no mesmo dia, até 30 min um do outro, viram **uma linha**
  ("Escape em atenção · 3 vezes entre 09:12 e 09:25 · até 53 °C") que abre e mostra cada um.
- Eventos de rotina em tom mais apagado.
- Tipos: os alarmes da tabela `eventos` (títulos de `TITULO_TIPO`); **Crachá aceito** e **Sessão
  encerrada** (das sessões, com operador e duração); **Crachá recusado** (tentativas negadas de
  `registros_operacao`); e os calculados das leituras: **Motor ligou / Motor parou** (com "Partida
  com crachá" / "Sem sessão de crachá aberta" / "Ficou 4 h 39 ligado"), **Placa parou de enviar /
  voltou a enviar** (com a duração) e **Temperatura voltou ao normal** (primeira faixa abaixo do limite
  de atenção depois de um alarme de escape ou chama; detalhe "38 °C · calculado das leituras").

**G5. Gráfico e lista ligados.** Tocar num marcador seleciona o evento (ou grupo) e rola a lista até
ele; tocar numa linha da lista marca o marcador (anel pulsando) e põe o cursor e a caixa de leitura
naquele horário; tocar de novo desmarca.

**G6. Estados.** Sem leituras da máquina: a mensagem de hoje. Janela sem eventos: gráfico vazio + "A
máquina ficou parada e sem leituras novas neste período" e, na lista, "Nenhum evento neste período"
com o intervalo. Filtro sem resultado: "Nenhum evento com este filtro" + botão "Ver tudo". Erro:
"Não deu para carregar a linha do tempo." com "Tentar de novo".

**G7. Desempenho com 7 dias e Período.** Uma função SQL nova agrega a telemetria por faixa no banco
(o Felipe roda o `.sql` uma vez no Supabase, como o `ao_vivo.sql`). A API faz as consultas em
paralelo e devolve tudo em **uma** resposta.

## Fora do escopo

- Outras seções do painel (Temperatura por dia, Atividade de alertas, Histórico, Leituras) não mudam.
- O firmware e as tabelas não mudam (só uma função SQL nova, sem tabela nova).
- Os textos e as amostras do mockup que existem só nele: o bloco "Teste os estados", "O que muda",
  "O que é simulado", o selo "Mockup com dados de exemplo" e o botão de tema da página.
- Gravar no banco os eventos calculados (motor, placa, temperatura normal): são calculados a cada
  consulta.

## O que faria isto dar errado, mesmo que funcione

- Ficar mais lenta que a atual em 24 h (hoje ~3 s) ou levar mais de ~4 s em 7 dias no Lambda.
- Lista que vira poluição de novo: dezenas de "Motor ligou/parou" por oscilação de uma faixa. Trechos
  de motor separados por menos de uma faixa sem leitura **não** contam como parar e ligar.
- Gráfico ou lista que só funcionam com mouse; não caber em 400 px de largura.
- Cor como único sinal (os selos têm texto; os marcadores críticos são maiores).
- Antes de o Felipe rodar o SQL, a seção quebrar em produção (ver R4).

## Restrições

- R1. Mesmos tokens, fonte, ícones (Material Symbols) e componentes do painel (`.seg`, chips,
  `ligarHover`/`tipEsconder` quando servir, `animarAgora`/`entrar`/`revelar`, `mudou`); tema escuro;
  `prefers-reduced-motion`. A seção mantém `data-section="linhaTempo"` e o lugar no layout.
- R2. A CSP não permite `eval` nem estilo/script de outro domínio; Tailwind só com classes que existem
  no `painel.css` (classe nova exige rebuild, comando no `HANDOFF` da #4 / `contexto.md`).
- R3. Somente leitura no banco. A função SQL roda com as permissões de quem chama
  (`security invoker`), recebe a máquina e o intervalo, e só o `service_role` executa.
- R4. **Ordem de deploy segura:** se a função ainda não existir no Supabase, a API cai na agregação
  atual em Python para janelas de até 72 h; acima disso devolve um erro claro
  (`sql_pendente`) e o painel mostra "Falta rodar `linha_do_tempo.sql` no Supabase para períodos
  longos." Nada mais do painel é afetado.
- R5. Testes: Python (rota e cálculos, Supabase simulado), SQL no PGlite (`firmware/sql/tests`), e
  navegador (Playwright, desktop e mobile), como nas Issues anteriores.

## Decisões do Felipe

- Eventos primeiro; o resto (gráfico, resumo) serve à lista. ("quais eventos aconteceram")
- Fazer exatamente como o mockup. ("faça exatamente desse jeito")
- 7 dias e Período com função SQL no Supabase, que ele roda.
- Entram os alarmes **e** a rotina (motor, crachá, placa), com filtro. (aceitou a proposta: "pode seguir")
- Issue nova para a tarefa (#5).

## Escolhas minhas (o Felipe pode desfazer)

- C1. **Tamanho da faixa** pela janela, para ~300 pontos: 24 h → 5 min; 7 dias → 30 min; Período →
  o menor de {5, 10, 15, 30, 60, 120, 180, 360, 720, 1440} min que dê no máximo 400 faixas.
- C2. **Placa sem enviar** = faixas seguidas sem leitura somando pelo menos 15 min (e pelo menos 2
  faixas). Lacunas menores não aparecem. Não conta antes da primeira nem depois da última leitura
  da janela.
- C3. **Motor ligou/parou** nas bordas dos trechos de faixas com `motor_ligado`; a hora mostrada é o
  início da faixa (precisão da faixa: 5 min em 24 h). Trechos separados só por faixas sem leitura
  (lacuna de envio) são o mesmo trecho.
- C4. **Limites no gráfico.** Cada alarme de escape traz só o limite que cruzou em
  `detalhes.limiar_c` (o firmware hoje está em 40/60 °C para a demonstração na Next e volta para
  450/550 depois). Atenção = `limiar_c` do último `escape_atencao` da janela; crítico = o do último
  `escape_critico`; sem alarme daquele tipo, o padrão 450 (atenção) e 550 (crítico). O eixo vai do
  menor ao maior valor da temperatura com folga de 10%, incluindo um limite só se ele for no máximo
  1,5× a temperatura máxima; limite fora do eixo não tem linha e vira um rótulo no canto ("crítico:
  550 °C"). "Voltou ao normal" usa o limite de atenção do próprio alarme que o abriu.
  (O `ESCAPE_ATENCAO = 450` de outras seções do painel não muda: fora do escopo.)
- C5. **Temperatura no gráfico** = máxima da faixa (pico não some na média); a caixa de leitura mostra
  essa máxima.
- C6. **Severidade** pelo número que o firmware grava em `eventos.severidade`: ≥ 3 é **Crítico**,
  1–2 é **Atenção**; sem número, por tipo (chama, escape_critico, operador_nao_autorizado e
  sensor_falha críticos; o resto atenção). **Crachá recusado** é furto/atenção.
- C7. O Período do resto do painel **não** comanda esta seção; ela tem o próprio seletor (como no
  mockup). Ao trocar de máquina volta para 24 h.
- C8. **Atualização:** a seção não segue o ciclo de 5 s do painel; recarrega a cada 60 s em 24 h e
  7 dias (a janela anda com a última leitura) e nunca no Período. Trocar de janela ou de máquina
  carrega na hora.
- C9. Sessão aberta vai até o fim da janela; sessão sem início dentro da janela começa na borda.
  Horário de sessão e de crachá recusado = `ocorrido_em`, ou `recebido_em` quando ele for nulo.
- C10. **Com a função SQL instalada, as três janelas usam a função**; o Python atual fica só como
  plano B de R4 (até 72 h).
- C11. **Muitos eventos (Período longo):** a API devolve no máximo 1.000 eventos, mantendo **todos os
  alarmes** e cortando a rotina mais antiga primeiro; a resposta diz quantos ficaram de fora e a lista
  mostra no fim "N eventos de rotina mais antigos não aparecem; escolha um período menor." O resumo
  (G2) conta tudo, mesmo o que foi cortado.
- C12. **Sem máquina escolhida** (consulta legada por `dispositivo_id`) não há sessões nem crachás:
  a faixa Crachá fica vazia e "Motor ligou" não diz se havia crachá.

## O que fica para quem for construir

- Nome e assinatura exatos da função SQL e o formato do JSON da rota (manter `janela` e `faixas`
  compatíveis no que já existe; acrescentar `temp_max` por faixa, `sessoes`, `eventos`).
- Se os eventos calculados nascem no Python (preferível: testável sem navegador) ou no front.
- Quantas marcas no eixo do Período; posição exata dos rótulos no celular.
- Animações: as do mockup (linha da temperatura desenhando, linhas da lista entrando, anel pulsando,
  grupo abrindo) com a duração e as curvas do painel.

## Como saber que está pronto

1. Em 24 h, a seção mostra o mesmo que o mockup com os dados de teste (resumo, gráfico, lista,
   grupos, filtros, ligação gráfico↔lista, estados vazio/filtro/erro), no desktop e a 400 px, nos dois
   temas.
2. 7 dias e Período funcionam com a função SQL (teste no PGlite e teste da rota com o Supabase
   simulado), e caem no comportamento de R4 sem ela.
3. Suítes verdes: backend, SQL (`node firmware/sql/tests/run.mjs`) e navegador.
4. Em produção (depois do `sompo-deploy` e do SQL): 24 h em até ~3 s e 7 dias em até ~4 s.
