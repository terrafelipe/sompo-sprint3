"""Escolher a maquina no seletor do topo em Operadores/Historico fica na aba e filtra por ela."""
import re
from urllib.parse import parse_qs, urlparse

from tests.test_painel import painel, pw, nav  # noqa: F401

SESSOES = {
    '1': dict(sessao_id='s1', equipamento_id=1, equipamento_nome='Trator 1', operador_id=7, operador_nome='Ana',
              inicio_em='2026-09-18T10:00:00Z', recebido_em='2026-09-18T10:00:00Z'),
    '2': dict(sessao_id='s2', equipamento_id=2, equipamento_nome='Trator 2', operador_id=8, operador_nome='Bruno',
              inicio_em='2026-09-18T11:00:00Z', recebido_em='2026-09-18T11:00:00Z'),
}


def _historico(page):
    pedidos = []

    def responder(r):
        q = parse_qs(urlparse(r.request.url).query)
        pedidos.append(q)
        eq = q.get('equipamento', [None])[0]
        dados = [SESSOES[eq]] if eq else list(SESSOES.values())
        r.fulfill(json={'dados': dados, 'total': len(dados)})
    page.route('**/operacoes?*', responder)
    return pedidos


def _operadores(page):
    page.route(re.compile(r'/operadores(\?|$)'), lambda r: r.fulfill(json={'dados': [
        dict(id_operador=7, nome='Ana', uid='01020304', ativo=True),
        dict(id_operador=8, nome='Bruno', uid='05060708', ativo=True)]}))
    page.route('**/equipamentos/1/operadores', lambda r: r.fulfill(json={'dados': [
        dict(equipamento_id=1, operador_id=7, ativo=True)]}))


def test_historico_fica_na_aba_e_filtra_pela_maquina(painel):
    page, state = painel
    pedidos = _historico(page)
    nav(page, 'historico')
    pw.expect(page.locator('#listaHistorico')).to_contain_text('Bruno')

    page.select_option('#equipamentoSel', '1')
    pw.expect(page.locator('#tituloView')).to_have_text('Histórico')
    filtro = page.locator('[data-section="historico"] [data-filtro-maquina]')
    pw.expect(filtro).to_be_visible()
    pw.expect(filtro).to_contain_text('Trator 1')
    pw.expect(page.locator('#listaHistorico')).not_to_contain_text('Bruno')
    assert pedidos[-1].get('equipamento') == ['1']

    filtro.locator('[data-limpar-maquina]').click()
    pw.expect(page.locator('#tituloView')).to_have_text('Histórico')
    pw.expect(filtro).to_be_hidden()
    pw.expect(page.locator('#listaHistorico')).to_contain_text('Bruno')
    assert 'equipamento' not in pedidos[-1]


def test_operadores_fica_na_aba_e_mostra_so_os_autorizados(painel):
    page, state = painel
    _operadores(page)
    nav(page, 'operadores')
    pw.expect(page.locator('#listaOperadores')).to_contain_text('Bruno')

    page.select_option('#equipamentoSel', '1')
    pw.expect(page.locator('#tituloView')).to_have_text('Operadores')
    filtro = page.locator('[data-section="operadores"] [data-filtro-maquina]')
    pw.expect(filtro).to_contain_text('Trator 1')
    pw.expect(page.locator('#listaOperadores')).to_contain_text('Ana')
    pw.expect(page.locator('#listaOperadores')).not_to_contain_text('Bruno')

    # O detalhe continua abrindo o operador certo (o indice aponta para a lista completa).
    page.locator('#listaOperadores [data-op]').first.click()
    pw.expect(page.locator('#detTitulo')).to_contain_text('Ana')
    page.keyboard.press('Escape')

    filtro.locator('[data-limpar-maquina]').click()
    pw.expect(filtro).to_be_hidden()
    pw.expect(page.locator('#listaOperadores')).to_contain_text('Bruno')


def test_voltar_o_seletor_para_vazio_limpa_o_filtro_na_hora(painel):
    page, state = painel
    pedidos = _historico(page)
    nav(page, 'historico')
    page.select_option('#equipamentoSel', '1')
    filtro = page.locator('[data-section="historico"] [data-filtro-maquina]')
    pw.expect(filtro).to_be_visible()
    pw.expect(page.locator('#listaHistorico')).not_to_contain_text('Bruno')

    page.evaluate("pausar('aba')")   # sem o refresh de 5 s: a limpeza tem de ser imediata
    page.select_option('#equipamentoSel', '')
    pw.expect(filtro).to_be_hidden()
    pw.expect(page.locator('#listaHistorico')).to_contain_text('Bruno')
    assert 'equipamento' not in pedidos[-1]


def test_na_aba_maquinas_escolher_maquina_continua_abrindo_o_painel(painel):
    page, state = painel
    nav(page, 'maquinas')
    page.select_option('#equipamentoSel', '1')
    pw.expect(page.locator('#tituloView')).to_have_text('Painel da máquina')
