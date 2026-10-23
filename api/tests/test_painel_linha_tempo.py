"""Regressao da apresentacao original da linha do tempo, em quatro trilhas."""
import os
from pathlib import Path

import pytest

from tests.ajuda_linha_tempo import resposta_exemplo, servir
from tests.test_painel import nav, painel, pw  # noqa: F401


def test_linha_do_tempo_volta_as_quatro_trilhas(painel):
    page, _ = painel
    servir(page)
    nav(page, 'visao')
    page.evaluate("pausar('manual')")
    page.select_option('#equipamentoSel', '1')
    svg = page.locator('#linhaTempo svg')
    pw.expect(svg).to_be_visible()
    for nome in ('Máquina', 'Risco', 'Crachá', 'Alertas'):
        pw.expect(svg.locator('text', has_text=nome)).to_have_count(1)
    pw.expect(page.locator('#linhaTempoSub')).to_contain_text('dessas 24 h')
    pw.expect(page.locator('#linhaTempoSeg')).to_have_count(0)
    pw.expect(page.locator('#ltLista')).to_have_count(0)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    destino = os.getenv('SOMPO_TEST_ARTIFACTS')
    if destino:
        Path(destino).mkdir(parents=True, exist_ok=True)
        page.locator('[data-section="linhaTempo"]').scroll_into_view_if_needed()
        page.wait_for_function("() => document.querySelector('#linhaTempo svg').getAnimations().every(a => a.playState === 'finished')")
        page.locator('[data-section="linhaTempo"]').screenshot(
            path=str(Path(destino) / f'linha-tempo-{page.viewport_size["width"]}.png'))


def _abrir(page, resposta=None):
    st = servir(page, resposta)
    nav(page, 'visao')
    page.evaluate("pausar('manual')")
    page.select_option('#equipamentoSel', '1')
    pw.expect(page.locator('#linhaTempo svg')).to_be_visible()
    return st


def test_detalhe_mostra_motor_risco_cracha_e_alertas_da_faixa(painel):
    page, _ = painel
    d = resposta_exemplo()
    faixa = 134  # 09:30-09:35: motor ligado, Joao e um alarme critico.
    d['faixas'][faixa]['risco'] = 'CRITICO'
    _abrir(page, d)
    page.locator('#linhaTempo .viz-hit').nth(faixa).dispatch_event('pointermove', {'clientX': 200, 'clientY': 300})
    tip = page.locator('#vizTip')
    pw.expect(tip).to_contain_text('Motor ligado')
    pw.expect(tip).to_contain_text('CRÍTICO')
    pw.expect(tip).to_contain_text('João Silva')
    pw.expect(tip).to_contain_text('1 (Escape crítico)')
    assert page.locator('#linhaTempo circle').count() == 9  # sem os eventos de rotina


def test_detalhe_de_faixa_sem_leituras(painel):
    page, _ = painel
    _abrir(page)
    page.locator('#linhaTempo .viz-hit').nth(236).dispatch_event('pointermove', {'clientX': 200, 'clientY': 300})
    pw.expect(page.locator('#vizTip')).to_contain_text('Sem leituras')
    pw.expect(page.locator('#vizTip')).to_contain_text('Nenhuma sessão')


def test_sessao_interrompida_sem_fim_nao_pinta_o_dia_inteiro(painel):
    page, _ = painel
    d = resposta_exemplo()
    d['sessoes'] = [{'inicio': '2026-10-22T09:00:00-03:00', 'fim': None,
                     'status': 'interrompida', 'operador_nome': 'Ana'}]
    _abrir(page, d)
    barra = page.locator('#linhaTempo svg rect[y="54"]').last
    assert float(barra.get_attribute('width')) == 2


def test_sessao_aberta_vai_ate_a_ultima_leitura(painel):
    page, _ = painel
    d = resposta_exemplo()
    d['sessoes'] = [{'inicio': d['janela']['inicio'], 'fim': None,
                     'status': 'aberta', 'operador_nome': 'Ana'}]
    _abrir(page, d)
    barras = page.locator('#linhaTempo svg rect[y="54"]')
    assert float(barras.nth(0).get_attribute('width')) == float(barras.nth(1).get_attribute('width'))


def test_atualiza_a_cada_60_segundos_sem_redesenhar_dados_iguais(painel):
    page, _ = painel
    st = _abrir(page)
    n = len(st['urls'])
    page.evaluate("document.querySelector('#linhaTempo svg').dataset.original = 'sim'; carregarLinhaTempo()")
    assert len(st['urls']) == n
    page.evaluate('linhaTempoEm -= 61000; carregarLinhaTempo()')
    assert len(st['urls']) == n + 1
    pw.expect(page.locator('#linhaTempo svg')).to_have_attribute('data-original', 'sim')
    assert all('horas=24' in url for url in st['urls'])


@pytest.mark.parametrize('resposta, mensagem', [
    ({'janela': None, 'faixas': []}, 'Sem leituras desta máquina'),
    ((502, {'erro': 'falha_na_consulta'}), 'Linha do tempo indisponível'),
])
def test_erro_e_vazio_nao_repetem_consulta_a_cada_ciclo(painel, resposta, mensagem):
    page, _ = painel
    st = servir(page, resposta)
    nav(page, 'visao')
    page.evaluate("pausar('manual')")
    page.select_option('#equipamentoSel', '1')
    pw.expect(page.locator('#linhaTempo')).to_contain_text(mensagem)
    n = len(st['urls'])
    page.evaluate('carregarLinhaTempo(); carregarLinhaTempo()')
    assert len(st['urls']) == n


def test_tentar_novamente_recupera_a_linha_do_tempo(painel):
    page, _ = painel
    st = servir(page, (502, {'erro': 'falha_na_consulta'}))
    nav(page, 'visao')
    page.evaluate("pausar('manual')")
    page.select_option('#equipamentoSel', '1')
    pw.expect(page.locator('#linhaTempo')).to_contain_text('Linha do tempo indisponível')
    page.unroute('**/telemetria/linha-do-tempo*')
    servir(page)
    page.locator('#linhaTempo [data-tentar]').click()
    pw.expect(page.locator('#linhaTempo svg')).to_be_visible()
    assert len(st['urls']) == 1


def test_trocar_maquina_descarta_resposta_atrasada(painel):
    page, _ = painel
    _abrir(page)
    presas = []
    page.unroute('**/telemetria/linha-do-tempo*')
    page.route('**/telemetria/linha-do-tempo*', lambda r: presas.append(r))
    with page.expect_request('**/telemetria/linha-do-tempo*'):
        page.evaluate('carregarLinhaTempo(true); undefined')
    page.select_option('#fazendaSel', '2')
    page.unroute('**/telemetria/linha-do-tempo*')
    servir(page, {'janela': None, 'faixas': []})
    page.select_option('#equipamentoSel', '2')
    pw.expect(page.locator('#linhaTempo')).to_contain_text('Sem leituras desta máquina')
    presas[0].fulfill(json=resposta_exemplo())
    page.wait_for_load_state('networkidle')
    pw.expect(page.locator('#linhaTempo')).to_contain_text('Sem leituras desta máquina')
    pw.expect(page.locator('#linhaTempo svg')).to_have_count(0)


def test_redesenho_e_tema_escuro_preservam_as_trilhas(painel):
    page, _ = painel
    _abrir(page)
    page.evaluate("document.documentElement.dataset.tema = 'escuro'; desenharLinhaTempo()")
    pw.expect(page.locator('#linhaTempo svg')).to_be_visible()
    assert page.locator('#linhaTempo svg .viz-hit').count() == 288
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
