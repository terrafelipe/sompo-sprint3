"""Seletor de máquina sempre visível na barra de contexto, mesmo sem fazenda escolhida."""
import os
from pathlib import Path

from tests.test_painel import painel, pw, nav  # noqa: F401

# Máquinas que o usuário consegue escolher (opção habilitada com valor).
MAQUINAS_HABILITADAS = """s => [...s.options].filter(o => o.value && !o.disabled).map(o => o.textContent)"""
AVISOS = """s => [...s.options].filter(o => o.disabled).map(o => o.textContent)"""


def _print(page, nome):
    destino = Path(os.environ.get('TEMP', '.')) / 'sompo-seletor'
    destino.mkdir(parents=True, exist_ok=True)
    largura = page.viewport_size['width']
    for tema in ('claro', 'escuro'):
        page.evaluate('t => document.documentElement.dataset.tema = t', tema)
        page.locator('#barraContexto').screenshot(path=str(destino / f'{nome}-{tema}-{largura}.png'))
    page.evaluate("document.documentElement.dataset.tema = 'claro'")


def _painel_sem_fazenda(page):
    # O fixture já abriu a Fazenda 1; recarregar volta ao estado de primeira entrada
    # (perfil Sompo no Início, nenhuma fazenda escolhida) e daí vamos direto ao Painel.
    page.reload()
    pw.expect(page.locator('#tituloView')).to_have_text('Início')
    pw.expect(page.locator('#fazendaSel option')).to_have_count(3)
    nav(page, 'visao')
    assert page.evaluate('fazendaSelecionada') is None


def test_seletor_de_maquina_visivel_sem_fazenda_e_sem_maquinas(painel):
    page, state = painel
    _painel_sem_fazenda(page)
    sel = page.locator('#equipamentoSel')
    pw.expect(page.locator('#equipamentoSelWrap')).to_be_visible()
    pw.expect(page.locator('#fazendaSelWrap')).to_be_visible()
    pw.expect(sel).to_have_value('')
    pw.expect(page.locator('#equipamentoSel selectedcontent')).to_have_text('Selecione uma máquina')
    assert sel.evaluate(MAQUINAS_HABILITADAS) == []
    assert sel.evaluate(AVISOS) == ['Escolha uma fazenda primeiro']
    _print(page, 'sem-fazenda')

    page.select_option('#fazendaSel', '1')
    pw.expect(page.locator('#equipamentoSel option[value="1"]')).to_have_count(1)
    assert sel.evaluate(MAQUINAS_HABILITADAS) == ['Trator 1']
    assert sel.evaluate(AVISOS) == []
    pw.expect(page.locator('#equipamentoSelWrap')).to_be_visible()
    _print(page, 'com-fazenda')

    page.select_option('#equipamentoSel', '1')
    pw.expect(page.locator('#tituloView')).to_have_text('Painel da máquina')
    assert page.evaluate('equipamentoSelecionado') == 1
    pw.expect(page.locator('#equipamentoSel selectedcontent')).to_have_text('Trator 1')
    assert not state['errors']


def test_fazenda_sem_maquinas_avisa_no_seletor(painel):
    page, state = painel
    state['sem_maquinas'] = True
    _painel_sem_fazenda(page)
    page.select_option('#fazendaSel', '2')
    sel = page.locator('#equipamentoSel')
    pw.expect(sel.locator('option[disabled]')).to_have_text('Nenhuma máquina nesta fazenda')
    assert sel.evaluate(MAQUINAS_HABILITADAS) == []
    pw.expect(page.locator('#equipamentoSelWrap')).to_be_visible()
    # Voltar para "Selecione uma fazenda" devolve o aviso de escolher a fazenda.
    page.select_option('#fazendaSel', '')
    pw.expect(sel.locator('option[disabled]')).to_have_text('Escolha uma fazenda primeiro')
    assert not state['errors']
