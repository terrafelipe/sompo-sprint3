"""Historico de operacao: 7/30/90 dias ou periodo livre (De/Ate) pelo calendario do painel (rede isolada)."""
from urllib.parse import parse_qs, urlparse

from tests.ajuda_calendario import escolher_periodo
from tests.test_painel import painel, nav, pw  # noqa: F401

SEG = '#historicoSeg'
LIVRE = f'{SEG} [data-periodo-livre]'

SESSAO = dict(sessao_id='s1', equipamento_id=1, equipamento_nome='Trator 1', operador_id=2, operador_nome='Ana',
              operador_excluido_em=None, inicio_em='2026-10-10T10:00:00Z', recebido_em='2026-10-10T10:00:00Z', status='encerrada')


def dias_btn(n):
    return f'{SEG} [data-dias="{n}"]'


def abrir_historico(page):
    """Abre o Historico e devolve a lista (viva) dos parametros de cada GET de /operacoes."""
    pedidos = []

    def ver(req):
        url = urlparse(req.url)
        if url.hostname == 'painel.test' and url.path == '/operacoes':
            pedidos.append({k: v[0] for k, v in parse_qs(url.query).items()})
    page.on('request', ver)
    page.route('**/operacoes?*', lambda r: r.fulfill(json={'dados': [SESSAO], 'total': 1}))
    nav(page, 'historico')
    pw.expect(page.locator('#listaHistorico')).to_contain_text('Trator 1')
    return pedidos


def test_botao_periodo_vem_depois_de_7_30_90_e_comeca_desligado(painel):
    page, state = painel
    abrir_historico(page)
    pw.expect(page.locator(f'{SEG} button')).to_have_text(['7 dias', '30 dias', '90 dias', 'calendar_monthPeríodo'])
    pw.expect(page.locator(dias_btn(7))).to_have_attribute('aria-pressed', 'true')
    pw.expect(page.locator(LIVRE)).to_have_attribute('aria-pressed', 'false')


def test_historico_7_30_90_continuam_pedindo_dias(painel):
    page, state = painel
    pedidos = abrir_historico(page)
    assert pedidos[-1]['dias'] == '7'
    page.locator(dias_btn(30)).click()
    pw.expect(page.locator(dias_btn(30))).to_have_attribute('aria-pressed', 'true')
    page.wait_for_load_state('networkidle')
    assert pedidos[-1]['dias'] == '30' and 'de' not in pedidos[-1]


def test_historico_periodo_livre_pede_de_ate_e_volta_para_a_pagina_1(painel):
    page, state = painel
    pedidos = abrir_historico(page)
    page.evaluate('historicoPagina = 1')
    escolher_periodo(page, '2026-10-02', '2026-10-21', botao=LIVRE)
    pw.expect(page.locator(f'{LIVRE} .rot')).to_have_text('2 out – 21 out')
    page.wait_for_load_state('networkidle')
    ped = pedidos[-1]
    assert (ped['de'], ped['ate']) == ('2026-10-02', '2026-10-21') and 'dias' not in ped
    assert page.evaluate('historicoPagina') == 0
    pw.expect(page.locator(LIVRE)).to_have_attribute('aria-pressed', 'true')
    for n in (7, 30, 90):
        pw.expect(page.locator(dias_btn(n))).to_have_attribute('aria-pressed', 'false')


def test_historico_periodo_livre_nao_mexe_nas_outras_secoes_e_o_global_nao_mexe_nele(painel):
    page, state = painel
    abrir_historico(page)
    escolher_periodo(page, '2026-10-02', '2026-10-21', botao=LIVRE)
    pw.expect(page.locator(LIVRE)).to_have_attribute('aria-pressed', 'true')
    assert page.evaluate('[alertasLivre, tempLivre]') == [None, None]
    page.evaluate("document.querySelector('[data-periodo=\"30\"]').click()")   # filtro global do topo
    page.wait_for_load_state('networkidle')
    pw.expect(page.locator(LIVRE)).to_have_attribute('aria-pressed', 'true')
    assert page.evaluate('historicoLivre') == {'de': '2026-10-02', 'ate': '2026-10-21'}


def test_voltar_para_7_30_90_depois_do_periodo_livre_do_historico(painel):
    page, state = painel
    pedidos = abrir_historico(page)
    escolher_periodo(page, '2026-10-02', '2026-10-21', botao=LIVRE)
    pw.expect(page.locator(LIVRE)).to_have_attribute('aria-pressed', 'true')
    page.locator(dias_btn(90)).click()
    pw.expect(page.locator(LIVRE)).to_have_attribute('aria-pressed', 'false')
    pw.expect(page.locator(f'{LIVRE} .rot')).to_have_text('Período')
    page.wait_for_load_state('networkidle')
    assert pedidos[-1]['dias'] == '90' and 'de' not in pedidos[-1]


def _sessoes(n):
    return [dict(SESSAO, sessao_id=f's{i}', recebido_em=f'2026-10-10T10:{i % 60:02d}:00Z') for i in range(n)]


def test_historico_avisa_quando_o_periodo_tem_mais_sessoes_do_que_vieram(painel):
    page, state = painel
    pedidos = []
    page.on('request', lambda r: pedidos.append(dict(parse_qs(urlparse(r.url).query))) if urlparse(r.url).path == '/operacoes' else None)
    page.route('**/operacoes?*', lambda r: r.fulfill(json={'dados': _sessoes(200), 'total': 450}))
    nav(page, 'historico')
    pw.expect(page.locator('#historicoAviso')).to_have_text('Mostrando as 200 sessões mais recentes de 450 no período. Escolha um período menor para ver as demais.')
    assert pedidos[-1]['limite'] == ['200']                      # o maximo que a API aceita (o padrao era 50)


def test_historico_sem_corte_nao_mostra_aviso(painel):
    page, state = painel
    page.route('**/operacoes?*', lambda r: r.fulfill(json={'dados': _sessoes(3), 'total': 3}))
    nav(page, 'historico')
    pw.expect(page.locator('#listaHistorico')).to_contain_text('Trator 1')
    pw.expect(page.locator('#historicoAviso')).to_be_hidden()
