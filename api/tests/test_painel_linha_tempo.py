"""Linha do tempo do Painel da maquina (mockup aprovado da Issue #5), com a rota respondida pelo teste."""
from tests.ajuda_linha_tempo import resposta_exemplo, servir, vazia  # noqa: F401
from tests.test_painel import nav, painel, pw  # noqa: F401


def _abrir(page, resposta=None):
    st = servir(page, resposta)
    nav(page, 'visao')
    page.evaluate("pausar('manual')")
    page.select_option('#equipamentoSel', '1')
    pw.expect(page.locator('#ltGrafico svg')).to_be_visible()
    return st


def _x_da_hora(page, hhmm):
    """Posicao x (na tela) de um horario do dia 22/10 no grafico."""
    return page.evaluate("""hhmm => {
      const svg = document.querySelector('#ltGrafico svg'), d = Object.fromEntries(Object.entries(svg.dataset).map(([k, v]) => [k, +v]));
      const t = Date.parse('2026-10-22T' + hhmm + ':00-03:00');
      const r = svg.getBoundingClientRect(), W = svg.viewBox.baseVal.width;
      return r.left + (d.ml + (t - d.ini) / (d.fim - d.ini) * d.iw) / W * r.width;
    }""", hhmm)


def test_resumo_mostra_alarmes_motor_e_lacuna(painel):
    page, _ = painel
    _abrir(page)
    r = page.locator('#ltResumo')
    pw.expect(r).to_contain_text('5 alarmes de incêndio')
    pw.expect(r).to_contain_text('4 alarmes de furto')
    pw.expect(r).to_contain_text('7 h 05 de motor ligado')
    pw.expect(r).to_contain_text('4 h 45 sem enviar')


def test_grafico_tem_temperatura_limites_motor_cracha_e_lacuna(painel):
    page, _ = painel
    _abrir(page)
    svg = page.locator('#ltGrafico svg')
    pw.expect(svg.locator('path.lt-temp')).to_have_count(1)
    pw.expect(svg.locator('text', has_text='40 °C')).to_have_count(1)
    pw.expect(svg.locator('text', has_text='60 °C')).to_have_count(1)
    assert svg.locator('rect.lt-motor').count() == 3
    assert svg.locator('rect.lt-cracha').count() == 2
    assert svg.locator('rect.lt-lacuna').count() == 1
    marcas = svg.locator('[data-lt-marca]')
    assert marcas.count() == 6   # capo, atencao x3, critico x2, partida, movimento, recusado -> 6 grupos/pontos
    pw.expect(svg.locator('text', has_text='×3')).to_have_count(1)
    pw.expect(svg.locator('text', has_text='×2')).to_have_count(1)


def test_limite_fora_da_escala_vira_rotulo(painel):
    page, _ = painel
    d = resposta_exemplo()
    d['limites'] = {'atencao': 450, 'critico': 550}
    _abrir(page, d)
    svg = page.locator('#ltGrafico svg')
    assert svg.locator('line.lt-limite').count() == 0
    pw.expect(page.locator('#ltGrafico')).to_contain_text('crítico: 550 °C')
    pw.expect(page.locator('#ltGrafico')).to_contain_text('atenção: 450 °C')


def test_arrastar_mostra_hora_temperatura_motor_e_operador(painel):
    page, _ = painel
    _abrir(page)
    page.locator('#ltGrafico svg').scroll_into_view_if_needed()
    y = page.locator('#ltGrafico svg').bounding_box()
    page.mouse.move(_x_da_hora(page, '09:33'), y['y'] + y['height'] * 0.4)
    leitura = page.locator('#ltLeitura')
    pw.expect(leitura).to_contain_text('22/10 09:3')
    pw.expect(leitura).to_contain_text('°C')
    pw.expect(leitura).to_contain_text('Motor ligado')
    pw.expect(leitura).to_contain_text('João Silva')
    page.mouse.move(_x_da_hora(page, '18:00'), y['y'] + y['height'] * 0.4)
    pw.expect(leitura).to_contain_text('Sem leituras')


def test_celular_sem_rolagem_horizontal(painel, request):
    page, _ = painel
    _abrir(page)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    alvo = page.locator('[data-lt-marca] rect.lt-alvo').first.bounding_box()
    assert alvo['width'] >= 22 or request.node.callspec.id == 'desktop'


def test_sem_leituras_e_erro_continuam(painel):
    page, _ = painel
    st = servir(page, lambda p: (502, {'erro': 'falha_na_consulta'}))
    nav(page, 'visao')
    page.evaluate("pausar('manual')")
    page.select_option('#equipamentoSel', '1')
    pw.expect(page.locator('#linhaTempo')).to_contain_text('Linha do tempo indisponível', timeout=8000)
    pw.expect(page.locator('#linhaTempo button', has_text='Tentar novamente')).to_be_visible()
    assert st['urls']


def test_tema_escuro_usa_as_cores_do_tema(painel):
    page, _ = painel
    _abrir(page)
    page.evaluate("document.documentElement.dataset.tema = 'escuro'")
    # espera as transicoes de cor (150 ms no .seg) terminarem: nada branco sobra no tema escuro
    page.wait_for_function("""() => ![...document.querySelectorAll('#linhaTempo *')].some(e => {
      const c = getComputedStyle(e); return c.backgroundColor === 'rgb(255, 255, 255)' || c.fill === 'rgb(255, 255, 255)'; })""", timeout=3000)


# ---- lista de eventos, grupos, filtros e ligacao com o grafico ----

def test_lista_por_dia_mais_recente_primeiro_e_hora_crescente_no_dia(painel):
    page, _ = painel
    _abrir(page, resposta_exemplo(horas=168))
    dias = page.locator('#ltLista .lt-dia')
    pw.expect(dias.first).to_contain_text('22 de outubro')
    pw.expect(dias.nth(1)).to_contain_text('21 de outubro')
    horas = page.locator('#ltLista .lt-ev').evaluate_all(
        "els => { const out = []; for(const e of els){ if(e.closest('[data-dia]').dataset.dia !== els[0].closest('[data-dia]').dataset.dia) break; out.push(e.querySelector('.h').textContent); } return out; }")
    assert horas == sorted(horas) and len(horas) > 5


def test_alarmes_repetidos_viram_uma_linha_que_abre(painel):
    page, _ = painel
    _abrir(page)
    grupo = page.locator('#ltLista .lt-ev', has_text='Escape em atenção')
    pw.expect(grupo).to_have_count(1)
    pw.expect(grupo).to_contain_text('3 vezes entre 09:12 e 09:25 · até 53 °C')
    pw.expect(grupo).to_have_attribute('aria-expanded', 'false')
    grupo.click()
    pw.expect(grupo).to_have_attribute('aria-expanded', 'true')
    filhos = page.locator(f'#ltLista .lt-filhos[data-de="{grupo.get_attribute("data-lt-alvo")}"]')
    pw.expect(filhos).to_contain_text('09:18')
    pw.expect(filhos).to_contain_text('47 °C')


def test_grupos_respeitam_30_min_mesmo_tipo_e_mesmo_dia(painel):
    page, _ = painel
    _abrir(page)
    tamanhos = page.evaluate("""() => {
      const e = (id, tipo, em) => ({id, tipo, em, eixo: 'incendio'});
      return LinhaDoTempo.grupos([
        e(1, 'escape_atencao', '2026-10-22T09:00:00-03:00'), e(2, 'escape_atencao', '2026-10-22T09:29:00-03:00'),
        e(3, 'escape_atencao', '2026-10-22T10:00:00-03:00'), e(4, 'escape_critico', '2026-10-22T10:05:00-03:00'),
        e(5, 'escape_atencao', '2026-10-22T23:50:00-03:00'), e(6, 'escape_atencao', '2026-10-23T00:10:00-03:00'),
      ]).map(g => g.itens.length); }""")
    assert tamanhos == [2, 1, 1, 1, 1]


def test_filtros_e_contagem(painel):
    page, _ = painel
    _abrir(page)
    lista, cont = page.locator('#ltLista'), page.locator('#ltCont')
    pw.expect(cont).to_have_text('22 eventos · 9 alarmes')
    page.locator('#ltFiltros [data-f="alarmes"]').click()
    pw.expect(lista).not_to_contain_text('Motor ligou')
    pw.expect(lista).to_contain_text('Capô aberto')
    page.locator('#ltFiltros [data-f="incendio"]').click()
    pw.expect(lista).not_to_contain_text('Capô aberto')
    pw.expect(lista).to_contain_text('Escape crítico')
    page.locator('#ltFiltros [data-f="rotina"]').click()
    pw.expect(lista).to_contain_text('Motor ligou')
    pw.expect(lista).not_to_contain_text('Escape crítico')
    chip = page.locator('#ltResumo [data-filtro="furto"]')
    chip.click()
    pw.expect(page.locator('#ltFiltros [data-f="furto"]')).to_have_attribute('aria-pressed', 'true')
    pw.expect(lista).to_contain_text('Crachá recusado')
    pw.expect(lista).not_to_contain_text('Escape crítico')
    page.locator('#ltResumo [data-filtro="furto"]').click()
    pw.expect(page.locator('#ltFiltros [data-f="tudo"]')).to_have_attribute('aria-pressed', 'true')


def test_tocar_no_marcador_rola_e_seleciona_na_lista(painel):
    page, _ = painel
    _abrir(page)
    marca = page.locator('#ltGrafico [data-lt-marca]').nth(2)   # capo, atencao, critico...
    marca.locator('rect.lt-alvo').dispatch_event('click')
    linha = page.locator('#ltLista .lt-ev.sel')
    pw.expect(linha).to_contain_text('Escape crítico')
    pw.expect(linha).to_be_in_viewport()
    pw.expect(page.locator('#ltLeitura')).to_contain_text('Escape crítico')


def test_tocar_na_lista_marca_o_grafico_e_tocar_de_novo_desmarca(painel):
    page, _ = painel
    _abrir(page)
    linha = page.locator('#ltLista .lt-ev', has_text='Capô aberto')
    linha.click()
    pw.expect(page.locator('#ltGrafico .lt-marca.sel .lt-anel')).to_have_count(1)
    pw.expect(page.locator('#ltLeitura')).to_contain_text('02:14')
    page.locator('#ltLista .lt-ev', has_text='Capô aberto').click()
    pw.expect(page.locator('#ltGrafico .lt-anel')).to_have_count(0)


def test_estados_vazio_filtro_sem_resultado_e_corte(painel):
    page, _ = painel
    _abrir(page, vazia())
    pw.expect(page.locator('#ltLista')).to_contain_text('Nenhum evento neste período')
    pw.expect(page.locator('#ltLeitura')).to_contain_text('A máquina ficou parada')
    page.unroute('**/telemetria/linha-do-tempo*')
    d = resposta_exemplo()
    d['eventos'] = [e for e in d['eventos'] if e['eixo'] != 'incendio']
    d['omitidos'] = 1234
    servir(page, d)
    page.evaluate('carregarLinhaTempo()')
    pw.expect(page.locator('#ltLista')).to_contain_text('1.234 eventos de rotina mais antigos não aparecem; escolha um período menor.')
    page.locator('#ltFiltros [data-f="incendio"]').click()
    pw.expect(page.locator('#ltLista')).to_contain_text('Nenhum evento com este filtro')
    page.locator('#ltLista button', has_text='Ver tudo').click()
    pw.expect(page.locator('#ltFiltros [data-f="tudo"]')).to_have_attribute('aria-pressed', 'true')


def test_reduced_motion_sem_animacao(painel):
    page, _ = painel
    page.emulate_media(reduced_motion='reduce')
    _abrir(page)
    nomes = page.locator('#ltLista .lt-ev').evaluate_all('els => els.map(e => getComputedStyle(e).animationName)')
    assert nomes and set(nomes) == {'none'}
