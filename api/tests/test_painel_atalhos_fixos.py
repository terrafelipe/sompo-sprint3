"""Atalhos do Painel da máquina (Resumo, Alertas, Risco, Telemetria) ficam fixos ao rolar."""
from tests.test_painel import painel, pw, nav  # noqa: F401

CAIXA = "id => { const r = document.getElementById(id).getBoundingClientRect(); return {top: r.top, bottom: r.bottom}; }"


def _abrir_painel(page):
    nav(page, 'visao')
    page.select_option('#equipamentoSel', '1')
    pw.expect(page.locator('#atalhosPainel')).to_be_visible()


def _parado(page):
    # Espera a rolagem suave começar e terminar: a posição não muda por 250 ms.
    for _ in range(20):
        if page.evaluate("""() => new Promise(ok => { const y = scrollY;
                setTimeout(() => ok(scrollY === y), 250); })"""):
            return
    raise AssertionError('a rolagem não parou')


def test_atalhos_ficam_visiveis_ao_rolar_ate_a_telemetria(painel):
    page, state = painel
    _abrir_painel(page)
    page.evaluate("document.getElementById('secTelemetria').scrollIntoView({block: 'start'})")
    _parado(page)
    assert page.evaluate('scrollY') > 300, 'o painel precisa rolar para o teste valer'
    barra = page.evaluate(CAIXA, 'atalhosPainel')
    assert 0 <= barra['top'] <= 120, barra
    pw.expect(page.locator('#atalhosPainel [data-ir="secResumo"]')).to_be_in_viewport()
    # A parte de destino também não fica embaixo da barra.
    assert page.evaluate(CAIXA, 'secTelemetria')['top'] >= barra['bottom'] - 1
    assert not state['errors']


def test_clicar_num_atalho_mostra_a_parte_abaixo_da_barra(painel):
    page, state = painel
    _abrir_painel(page)
    page.locator('#atalhosPainel [data-ir="secTelemetria"]').click()
    pw.expect(page.locator('#atalhosPainel [data-ir="secTelemetria"]')).to_have_attribute('aria-pressed', 'true')
    _parado(page)
    barra = page.evaluate(CAIXA, 'atalhosPainel')
    assert 0 <= barra['top'] <= 120, barra
    alvo = page.evaluate(CAIXA, 'secTelemetria')
    assert barra['bottom'] - 1 <= alvo['top'] <= barra['bottom'] + 40, (barra, alvo)

    page.locator('#atalhosPainel [data-ir="secResumo"]').click()
    _parado(page)
    barra = page.evaluate(CAIXA, 'atalhosPainel')
    resumo = page.evaluate(CAIXA, 'secResumo')
    assert resumo['top'] >= barra['bottom'] - 1, (barra, resumo)
    pw.expect(page.locator('#secResumo')).to_be_in_viewport()
    assert not state['errors']


def test_atalhos_ficam_abaixo_do_aviso_de_pausa(painel):
    page, state = painel
    _abrir_painel(page)
    page.evaluate("document.getElementById('avisoPausa').hidden = false")
    page.evaluate("document.getElementById('secTelemetria').scrollIntoView({block: 'start'})")
    _parado(page)
    page.wait_for_function("""() => document.getElementById('atalhosPainel').getBoundingClientRect().top
        >= document.getElementById('avisoPausa').getBoundingClientRect().bottom - 1""")
    page.evaluate("document.getElementById('avisoPausa').hidden = true")
    page.wait_for_function("() => document.getElementById('atalhosPainel').getBoundingClientRect().top <= 60")


def test_painel_sem_rolagem_horizontal(painel):
    page, state = painel
    _abrir_painel(page)
    for id in ('secResumo', 'secTelemetria'):
        page.evaluate("id => document.getElementById(id).scrollIntoView({block: 'start'})", id)
        _parado(page)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    # Nada rola de lado: nem a página, nem o conteúdo.
    page.evaluate('scrollBy(500, 0)')
    assert page.evaluate('scrollX') == 0
    assert page.evaluate("document.getElementById('conteudo').scrollLeft") == 0
