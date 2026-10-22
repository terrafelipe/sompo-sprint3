# Aba "Leituras", calendário próprio e período personalizado

Data: 2026-10-21. Mockup aprovado pelo Felipe: `2026-10-21-leituras-calendario-mockup.html`
(interativo; abrir no navegador). Estado do código de partida: `main` com o filtro De/Até das
últimas leituras já publicado (`7534154`, Issue #3).

## Intenção

O Felipe usa o painel para **auditar os dados** da máquina: escolher, por exemplo, de 21/09 a 21/10
e ver todas as leituras daquele mês. Hoje isso já funciona na seção "Últimas leituras", mas:

1. a seção só é alcançada rolando a página; não há atalho no alto, ao lado de Resumo, Alertas, Risco
   e Telemetria;
2. o rodapé mostra só "Página N", sem o total de páginas e sem pular para uma página específica;
3. os campos de data são o calendário nativo do navegador (padrão do Windows, quadrado, em outras
   cores), que destoa do resto do painel;
4. as outras telas que filtram por dias (Temperatura por dia, Feed de alertas, Histórico) só aceitam
   7, 30 ou 90 dias.

## O que será entregue

**G1. Aba "Leituras".** A barra de atalhos do Painel da máquina passa a ter
Resumo, Alertas, Risco, Telemetria e **Leituras**; clicar rola até a seção, como as outras. A seção
(hoje "Últimas leituras") passa a se chamar **Leituras** e fica assim:
- cabeçalho com o botão de período (ícone de calendário, "21/09/2026 até 21/10/2026") e "Limpar";
- tabela com as mesmas colunas de hoje (50 linhas por página, da mais nova para a mais velha);
- rodapé: "Mostrando 1 a 50 de 8.928 leituras", botão **Anterior**, **Página [caixa de seleção] de 179**,
  botão **Próxima**;
- sem período escolhido, tudo continua como hoje (as 10 mais recentes, com a atualização de 5 s).

**G2. Calendário próprio**, um único componente reaproveitado em todo o painel, no visual do painel
(Inter, cinzas neutros, vermelho `#b70100`, borda e cantos dos selects estilizados, temas claro e
escuro). Dois modos:
- **intervalo** (Leituras, Temperatura por dia, Feed de alertas, Histórico): clique no primeiro dia,
  passe o mouse (prévia do intervalo) e clique no segundo; coluna de atalhos (Hoje, Ontem, Últimos 7
  dias, Últimos 30 dias, Este mês, Mês passado, Últimos 90 dias); setas de mês e de ano; rodapé com
  resumo ("21 out até 21 out · 30 dias"), **Limpar** e **Aplicar**;
- **dia único** (cadastro de máquina: Fabricação e Última manutenção): um clique escolhe e fecha, sem
  "Aplicar" nem atalhos.
Semana começando no domingo (D S T Q Q S S), mês e ano no cabeçalho, hoje com contorno, dias
futuros desabilitados. Teclado completo: setas movem o dia, PageUp/PageDown mudam o mês, Home/End,
Enter escolhe, Esc fecha e devolve o foco ao botão. No celular cabe na largura da tela e os atalhos
viram uma fileira rolável acima do mês.

**G3. Botão "Período"** como quarto item depois de 7, 30 e 90 dias em **Temperatura por dia**,
**Feed de alertas** e **Histórico**. Cada seção guarda o seu próprio período, como hoje. Com período
livre ativo, o botão mostra o intervalo ("21 set – 21 out") e fica selecionado; escolher 7, 30 ou 90
dias volta ao comportamento atual.

**G4. Lista de páginas no padrão do painel.** A lista aberta da caixa de página (e de qualquer outro
select) usa a barra de rolagem fina e arredondada do painel, sem as setinhas do Windows. O Felipe
mostrou o problema por foto: a lista estreita com a barra cinza padrão do Windows.

## Fora do escopo (decidido pelo Felipe: "só o que pedi")

Período no filtro global do topo e no relatório em PDF; Início (carteira) e resumo da fazenda
(continuam em 7 dias); filtro por data em Ocorrências; score de risco (continua sempre 7 dias);
exportar CSV; escolher hora (só dias); biblioteca externa de calendário.

## O que faria isto dar errado, mesmo que funcione

- Qualquer parte com cara de componente nativo do Windows ou do Chrome.
- Quebrar o que já funciona: a atualização de 5 s do painel, o modo ao vivo, a paginação sem linhas
  repetidas (o `corte` do `7534154`), as seleções de 7/30/90 dias.
- Consultas a mais ao Supabase em cada atualização: a ida Lambda (EUA) → Supabase (SP) custa cerca de
  0,3 s por consulta, e cada rota do painel já faz de 2 a 5.

## Restrições

- Flask na AWS Lambda; Supabase por PostgREST (`supabase_client.py`); Python 3.12 em produção.
- CSP do painel: sem `unsafe-eval`, sem handlers inline, sem script externo novo (por isso nada de
  biblioteca de calendário; o componente é código próprio em `index.html`).
- Tailwind local (CLI 3.4.17): classe nova no HTML exige rebuild de `api/static/painel.css`
  (`docs/COMO_TESTAR.md` §8).
- Horário de Brasília (UTC-3 fixo) para todas as datas; período máximo de 1 ano (365 dias de
  diferença entre as datas); sem dias futuros.
- Sem SQL novo, se possível. O deploy continua manual (`sompo-deploy`).
- Testes: pytest (backend) e Playwright em blocos (PC de casa tem pouca RAM). TDD.

## Decisões do Felipe (nas palavras dele, resumidas)

- Aba "Leituras" ao lado de Resumo, Alertas, Risco e Telemetria, com escolha de data/período.
- Rodapé com "Página X de Y" e uma caixa de seleção para ir a uma página específica.
- Trocar o visual do calendário, que "não bate com o site"; usar em mais lugares: Temperatura por
  dia, Feed de alertas, Histórico, "tudo que envolve dias e data".
- Protótipo v2 aprovado ("tá perfeito").
- Escopo fechado em "só o que pedi".

## Escolhas minhas (o Felipe pode desfazer)

1. **Total de leituras:** o backend conta com `Prefer: count=exact` do PostgREST (cabeçalho
   `Content-Range`) **só na página 1** do período e devolve `total_leituras` e `total_paginas`; o
   painel guarda esses números durante o período. As páginas seguintes não recontam. Sem SQL novo.
2. **Caixa de página:** `select` estilizado enquanto houver até 200 páginas; acima disso, um campo
   numérico ("Página [ 37 ] de 5.426"; Enter ou sair do campo vai à página; número maior que o total
   vira a última página), porque uma lista de milhares de números é ruim de rolar. **Na prática o campo
   numérico será o caso comum:** a placa grava a cada 10 s (2 s no modo ao vivo), ou seja, cerca de 8.640
   leituras por dia e 268 mil num mês, mais de 5 mil páginas de 50. Os números do mockup (8.928
   leituras, 179 páginas) são só ilustrativos.
3. **Backend dos outros períodos:** `/eventos`, `/resumo` e `/operacoes` passam a aceitar
   `?de=AAAA-MM-DD&ate=AAAA-MM-DD` como alternativa a `?dias=`, com a mesma semântica do
   `/telemetria` (inclusivo, Brasília, até 1 ano) e um helper único compartilhado; mandar `dias` e
   `de/ate` juntos dá 400 `periodo_invalido`. `/scores` e `/relatorio/risco` continuam só com `dias`.
4. **Comparação com o período anterior:** Feed de alertas e Temperatura comparam com o período
   imediatamente anterior de mesmo tamanho (hoje o painel pede `dias*2`); com `de/ate`, o painel pede
   de `de - n dias` até `ate` (limite na escolha 8).
5. **Seletores de dias viram botões:** as caixas `#tempDiaDias`, `#alertasDias` e `#historicoDias`
   são substituídas pelos botões 7/30/90/Período do protótipo, e os testes que as usam são ajustados.
6. **Limpar** no calendário apaga a seleção em edição; **Aplicar** fica desabilitado sem data inicial;
   com só a data inicial, Aplicar vale um dia só.
7. **Dia único:** Fabricação e Última manutenção não aceitam datas futuras (hoje o campo nativo aceita).
8. **Comparação com o período anterior só quando cabe em 1 ano:** o período anterior de mesmo tamanho
   precisa caber na regra de 365 dias (a janela pedida é `de - n` até `ate`). Se 2n passar de 365 dias
   (período livre acima de cerca de 6 meses), o painel mostra os dados do período sem a comparação, e
   o texto "vs. período anterior" não aparece. Com 7, 30 ou 90 dias nada muda.
9. **Clique nos botões 7/30/90 do topo (filtro global):** continua sobrescrevendo Temperatura por dia
   e Feed de alertas, como hoje, e agora também **apaga o período livre** dessas duas seções (o botão
   "Período" volta a "Período" e o rótulo some). O Histórico e as Leituras não são afetados pelo
   filtro do topo, como já são hoje.
10. **Contagem que demora:** `count=exact` com tempo limite (cerca de 3 s). Se estourar ou falhar, a
    seção mostra "Página N" sem total, só com Anterior e Próxima e o campo de página, e a tabela segue
    funcionando; o painel nunca fica sem as linhas por causa da contagem. Período de um ano com 2 s de
    gravação é o pior caso; medir no deploy.

## O que fica para quem for construir

Estrutura e nome do componente e das funções; a ordem das etapas (sugestão: calendário, depois
Leituras, depois os três períodos); o desenho exato das animações (curva `cubic-bezier(0.23,1,0.32,1)`,
150 ms, respeitando `prefers-reduced-motion`); como medir o custo da contagem exata (a escolha 10 já
define o que acontece se ela demorar); os testes que cobrem cada parte.

## Como saber que está pronto

- Escolho 21/09 a 21/10 em Leituras, vejo "Mostrando … de …", "Página 1 de N" e salto para a página 10
  pela caixa; a lista aberta tem a barra fina do painel.
- A aba "Leituras" aparece e rola até a seção; não há nenhum calendário nativo do navegador no painel.
- Temperatura por dia, Feed de alertas e Histórico aceitam um período livre e mostram o intervalo
  escolhido; 7/30/90 dias continuam como antes.
- Fabricação e Última manutenção abrem o calendário de dia único.
- Suítes de backend e de navegador verdes (em desktop e celular), revisão do Codex sem achado aberto.
