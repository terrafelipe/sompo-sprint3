"""Temperatura por dia e Alertas tem periodo proprio, que parte do seletor global."""
import re
from urllib.parse import parse_qs, urlparse

from tests.test_painel import painel, pw, nav  # noqa: F401


def abrir_maquina(page):
    nav(page, 'visao')
    page.select_option('#equipamentoSel', '1')
    page.wait_for_load_state('networkidle')
    pw.expect(page.locator('#tempDiaSub')).to_contain_text('últimos 7 dias')


def gravar(page):
    """Registra (rota, dias) de cada GET de /resumo e /eventos feito daqui para frente."""
    pedidos = []

    def ver(req):
        url = urlparse(req.url)
        if url.hostname == 'painel.test' and url.path in ('/resumo', '/eventos'):
            pedidos.append((url.path, parse_qs(url.query).get('dias', [''])[0]))
    page.on('request', ver)
    return pedidos


def test_periodo_da_temperatura_so_recarrega_a_temperatura(painel):
    page, state = painel
    abrir_maquina(page)
    pw.expect(page.locator('#tempDiaDias')).to_have_value('7')
    pw.expect(page.locator('#tempDiaDias')).to_have_attribute('aria-label', 'Período da temperatura')
    pedidos = gravar(page)
    page.select_option('#tempDiaDias', '30')
    pw.expect(page.locator('#tempDiaSub')).to_contain_text('últimos 30 dias')
    page.wait_for_load_state('networkidle')
    assert pedidos == [('/resumo', '30')]
    pw.expect(page.locator('#atividadeSub')).to_contain_text('últimos 7 dias')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_periodo_dos_alertas_so_recarrega_os_alertas(painel):
    page, state = painel
    abrir_maquina(page)
    pw.expect(page.locator('#alertasDias')).to_have_value('7')
    pw.expect(page.locator('#alertasDias')).to_have_attribute('aria-label', 'Período dos alertas')
    pedidos = gravar(page)
    page.select_option('#alertasDias', '90')
    pw.expect(page.locator('#atividadeSub')).to_contain_text('últimos 90 dias')
    pw.expect(page.locator('#tiposSub')).to_have_text('Total nos últimos 90 dias')
    pw.expect(page.locator('#kpiAlertasPill')).to_have_text('90 dias')
    page.wait_for_load_state('networkidle')
    assert pedidos == [('/eventos', '180')]
    pw.expect(page.locator('#tempDiaSub')).to_contain_text('últimos 7 dias')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_trocar_o_global_reinicia_as_secoes(painel):
    page, state = painel
    abrir_maquina(page)
    page.select_option('#tempDiaDias', '90')
    page.select_option('#alertasDias', '7')
    pw.expect(page.locator('#tempDiaSub')).to_contain_text('últimos 90 dias')
    page.locator('[data-periodo="30"]').click()
    pw.expect(page.locator('#tempDiaDias')).to_have_value('30')
    pw.expect(page.locator('#alertasDias')).to_have_value('30')
    pw.expect(page.locator('#tempDiaSub')).to_contain_text('últimos 30 dias')
    pw.expect(page.locator('#atividadeSub')).to_contain_text('últimos 30 dias')


def test_refresh_mantem_o_periodo_de_cada_secao(painel):
    page, state = painel
    page.clock.install()
    abrir_maquina(page)
    page.select_option('#tempDiaDias', '90')
    page.select_option('#alertasDias', '30')
    pw.expect(page.locator('#tempDiaSub')).to_contain_text('últimos 90 dias')
    pw.expect(page.locator('#atividadeSub')).to_contain_text('últimos 30 dias')
    page.wait_for_load_state('networkidle')
    pedidos = gravar(page)
    page.clock.fast_forward(5100)
    for _ in range(100):
        if len(pedidos) >= 2:
            break
        page.wait_for_timeout(50)
    page.wait_for_load_state('networkidle')
    pw.expect(page.locator('#tempDiaSub')).to_contain_text('últimos 90 dias')
    assert sorted(pedidos) == [('/eventos', '60'), ('/resumo', '90')]
    pw.expect(page.locator('#tempDiaDias')).to_have_value('90')
    pw.expect(page.locator('#alertasDias')).to_have_value('30')


def test_periodo_da_secao_e_contexto_novo_so_dela(painel):
    page, state = painel
    abrir_maquina(page)
    state['hold'] = '/resumo'
    page.select_option('#tempDiaDias', '30')
    pw.expect(page.locator('#graficoTempDia')).to_have_class(re.compile(r'viz-carregando'))
    assert not page.locator('#graficoAtividade').evaluate("e => e.classList.contains('viz-carregando')")
    for rota in state['held']:
        rota.fulfill(json={'dados': []})
    state['held'].clear()
    pw.expect(page.locator('#graficoTempDia')).not_to_have_class(re.compile(r'viz-carregando'))
