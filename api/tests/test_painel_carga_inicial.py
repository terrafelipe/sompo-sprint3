"""Carga inicial enxuta: o Inicio nao espera cadastros de outras telas nem repete /fazendas."""
from urllib.parse import urlparse

from tests.test_painel import painel, pw, nav  # noqa: F401


def _caminhos(pedidos):
    return [urlparse(u).path for u in pedidos]


def test_inicio_nao_carrega_cadastros_nem_repete_fazendas(painel):
    page, state = painel
    pedidos = []
    page.on('request', lambda r: pedidos.append(r.url) if 'painel.test' in r.url else None)
    page.reload()
    pw.expect(page.locator('#listaInicio .fazenda-card')).to_have_count(2)
    page.wait_for_timeout(600)
    caminhos = _caminhos(pedidos)
    assert caminhos.count('/fazendas') == 1, caminhos
    # Fazendas e resumos do Inicio numa chamada so, sem um /fazendas/<id>/resumo por fazenda.
    assert caminhos.count('/carteira') == 1, caminhos
    assert not [c for c in caminhos if c.endswith('/resumo')], caminhos
    for fora in ('/clientes', '/usuarios', '/operadores'):
        assert fora not in caminhos, (fora, caminhos)
    assert not state['errors']


def test_cadastros_carregam_ao_abrir_a_tela(painel):
    page, state = painel
    pedidos = []
    page.on('request', lambda r: pedidos.append(r.url) if 'painel.test' in r.url else None)
    nav(page, 'fazendas')
    pw.expect(page.locator('#listaFazendas [data-linha]')).to_have_count(2)
    page.wait_for_timeout(300)
    assert '/clientes' in _caminhos(pedidos)          # o select de cliente do formulario de fazenda
    nav(page, 'usuarios')
    pw.expect(page.locator('#listaUsuarios [data-linha]')).to_have_count(1)
    assert page.locator('#usFazenda option').count() >= 2   # select de fazenda do formulario de usuario
    nav(page, 'operadores')
    pw.expect(page.locator('#listaOperadores [data-linha]')).to_have_count(1)
    assert not state['errors']
