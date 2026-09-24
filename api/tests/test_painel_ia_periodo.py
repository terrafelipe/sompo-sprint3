"""Trocar o periodo global pede o texto da IA de novo (com o dias novo); o refresh de 5 s nao."""
from tests.test_painel import painel, pw, nav  # noqa: F401
from tests.test_painel_ia import TEXTO_IA, _rotas


def _ticks_de_5s(page, estado, ciclos=3):
    for _ in range(ciclos):
        # Um tick pode cair sobre a carga anterior ainda pendente: o ciclo so conta com um ia=0 novo.
        antes = estado['rapidas']
        for _tick in range(4):
            page.clock.run_for(5100)
            page.wait_for_load_state('networkidle')
            if estado['rapidas'] > antes:
                break
        assert estado['rapidas'] > antes


def test_trocar_periodo_pede_a_ia_de_novo_e_o_refresh_nao(painel):
    page, state = painel
    nav(page, 'visao')
    estado = _rotas(page, segurar=False)
    page.clock.install()
    page.select_option('#equipamentoSel', '1')
    pw.expect(page.locator('#riscoResumo')).to_have_text(TEXTO_IA)
    page.evaluate("pausar('aba'); retomar()")   # religa o relogio de 5 s sob o relogio falso
    page.wait_for_load_state('networkidle')
    assert len(estado['ia']) == 1 and 'dias=7' in estado['ia'][0]

    with page.expect_request(lambda req: '/relatorio/risco?' in req.url and 'dias=90' in req.url
                             and 'ia=0' not in req.url):
        page.locator('[data-periodo="90"]:visible').first.click()
    pw.expect(page.locator('#riscoResumo')).to_have_text(TEXTO_IA)
    assert len(estado['ia']) == 2 and 'dias=90' in estado['ia'][1] and 'ia=0' not in estado['ia'][1]

    # Refresh de 5 s no mesmo periodo: so o ia=0 se repete, a IA nao e pedida de novo.
    _ticks_de_5s(page, estado)
    assert len(estado['ia']) == 2
    assert not state['errors']
