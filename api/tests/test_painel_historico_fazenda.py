"""Sem fazenda (Sompo), Operadores e Historico pedem a fazenda; o historico marca operador excluido."""
from tests.test_painel import painel, pw, nav  # noqa: F401

SESSAO = dict(sessao_id='s1', equipamento_id=1, equipamento_nome='Trator 1', operador_id=2, operador_nome='Gustavo Pugas',
              operador_excluido_em='2026-09-24T13:14:03-03:00', inicio_em='2026-09-18T10:00:00Z',
              recebido_em='2026-09-18T10:00:00Z', status='encerrada')


def _sem_fazenda(page):
    page.select_option('#fazendaSel', '')
    page.wait_for_load_state('networkidle')


def test_sem_fazenda_operadores_e_historico_pedem_a_fazenda(painel):
    page, state = painel
    pedidos = []
    page.on('request', lambda r: pedidos.append(r.url))
    _sem_fazenda(page)
    for view, lista in [('operadores', '#listaOperadores'), ('historico', '#listaHistorico')]:
        antes = len(pedidos)
        nav(page, view)
        pw.expect(page.locator(lista)).to_contain_text('Nenhuma fazenda selecionada')
        page.wait_for_load_state('networkidle')
        assert not [u for u in pedidos[antes:] if '/operadores' in u or '/operacoes' in u], view


def test_historico_marca_operador_excluido_com_dia_e_hora(painel):
    page, state = painel
    page.route('**/operacoes?*', lambda r: r.fulfill(json={'dados': [SESSAO], 'total': 1}))
    nav(page, 'historico')
    pw.expect(page.locator('#listaHistorico')).to_contain_text('Operador excluído em 24/09/2026 às 13:14')
    page.locator('#listaHistorico [data-ses]').first.click()
    pw.expect(page.locator('#detCorpo')).to_contain_text('Excluído em 24/09/2026 às 13:14')
