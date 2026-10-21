"""Pop-ups abrem e fecham com animacao curta (busca, detalhe, confirmacao de exclusao).

A entrada sai de scale(0.96) + opacidade 0; a saida e mais curta e nao pode deixar o
pop-up preso na tela. Com "menos movimento" no sistema, so um fade (sem transform).
"""
import os
from pathlib import Path
import re
import shutil

import pytest

from tests.test_painel import painel, pw, nav, captura  # noqa: F401


@pytest.fixture(autouse=True)
def _navegador_animacoes(monkeypatch, request):
    # Autouse roda antes de painel; monkeypatch restaura o ambiente apos cada teste.
    if os.getenv('SOMPO_TEST_BROWSER'):
        return
    if Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe').is_file() or shutil.which('chrome'):
        monkeypatch.setenv('SOMPO_TEST_BROWSER', 'chrome')
    elif request.node.originalname in (
        'test_popups_entram_com_escala_e_fade',
        'test_fechar_por_esc_fundo_botao_e_codigo',
        'test_menos_movimento_so_fade',
    ):
        pytest.skip('headless shell nao avanca transicao de saida de dialog; rode com Chrome')


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
        page.wait_for_function("""alvo => {
          const transform = getComputedStyle(document.querySelector(alvo)).transform;
          return transform === 'none' || transform === 'matrix(1, 0, 0, 1, 0, 0)';
        }""", arg=POPUPS[nome][1], timeout=1000)
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


ANIMANDO_CARTOES = "() => document.getAnimations().filter(a => a.effect?.target?.classList?.contains('fazenda-card')).length"


def test_inicio_anima_na_hora_ao_voltar_sem_esperar_a_rede(painel):
    # Voltando ao Inicio os cartoes antigos ja estao no HTML: a animacao tocava so depois da
    # resposta do /carteira (parados ~0,5 s e depois piscavam). Tem de tocar ja, e a resposta
    # tardia nao pode repeti-la.
    page, state = painel
    pw.expect(page.locator('#listaInicio .fazenda-card')).to_have_count(2)
    carteira = page.evaluate("fetch('/carteira?dias=7').then(r => r.json())")
    page.wait_for_function("() => !document.getAnimations().some(a => a.effect?.target?.classList?.contains('fazenda-card'))")
    nav(page, 'operadores')
    state['hold'] = '/carteira'
    nav(page, 'inicio')
    page.wait_for_timeout(120)
    assert state['held'], 'a rede devia estar segurada'
    assert page.evaluate(ANIMANDO_CARTOES) == 2          # animando sem a rede ter respondido
    page.wait_for_function("() => !document.getAnimations().some(a => a.effect?.target?.classList?.contains('fazenda-card'))")
    state['hold'] = None
    for r in state['held']:
        r.fulfill(json=carteira)
    page.wait_for_timeout(250)
    assert page.evaluate(ANIMANDO_CARTOES) == 0          # a resposta nao repete a animacao
    pw.expect(page.locator('#listaInicio .fazenda-card')).to_have_count(2)
    assert not state['errors']


def test_painel_da_maquina_entra_na_hora_ao_voltar_e_nao_refaz_os_graficos(painel):
    # Voltando a uma aba ja desenhada, as secoes entram na hora (fade curto) com os dados antigos;
    # os efeitos por elemento (linhas, medidores, barras: todos passam por entrar()) nao repetem
    # quando a resposta chega.
    page, state = painel
    page.evaluate("""() => { window.__entrar = 0; const o = window.entrar;
        window.entrar = function(...a){ window.__entrar++; return o.apply(this, a); }; }""")
    page.select_option('#equipamentoSel', '1')
    pw.expect(page.locator('#tituloView')).to_have_text('Painel da máquina')
    page.wait_for_timeout(2500)
    assert page.evaluate('window.__entrar') > 0          # 1a visita: os efeitos por elemento tocam
    nav(page, 'operadores')
    page.wait_for_timeout(300)
    page.evaluate('window.__entrar = 0')
    nav(page, 'visao')
    page.wait_for_timeout(100)
    na_hora = page.evaluate("() => document.getAnimations().filter(a => a.effect?.target?.hasAttribute?.('data-section')).length")
    assert na_hora >= 1                                  # as secoes ja estao entrando
    page.wait_for_timeout(1500)
    assert page.evaluate('window.__entrar') == 0         # e a resposta nao refez os efeitos
    assert not state['errors']


def test_trocar_o_periodo_continua_animando_os_efeitos(painel):
    # A entrada rapida vale so para a VOLTA a uma aba; trocar o periodo (ou a maquina) e entrada nova.
    page, state = painel
    page.evaluate("""() => { window.__entrar = 0; const o = window.entrar;
        window.entrar = function(...a){ window.__entrar++; return o.apply(this, a); }; }""")
    page.select_option('#equipamentoSel', '1')
    pw.expect(page.locator('#tituloView')).to_have_text('Painel da máquina')
    page.wait_for_timeout(2000)
    nav(page, 'operadores')
    nav(page, 'visao')
    page.wait_for_timeout(500)
    page.evaluate('window.__entrar = 0')
    page.evaluate("document.querySelector('[data-periodo=\"30\"]').click()")
    page.wait_for_timeout(2000)
    assert page.evaluate('window.__entrar') > 0
    assert not state['errors']
