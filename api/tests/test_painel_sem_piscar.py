"""Graficos preservam o conteudo no refresh e sinalizam somente um contexto novo."""
import re
import time
from datetime import datetime, timezone

import pytest

from tests.test_painel import painel, pw, nav  # noqa: F401


CASOS = [
    pytest.param('/eventos', ['graficoAtividade', 'graficoTipos'], 'eventos', id='alertas'),
    pytest.param('/resumo', ['graficoTempDia'], 'temperatura', id='temperatura'),
    pytest.param('/resumo', ['graficoTempDia'], 'vazio', id='temperatura-vazia'),
]


def resposta(caso):
    if caso == 'eventos':
        return {'dados': [dict(id=1, tipo='furto_capo', severidade=2,
                               criado_em=datetime.now(timezone.utc).isoformat())]}
    if caso == 'temperatura':
        return {'dados': [dict(dia='2026-09-18', amostras=35, temp_escape_max=61.0,
                               temp_escape_media=38.2, temp_ambiente_media=25.1)]}
    return {'dados': []}


def esperar_retida(page, state):
    limite = time.monotonic() + 5
    while not state['held'] and time.monotonic() < limite:
        page.wait_for_timeout(10)
    assert state['held'], 'O ciclo deveria buscar os dados do cartao'


def liberar(page, state, dados):
    esperar_retida(page, state)
    # Guarda a carga ainda pendente: chamar carregarTudo depois de liberar pode
    # iniciar outro refresh e prender uma nova requisicao no proprio teste.
    page.evaluate('() => { window.__cargaTeste = carregarTudo(); }')
    for rota in state['held']:
        rota.fulfill(json=dados)
    state['held'].clear()
    page.evaluate('window.__cargaTeste')


@pytest.mark.parametrize('rota,cartoes,caso', CASOS)
def test_refresh_preserva_cartoes_e_periodo_novo_mostra_carga(painel, rota, cartoes, caso):
    page, state = painel
    page.clock.install()
    nav(page, 'visao')
    state['hold'] = rota
    page.select_option('#equipamentoSel', '1')
    for id in cartoes:
        pw.expect(page.locator('#' + id)).to_have_class(re.compile(r'viz-carregando'))
    dados = resposta(caso)
    liberar(page, state, dados)
    for id in cartoes:
        pw.expect(page.locator('#' + id)).not_to_have_class(re.compile(r'viz-carregando'))
    page.evaluate('ids => { window.__conteudo = ids.map(id => document.getElementById(id).firstChild); }', cartoes)

    # Exercita o intervalo real de 5 s, com a resposta ainda em voo.
    page.clock.fast_forward(5100)
    esperar_retida(page, state)
    for id in cartoes:
        assert not page.locator('#' + id).evaluate("e => e.classList.contains('viz-carregando')")
    liberar(page, state, dados)
    assert page.evaluate('ids => ids.every((id, i) => document.getElementById(id).firstChild === window.__conteudo[i])', cartoes)

    page.locator('[data-periodo="30"]').click()
    esperar_retida(page, state)
    for id in cartoes:
        pw.expect(page.locator('#' + id)).to_have_class(re.compile(r'viz-carregando'))
    liberar(page, state, dados)
    for id in cartoes:
        pw.expect(page.locator('#' + id)).not_to_have_class(re.compile(r'viz-carregando'))


@pytest.mark.parametrize('rota,cartoes,caso', CASOS[:2])
def test_trocar_maquina_mostra_nova_carga(painel, rota, cartoes, caso):
    page, state = painel
    nav(page, 'visao')
    page.select_option('#equipamentoSel', '1')
    page.evaluate('carregarTudo()')
    page.select_option('#fazendaSel', '2')
    pw.expect(page.locator('#equipamentoSel option')).to_have_count(2)
    state['hold'] = rota
    page.select_option('#equipamentoSel', '2')
    esperar_retida(page, state)
    for id in cartoes:
        pw.expect(page.locator('#' + id)).to_have_class(re.compile(r'viz-carregando'))
    liberar(page, state, resposta(caso))
