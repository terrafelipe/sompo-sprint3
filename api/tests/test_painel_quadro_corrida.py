"""Quadro de ocorrências: respostas fora de ordem e falha no refresh não desfazem o arraste."""
import time

from tests.test_painel import painel, pw, nav, arrastar, _ocorrencia  # noqa: F401


def _quadro(page, state):
    state['ocorrencias'] = [_ocorrencia(1, 'Capô aberto', 'aberta'), _ocorrencia(2, 'Cerca', 'em_verificacao')]
    nav(page, 'ocorrencias')
    pw.expect(page.locator('[data-coluna="aberta"] [data-oc]')).to_have_count(1)


def _esperar_retidas(page, state, n):
    limite = time.monotonic() + 10
    while len(state['held']) < n and time.monotonic() < limite:
        page.wait_for_timeout(20)
    assert len(state['held']) >= n


def test_leitura_antiga_que_chega_depois_nao_devolve_o_cartao(painel):
    page, state = painel
    _quadro(page, state)
    antigas = {'dados': [dict(o) for o in state['ocorrencias']]}   # foto antes de mover
    state['hold'] = '/ocorrencias'
    page.evaluate('() => { carregarOcorrencias(); }')              # refresh sai antes do PATCH
    _esperar_retidas(page, state, 1)
    arrastar(page, '[data-oc="1"]', '[data-lista-oc="em_verificacao"]')
    # PATCH concluído (movendoOc volta a 0) e a recarga de confirmação já saiu.
    limite = time.monotonic() + 10
    while (('/ocorrencias/1', {'status': 'em_verificacao'}) not in state['posts']
           or page.evaluate('movendoOc')) and time.monotonic() < limite:
        page.wait_for_timeout(20)
    _esperar_retidas(page, state, 2)
    page.wait_for_timeout(200)
    antiga, *novas = state['held']
    state['hold'] = None
    for r in novas:
        r.fulfill(json={'dados': state['ocorrencias']})
    antiga.fulfill(json=antigas)                                   # chega por último, com o status velho
    page.wait_for_timeout(300)
    # Checagem imediata: o expect com repeticao esperaria o proximo refresh consertar a tela.
    assert page.locator('[data-lista-oc="em_verificacao"] [data-oc="1"]').count() == 1
    assert not state['errors']


def test_falha_no_refresh_durante_o_arraste_nao_apaga_o_quadro(painel):
    page, state = painel
    _quadro(page, state)
    pw.expect(page.locator('[data-lista-oc="em_verificacao"]')).to_have_attribute('data-arrastavel', '1')
    a = page.locator('[data-oc="1"]').bounding_box()
    page.mouse.move(a['x'] + a['width'] / 2, a['y'] + a['height'] / 2)
    page.mouse.down()
    page.mouse.move(a['x'] + a['width'] / 2 + 12, a['y'] + a['height'] / 2 + 12, steps=4)
    page.mouse.move(a['x'] + a['width'] / 2 + 40, a['y'] + a['height'] / 2 + 40, steps=8)
    assert page.evaluate('arrastandoOc')
    page.route('**/ocorrencias', lambda r: r.fulfill(status=502, json={'erro': 'indisponivel'})
               if r.request.method == 'GET' else r.fallback())
    page.evaluate('carregarOcorrencias()')
    assert page.locator('#quadroOcorrencias [data-oc]').count() == 2
    page.mouse.up()
