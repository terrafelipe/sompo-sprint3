"""Medidor semicircular de risco: trilho cinza, arco na cor da classe e animacao ao aparecer."""
from tests.test_painel import painel, pw, nav  # noqa: F401

VERDE, AMARELO, VERMELHO = '#10b981', '#f59e0b', '#ba1a1a'


def _risco(page, furto, incendio):
    """Troca o /relatorio/risco do fixture; cada chamada devolve um gerado_em novo
    (como o backend sem IA faz), o que dispara o redesenho a cada refresh de 5 s."""
    atual = {'furto': furto, 'incendio': incendio, 'n': 0}

    def responder(r):
        atual['n'] += 1
        (sf, cf), (si, ci) = atual['furto'], atual['incendio']
        r.fulfill(json=dict(score_furto=sf, score_incendio=si, classificacao_furto=cf, classificacao_incendio=ci,
                            faixas={'medio': 34, 'alto': 67}, pontos_acumulados={'furto': sf, 'incendio': si},
                            detalhamento={}, origem_da_analise='prompt_apenas',
                            gerado_em=f'2026-09-24T12:00:{atual["n"]:02d}Z'))
    page.route('**/relatorio/risco*', responder)
    return atual


def _abrir(page):
    page.select_option('#equipamentoSel', '1')
    page.wait_for_selector('#gaugeFurto svg')
    page.wait_for_load_state('networkidle')


def _aparecer(page, sel='#gaugeFurto'):
    page.locator(sel).scroll_into_view_if_needed()


ANIMANDO = """sel => { const p = document.querySelector(sel + ' .arco-valor');
  return !!p && p.isConnected && p.getAnimations().some(a => a.playState === 'running'); }"""


def test_medidor_tem_trilho_cinza_unico_e_arco_na_cor_da_classe(painel):
    page, _ = painel
    _risco(page, (50, 'MEDIO'), (80, 'ALTO'))
    _abrir(page)
    for sel, cor in (('#gaugeFurto', AMARELO), ('#gaugeIncendio', VERMELHO)):
        estilos = page.eval_on_selector_all(f'{sel} svg path', 'ps => ps.map(p => p.getAttribute("style") || "")')
        assert not [e for e in estilos if '--v-faixa-' in e]
        assert len([e for e in estilos if '--v-borda-forte' in e]) == 1
        assert page.locator(f'{sel} .arco-valor').get_attribute('stroke') == cor
        # As marcas 34 e 67 continuam no medidor.
        pw.expect(page.locator(f'{sel} svg')).to_contain_text('34')
        pw.expect(page.locator(f'{sel} svg')).to_contain_text('67')


def test_medidor_baixo_verde_e_score_zero_so_cinza(painel):
    page, _ = painel
    _risco(page, (0, 'BAIXO'), (20, 'BAIXO'))
    _abrir(page)
    assert page.locator('#gaugeFurto .arco-valor').count() == 0
    assert page.locator('#gaugeFurto svg path').count() == 1
    assert page.locator('#gaugeIncendio .arco-valor').get_attribute('stroke') == VERDE


def test_medidor_anima_quando_aparece(painel):
    page, _ = painel
    _abrir(page)
    # Fora da tela: espera parado e o numero comeca em 0.
    assert not page.evaluate(ANIMANDO, '#gaugeFurto')
    assert page.locator('#gaugeFurto .num-gauge').text_content() == '0'
    _aparecer(page)
    page.wait_for_function(ANIMANDO, arg='#gaugeFurto', timeout=500)
    pw.expect(page.locator('#gaugeFurto .num-gauge')).to_have_text('5')


def test_refresh_antes_de_aparecer_nao_mata_a_animacao(painel):
    """Causa do "nao vejo animacao": o refresh de 5 s trocava o SVG antes de o usuario
    rolar ate o risco, e a animacao ficava presa nos paths antigos."""
    page, _ = painel
    _risco(page, (50, 'MEDIO'), (80, 'ALTO'))
    _abrir(page)
    page.evaluate("document.querySelector('#gaugeFurto svg').dataset.marca = 'antigo'")
    page.evaluate('carregarRisco()')   # mesmo score, gerado_em novo (refresh de 5 s)
    page.wait_for_load_state('networkidle')
    # Nada mudou no medidor: o SVG continua o mesmo.
    assert page.locator('#gaugeFurto svg').get_attribute('data-marca') == 'antigo'
    _aparecer(page)
    page.wait_for_function(ANIMANDO, arg='#gaugeFurto', timeout=500)


def test_score_novo_no_refresh_anima_do_valor_antigo(painel):
    page, _ = painel
    atual = _risco(page, (50, 'MEDIO'), (80, 'ALTO'))
    _abrir(page)
    _aparecer(page)
    pw.expect(page.locator('#gaugeFurto .num-gauge')).to_have_text('50')
    page.wait_for_function("() => !document.querySelector('#gaugeFurto .arco-valor').getAnimations().length")
    atual['furto'] = (90, 'ALTO')
    page.evaluate('carregarRisco()')
    page.wait_for_function(ANIMANDO, arg='#gaugeFurto', timeout=2000)
    inicio = page.evaluate("""() => document.querySelector('#gaugeFurto .arco-valor').getAnimations()[0]
        .effect.getKeyframes()[0].strokeDashoffset""")
    assert float(inicio) == 50   # parte de 50 (o valor antigo), nao de 0
    assert page.locator('#gaugeFurto .arco-valor').get_attribute('stroke') == VERMELHO
    pw.expect(page.locator('#gaugeFurto .num-gauge')).to_have_text('90')
