"""Temperatura por dia e Alertas tem periodo proprio, que parte do seletor global."""
import re
from urllib.parse import parse_qs, urlparse

from tests.ajuda_calendario import escolher_periodo
from tests.test_painel import painel, pw, nav  # noqa: F401

SEG = '#alertasSeg'
LIVRE = f'{SEG} [data-periodo-livre]'


def dias_btn(n):
    return f'{SEG} [data-dias="{n}"]'


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
    pw.expect(page.locator(dias_btn(7))).to_have_attribute('aria-pressed', 'true')
    pw.expect(page.locator(SEG)).to_have_attribute('aria-label', 'Período dos alertas')
    pedidos = gravar(page)
    page.locator(dias_btn(90)).click()
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
    page.locator(dias_btn(7)).click()
    pw.expect(page.locator('#tempDiaSub')).to_contain_text('últimos 90 dias')
    page.locator('[data-periodo="30"]').click()
    pw.expect(page.locator('#tempDiaDias')).to_have_value('30')
    pw.expect(page.locator(dias_btn(30))).to_have_attribute('aria-pressed', 'true')
    pw.expect(page.locator('#tempDiaSub')).to_contain_text('últimos 30 dias')
    pw.expect(page.locator('#atividadeSub')).to_contain_text('últimos 30 dias')


def test_refresh_mantem_o_periodo_de_cada_secao(painel):
    page, state = painel
    page.clock.install()
    abrir_maquina(page)
    page.select_option('#tempDiaDias', '90')
    page.locator(dias_btn(30)).click()
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
    pw.expect(page.locator(dias_btn(30))).to_have_attribute('aria-pressed', 'true')


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


# ---------- periodo livre na Atividade de alertas ----------

def gravar_eventos(page):
    """Parametros de cada GET de /eventos feito daqui para frente."""
    pedidos = []

    def ver(req):
        url = urlparse(req.url)
        if url.hostname == 'painel.test' and url.path == '/eventos':
            pedidos.append({k: v[0] for k, v in parse_qs(url.query).items()})
    page.on('request', ver)
    return pedidos


def test_botao_periodo_vem_depois_de_7_30_90_e_comeca_desligado(painel):
    page, state = painel
    abrir_maquina(page)
    botoes = page.locator(f'{SEG} button')
    pw.expect(botoes).to_have_text(['7 dias', '30 dias', '90 dias', 'calendar_monthPeríodo'])
    pw.expect(page.locator(LIVRE)).to_have_attribute('aria-pressed', 'false')


def test_periodo_livre_pede_a_janela_anterior_junto(painel):
    page, state = painel
    abrir_maquina(page)
    pedidos = gravar_eventos(page)
    escolher_periodo(page, '2026-10-02', '2026-10-21', botao=LIVRE)          # 20 dias
    pw.expect(page.locator('#kpiAlertasSub')).to_contain_text('20 dias anteriores')
    ped = pedidos[-1]
    assert (ped['de'], ped['ate']) == ('2026-09-12', '2026-10-21') and 'dias' not in ped   # 20 dias antes de 02/10
    pw.expect(page.locator(LIVRE)).to_have_attribute('aria-pressed', 'true')
    pw.expect(page.locator(f'{LIVRE} .rot')).to_have_text('2 out – 21 out')
    for n in (7, 30, 90):
        pw.expect(page.locator(dias_btn(n))).to_have_attribute('aria-pressed', 'false')


def test_periodo_livre_separa_atual_e_anterior_pelo_dia_de_brasilia(painel):
    page, state = painel
    state['eventos'] = [
        dict(id=1, dispositivo_id='ESP-1', tipo='furto_capo', severidade=2, criado_em='2026-10-10T15:00:00+00:00'),
        dict(id=2, dispositivo_id='ESP-1', tipo='furto_capo', severidade=2, criado_em='2026-09-20T15:00:00+00:00'),
        dict(id=3, dispositivo_id='ESP-1', tipo='furto_capo', severidade=2, criado_em='2026-09-25T15:00:00+00:00'),
        # 01:30 UTC de 02/10 ainda e 01/10 em Brasilia: pertence ao periodo ANTERIOR, nao ao atual
        dict(id=4, dispositivo_id='ESP-1', tipo='furto_capo', severidade=2, criado_em='2026-10-02T01:30:00+00:00'),
    ]
    abrir_maquina(page)
    escolher_periodo(page, '2026-10-02', '2026-10-21', botao=LIVRE)
    pw.expect(page.locator('#kpiAlertas')).to_have_text('1')
    pw.expect(page.locator('#kpiAlertasSub')).to_contain_text('−67% vs. 20 dias anteriores')   # 1 contra 3


def test_periodo_livre_acima_de_182_dias_nao_compara(painel):
    page, state = painel
    abrir_maquina(page)
    pedidos = gravar_eventos(page)
    escolher_periodo(page, '2026-01-01', '2026-10-21', botao=LIVRE)           # 294 dias: o dobro passa de 365
    pw.expect(page.locator(f'{LIVRE} .rot')).to_have_text('1 jan – 21 out')
    pw.expect(page.locator('#kpiAlertasSub')).to_have_text('Eventos registrados no período')
    ped = pedidos[-1]
    assert (ped['de'], ped['ate']) == ('2026-01-01', '2026-10-21')


def test_eixo_do_grafico_vai_do_de_ao_ate_e_atravessa_29_de_fevereiro(painel):
    page, state = painel
    state['eventos'] = [dict(id=1, dispositivo_id='ESP-1', tipo='furto_capo', severidade=2, criado_em='2026-10-19T15:00:00+00:00')]
    abrir_maquina(page)
    assert page.evaluate("diasEntre('2028-02-27', '2028-03-02')") == \
        ['2028-02-27', '2028-02-28', '2028-02-29', '2028-03-01', '2028-03-02']
    assert page.evaluate("diasEntre('2026-12-30', '2027-01-02')") == ['2026-12-30', '2026-12-31', '2027-01-01', '2027-01-02']
    escolher_periodo(page, '2026-10-17', '2026-10-21', botao=LIVRE)
    pw.expect(page.locator('#graficoAtividade .viz-hit')).to_have_count(5)


def test_dia_do_evento_e_o_de_brasilia(painel):
    page, state = painel
    abrir_maquina(page)
    assert page.evaluate("diaBR('2026-10-21T01:30:00Z')") == '2026-10-20'
    assert page.evaluate("diaBR('2026-10-21T03:30:00Z')") == '2026-10-21'


def test_rotulos_mostram_o_intervalo(painel):
    page, state = painel
    abrir_maquina(page)
    escolher_periodo(page, '2026-10-02', '2026-10-21', botao=LIVRE)
    pw.expect(page.locator('#atividadeSub')).to_have_text('Eventos por dia de 02/10/2026 a 21/10/2026')
    pw.expect(page.locator('#tiposSub')).to_have_text('Total de 02/10/2026 a 21/10/2026')
    pw.expect(page.locator('#feedSub')).to_have_text('Eventos de 02/10/2026 a 21/10/2026')
    pw.expect(page.locator('#kpiAlertasPill')).to_have_text('20 dias')


def test_clique_global_7_30_90_apaga_o_periodo_livre(painel):
    page, state = painel
    abrir_maquina(page)
    escolher_periodo(page, '2026-10-02', '2026-10-21', botao=LIVRE)
    pw.expect(page.locator(LIVRE)).to_have_attribute('aria-pressed', 'true')
    page.locator('[data-periodo="30"]').click()
    pw.expect(page.locator(LIVRE)).to_have_attribute('aria-pressed', 'false')
    pw.expect(page.locator(f'{LIVRE} .rot')).to_have_text('Período')
    pw.expect(page.locator(dias_btn(30))).to_have_attribute('aria-pressed', 'true')
    pw.expect(page.locator('#atividadeSub')).to_contain_text('últimos 30 dias')


def test_voltar_para_7_30_90_depois_do_periodo_livre(painel):
    page, state = painel
    abrir_maquina(page)
    escolher_periodo(page, '2026-10-02', '2026-10-21', botao=LIVRE)
    pw.expect(page.locator(LIVRE)).to_have_attribute('aria-pressed', 'true')
    pedidos = gravar_eventos(page)
    page.locator(dias_btn(90)).click()
    pw.expect(page.locator('#atividadeSub')).to_contain_text('últimos 90 dias')
    pw.expect(page.locator(LIVRE)).to_have_attribute('aria-pressed', 'false')
    assert pedidos[-1].get('dias') == '180' and 'de' not in pedidos[-1]
