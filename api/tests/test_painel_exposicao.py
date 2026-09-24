"""Exposicao financeira: tooltip com numero de maquinas, cartao sem valor e entrada sem reanimar."""
import os
import re
from pathlib import Path

from tests.test_painel import painel, pw, nav  # noqa: F401

# Fazenda 1: Trator 1 com score 80 (risco alto); Fazenda 2: Trator 2 com score 10.
SCORES = {1: dict(score_furto=80, score_incendio=0), 2: dict(score_furto=10, score_incendio=0)}


def _abrir(page, state, valor=None):
    state['scores'] = SCORES
    state['valor'] = valor if valor is not None else {2: '50000'}
    nav(page, 'exposicao')
    pw.expect(page.locator('#listaExposicao [data-linha]')).to_have_count(2)
    page.wait_for_load_state('networkidle')


def _sobre(page, seg):
    """Rola ate o segmento e espera o evento de scroll (que fecha o tooltip) antes do hover."""
    # No centro: longe do cabecalho fixo, o hover nao precisa rolar de novo.
    seg.evaluate("el => el.scrollIntoView({block: 'center'})")
    page.evaluate('new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')
    # A animacao de entrada comeca quando o segmento aparece: espera a barra crescer.
    seg.evaluate("el => Promise.race([Promise.all(el.getAnimations().map(a => a.finished)), new Promise(r => setTimeout(r, 2000))])")
    seg.hover()


def _print(page, nome):
    destino = os.getenv('SOMPO_TEST_ARTIFACTS')
    if destino:
        page.wait_for_timeout(250)   # fim do fade do tooltip
        Path(destino).mkdir(parents=True, exist_ok=True)
        tema = page.evaluate('document.documentElement.dataset.tema')
        page.screenshot(path=str(Path(destino) / f'exposicao-{nome}-{tema}-{page.viewport_size["width"]}.png'))


def test_hover_na_proporcao_mostra_quantas_maquinas(painel):
    page, state = painel
    _abrir(page, state)
    seg = page.locator('#listaExposicao [data-linha]').nth(0).locator('[data-barra="alto"]')
    _sobre(page, seg)
    tip = page.locator('#vizTip')
    pw.expect(tip).to_have_class(re.compile(r'\bvisivel\b'))
    pw.expect(tip).to_contain_text('Fazenda 1')
    pw.expect(tip).to_contain_text('Em risco alto: 1 máquina')
    pw.expect(tip).to_contain_text('R$ 150.000,50')
    _print(page, 'proporcao')
    # O refresh de 5 s com os mesmos dados nao redesenha a tabela (o tooltip continua aberto).
    page.evaluate('carregarExposicao()')
    page.wait_for_load_state('networkidle')
    pw.expect(tip).to_have_class(re.compile(r'\bvisivel\b'))
    page.mouse.move(2, 2)
    pw.expect(tip).not_to_have_class(re.compile(r'\bvisivel\b'))
    # Segmento azul: demais maquinas.
    seg2 = page.locator('#listaExposicao [data-linha]').nth(1).locator('[data-barra="demais"]')
    _sobre(page, seg2)
    pw.expect(tip).to_contain_text('Fazenda 2')
    pw.expect(tip).to_contain_text('Demais máquinas: 1 máquina')
    pw.expect(tip).to_contain_text('R$ 50.000,00')


def test_toque_na_proporcao_abre_e_scroll_fecha(painel):
    page, state = painel
    _abrir(page, state)
    seg = page.locator('#listaExposicao [data-linha]').nth(0).locator('[data-barra="alto"]')
    seg.scroll_into_view_if_needed()
    page.evaluate('new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')
    seg.evaluate("""el => { const r = el.getBoundingClientRect();
        el.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, pointerType: 'touch', clientX: r.x + 2, clientY: r.y + 2})); }""")
    tip = page.locator('#vizTip')
    pw.expect(tip).to_have_class(re.compile(r'\bvisivel\b'))
    pw.expect(tip).to_contain_text('1 máquina')
    page.evaluate("window.dispatchEvent(new Event('scroll'))")
    pw.expect(tip).not_to_have_class(re.compile(r'\bvisivel\b'))


def test_hover_na_faixa_mostra_maquinas_valor_e_percentual(painel):
    page, state = painel
    _abrir(page, state)
    seg = page.locator('#xFaixas [data-faixa="ALTO"]')
    _sobre(page, seg)
    tip = page.locator('#vizTip')
    pw.expect(tip).to_have_class(re.compile(r'\bvisivel\b'))
    pw.expect(tip).to_contain_text('Risco alto')
    pw.expect(tip).to_contain_text('1 máquina')
    pw.expect(tip).to_contain_text('R$ 150.000,50')
    pw.expect(tip).to_contain_text('75%')
    box = tip.bounding_box()   # dentro da tela, inclusive em 390 px
    assert box['x'] >= 0 and box['x'] + box['width'] <= page.viewport_size['width']
    _print(page, 'faixa')
    _sobre(page, page.locator('#xFaixas [data-faixa="BAIXO"]'))
    pw.expect(tip).to_contain_text('Risco baixo')
    pw.expect(tip).to_contain_text('25%')
    # O refresh com os mesmos dados nao reescreve as faixas.
    page.evaluate("document.querySelector('#xFaixas [data-faixa]').dataset.marca = '1'")
    page.evaluate('carregarExposicao()')
    page.wait_for_load_state('networkidle')
    assert page.evaluate("document.querySelector('#xFaixas [data-faixa]').dataset.marca") == '1'


def test_prints_no_tema_escuro(painel):
    page, state = painel
    page.evaluate("aplicarTema('escuro')")
    _abrir(page, state)
    for sel, nome in [('#listaExposicao [data-barra="alto"]', 'proporcao'), ('#xFaixas [data-faixa="ALTO"]', 'faixa')]:
        seg = page.locator(sel).first
        _sobre(page, seg)
        pw.expect(page.locator('#vizTip')).to_have_class(re.compile(r'\bvisivel\b'))
        _print(page, nome)


def test_cartao_sem_valor_explica_e_lista_as_maquinas(painel):
    page, state = painel
    _abrir(page, state, valor={1: None})
    card = page.locator('#xSemValor').locator('xpath=..')
    pw.expect(card).to_contain_text('Máquinas sem valor segurado')
    pw.expect(page.locator('#xSemValor')).to_have_text('1')
    pw.expect(page.locator('#xSemValorSub')).to_contain_text('Ficam fora das somas acima')
    pw.expect(page.locator('#xSemValorSub')).to_contain_text('Informe o valor em Máquinas, no botão Editar.')
    pw.expect(page.locator('#xSemValor')).to_have_attribute('title', re.compile('Trator 1'))


def test_cartao_sem_valor_com_todas_informadas(painel):
    page, state = painel
    _abrir(page, state)
    pw.expect(page.locator('#xSemValor')).to_have_text('0')
    pw.expect(page.locator('#xSemValorSub')).to_have_text('Todas as máquinas têm valor segurado no cadastro.')


CONTAR_ANIMS = """() => { window._animsExpo = 0; const orig = Element.prototype.animate;
    Element.prototype.animate = function(...a){
      if(this.matches('#xFaixas [data-faixa], #listaExposicao [data-barra], #xTotal, #xAlto')) window._animsExpo++;
      return orig.apply(this, a); }; }"""
TOCANDO = """() => [...document.querySelectorAll('#xFaixas [data-faixa], #listaExposicao [data-barra]')]
    .filter(el => el.getAnimations().some(a => a.playState === 'running')).length"""


def _abrir_guardando_carteira(page, state):
    """Abre a Exposicao e devolve a resposta de /carteira (para liberar depois uma carga segurada)."""
    with page.expect_response('**/carteira*') as resp:
        _abrir(page, state)
    return resp.value.json()


def test_voltar_para_exposicao_aparece_na_hora_e_anima(painel):
    page, state = painel
    # Conta toda animacao criada nos elementos da Exposicao (mais robusto que olhar so o instante).
    page.evaluate(CONTAR_ANIMS)
    carteira = _abrir_guardando_carteira(page, state)
    assert page.evaluate('window._animsExpo') > 0   # a primeira pintura anima
    total = page.locator('#xTotal').inner_text()
    nav(page, 'maquinas')
    page.wait_for_load_state('networkidle')
    # A carga da Exposicao fica presa: o que aparece vem do que ja estava em memoria.
    state['hold'] = '/carteira'
    page.evaluate('window._animsExpo = 0')
    nav(page, 'exposicao')
    pw.expect(page.locator('#listaExposicao [data-linha]')).to_have_count(2)
    pw.expect(page.locator('#xTotal')).to_have_text(total)
    assert 'Carregando' not in page.locator('[data-section="exposicao"]').inner_text()
    # A animacao de entrada toca sem esperar a rede.
    assert page.evaluate('window._animsExpo') > 0
    assert page.evaluate(TOCANDO) > 0
    assert state['held']
    # A carga em segundo plano chega com os mesmos dados: nao redesenha nem reanima de novo.
    page.evaluate('window._animsExpo = 0')
    page.evaluate("document.querySelector('#listaExposicao [data-linha]').dataset.marca = '1'")
    state['hold'] = None
    for r in state['held']:
        r.fulfill(json=carteira)
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(100)
    assert page.evaluate('window._animsExpo') == 0
    assert page.evaluate("document.querySelector('#listaExposicao [data-linha]').dataset.marca") == '1'
    assert not state['errors']


def test_cada_entrada_na_exposicao_reanima(painel):
    page, state = painel
    page.evaluate(CONTAR_ANIMS)
    _abrir(page, state)
    for _ in range(2):
        nav(page, 'maquinas')
        page.wait_for_load_state('networkidle')
        page.evaluate('window._animsExpo = 0')
        nav(page, 'exposicao')
        assert page.evaluate('window._animsExpo') > 0
        page.wait_for_load_state('networkidle')


def test_refresh_de_5s_na_exposicao_nao_reanima(painel):
    page, state = painel
    page.evaluate(CONTAR_ANIMS)
    _abrir(page, state)
    # O relogio do painel passa a usar o relogio falso do teste.
    page.clock.install()
    page.evaluate("pausar('teste'); retomar()")
    page.wait_for_load_state('networkidle')
    page.evaluate('window._animsExpo = 0')
    page.evaluate("document.querySelector('#xFaixas [data-faixa]').dataset.marca = '1'")
    with page.expect_request('**/carteira*'):
        page.clock.run_for(5100)
    page.wait_for_load_state('networkidle')
    assert page.evaluate('window._animsExpo') == 0
    assert page.evaluate("document.querySelector('#xFaixas [data-faixa]').dataset.marca") == '1'
    pw.expect(page.locator('#listaExposicao [data-linha]')).to_have_count(2)
