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
    fundo_claro = page.evaluate("""() => [...document.querySelectorAll('#linhaTempo *')].filter(e => {
      const c = getComputedStyle(e); return c.backgroundColor === 'rgb(255, 255, 255)' || c.fill === 'rgb(255, 255, 255)'; }).length""")
    assert fundo_claro == 0
