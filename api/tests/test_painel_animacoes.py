"""Pop-ups abrem e fecham com animacao curta (busca, detalhe, confirmacao de exclusao).

A entrada sai de scale(0.96) + opacidade 0; a saida e mais curta e nao pode deixar o
pop-up preso na tela. Com "menos movimento" no sistema, so um fade (sem transform).
"""
import re

from tests.test_painel import painel, pw, nav, captura  # noqa: F401

# Abre o pop-up e le o primeiro quadro no mesmo tique (antes de a transicao andar).
PRIMEIRO_QUADRO = """([abrir, alvo]) => {
  (0, eval)(abrir);
  const el = document.querySelector(alvo);
  const cs = getComputedStyle(el);
  return {
    transform: cs.transform,
    duracao: cs.transitionDuration,
    props: el.getAnimations().map(a => a.transitionProperty),
    fundo: document.getAnimations().filter(a => a.effect?.target === el.closest('dialog, #modalDetalhe'))
             .map(a => (a.effect.pseudoElement || '') + ':' + a.transitionProperty),
  };
}"""

POPUPS = {
    'busca': ("abrirPaleta()", '#paleta'),
    'detalhe': ("abrirDetalhe('Trator 1','agriculture','<p>corpo</p>')", '#modalDetalhe > div'),
    'exclusao': ("$('exclusaoDescricao').textContent='x'; $('confirmarExclusao').showModal()", '#confirmarExclusao'),
}


def _escala(transform):
    m = re.match(r'matrix\(([-\d.e]+)', transform)
    return float(m.group(1)) if m else 1.0


def _abrir(page, nome):
    return page.evaluate(PRIMEIRO_QUADRO, list(POPUPS[nome]))


def _fechado(page, nome):
    return page.evaluate("""nome => {
      const el = nome === 'detalhe' ? $('modalDetalhe') : $(nome === 'busca' ? 'paleta' : 'confirmarExclusao');
      const aberto = el.tagName === 'DIALOG' ? el.open : !el.classList.contains('hidden');
      return !aberto && getComputedStyle(el).display === 'none';
    }""", nome)


def _fechar(page, nome, jeito):
    if jeito == 'esc':
        page.keyboard.press('Escape')
    elif jeito == 'fundo':
        page.mouse.click(5, 5)              # canto da tela: fora da caixa, cai no fundo
    elif jeito == 'botao':
        page.locator({'busca': '#paletaFechar', 'detalhe': '#detFechar', 'exclusao': '#exclusaoCancelar'}[nome]).click()
    else:
        page.evaluate({'busca': "$('paleta').close()", 'detalhe': 'fecharDetalhe()',
                       'exclusao': "$('confirmarExclusao').close()"}[nome])


def test_popups_entram_com_escala_e_fade(painel):
    page, state = painel
    for nome in POPUPS:
        q = _abrir(page, nome)
        assert 'transform' in q['props'] and 'opacity' in q['props'], (nome, q)
        assert 0.95 <= _escala(q['transform']) < 1, (nome, q)       # parte de ~0.96, nunca de 0
        assert any(p.endswith(':opacity') for p in q['fundo']), (nome, q)   # o fundo escuro vem em fade
        assert any(float(d.rstrip('s')) > 0 for d in q['duracao'].split(',')), (nome, q)
        page.wait_for_timeout(400)
        assert page.evaluate(f"getComputedStyle(document.querySelector('{POPUPS[nome][1]}')).transform") in ('none', 'matrix(1, 0, 0, 1, 0, 0)')
        captura(page, f'popup-{nome}-aberto')
        _fechar(page, nome, 'codigo')
        page.wait_for_timeout(400)
        assert _fechado(page, nome), nome
    assert not state['errors']


def test_busca_e_rapida_e_saida_e_mais_curta(painel):
    page, state = painel
    duracoes = page.evaluate("""() => {
      const ms = el => Math.max(...getComputedStyle(el).transitionDuration.split(',').map(parseFloat)) * 1000;
      const p = $('paleta'), c = $('confirmarExclusao'), d = document.querySelector('#modalDetalhe > div');
      const saida = [ms(p), ms(c), ms(d)];
      p.showModal(); c.showModal(); $('modalDetalhe').classList.remove('hidden');
      const entrada = [ms(p), ms(c), ms(d)];
      p.close(); c.close(); $('modalDetalhe').classList.add('hidden');
      return {saida, entrada};
    }""")
    busca, exclusao, detalhe = duracoes['entrada']
    assert 140 <= busca <= 160 and 180 <= exclusao <= 220 and 180 <= detalhe <= 220, duracoes
    assert all(120 <= s <= 150 for s in duracoes['saida']), duracoes
    assert all(s < e for s, e in zip(duracoes['saida'], duracoes['entrada'])), duracoes


def test_fechar_por_esc_fundo_botao_e_codigo(painel):
    page, state = painel
    for nome in POPUPS:
        for jeito in ('esc', 'fundo', 'botao', 'codigo'):
            if nome == 'exclusao' and jeito == 'fundo':
                continue                    # a confirmacao de exclusao nao fecha pelo fundo (de proposito)
            _abrir(page, nome)
            page.wait_for_timeout(250)
            _fechar(page, nome, jeito)
            page.wait_for_timeout(300)
            assert _fechado(page, nome), (nome, jeito)
    assert not state['errors']


def test_reabrir_durante_a_saida_fica_aberto(painel):
    page, state = painel
    page.evaluate("abrirDetalhe('A','info','<p>a</p>')")
    page.wait_for_timeout(250)
    page.evaluate("fecharDetalhe(); abrirDetalhe('B','info','<p>b</p>')")   # como detalhe -> outro detalhe
    page.wait_for_timeout(400)
    pw.expect(page.locator('#modalDetalhe')).to_be_visible()
    pw.expect(page.locator('#detTitulo')).to_have_text('B')
    assert page.evaluate("getComputedStyle(document.querySelector('#modalDetalhe > div')).opacity") == '1'
    page.evaluate("abrirPaleta()")
    page.wait_for_timeout(200)
    page.evaluate("$('paleta').close(); abrirPaleta()")
    page.wait_for_timeout(300)
    assert page.evaluate("$('paleta').open && getComputedStyle($('paleta')).opacity") == '1'
    assert not state['errors']


def test_saida_nao_bloqueia_cliques_na_pagina(painel):
    page, state = painel
    # Durante a saida o pop-up ainda esta desenhado: nao pode segurar o clique de quem ja seguiu.
    page.evaluate("abrirDetalhe('A','info','<p>a</p>')")
    page.wait_for_timeout(250)
    alvos = page.evaluate("""() => {
      fecharDetalhe(); const a = document.elementFromPoint(5, 5)?.closest('#modalDetalhe');
      abrirPaleta(); $('paleta').close(); const b = document.elementFromPoint(5, 5)?.closest('dialog');
      return [!!a, !!b];
    }""")
    assert alvos == [False, False]


def test_busca_devolve_o_foco_ao_fechar(painel):
    page, state = painel
    page.evaluate("$('btnBusca').focus()")
    page.keyboard.press('Control+k')
    pw.expect(page.locator('#paletaInput')).to_be_focused()
    page.keyboard.press('Escape')
    pw.expect(page.locator('#btnBusca')).to_be_focused()


def test_menos_movimento_so_fade(painel):
    page, state = painel
    page.emulate_media(reduced_motion='reduce')
    for nome in POPUPS:
        q = _abrir(page, nome)
        assert q['transform'] == 'none' and 'transform' not in q['props'], (nome, q)
        page.wait_for_timeout(300)
        _fechar(page, nome, 'codigo')
        page.wait_for_timeout(300)
        assert _fechado(page, nome), nome
    assert not state['errors']
