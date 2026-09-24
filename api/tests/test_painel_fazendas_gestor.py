"""Aba Fazendas: gestor responsavel (com quem falar) na lista e no detalhe."""
from tests.test_painel import painel, pw, nav  # noqa: F401


def test_lista_e_detalhe_mostram_o_gestor(painel):
    page, state = painel
    state['gestores'] = {1: [dict(id_usuario=7, usuario='joao.silva'), dict(id_usuario=8, usuario='<b>maria</b>')]}
    nav(page, 'fazendas')
    lista = page.locator('#listaFazendas')
    pw.expect(lista.locator('thead')).to_contain_text('Gestor responsável')
    celula = lista.locator('tr[data-faz="0"] td[data-rotulo="Gestor responsável"]')
    # Nome escapado: vira texto, nunca HTML.
    pw.expect(celula).to_have_text('joao.silva, <b>maria</b>')
    assert celula.locator('b').count() == 0
    sem = lista.locator('tr[data-faz="1"] td[data-rotulo="Gestor responsável"]')
    pw.expect(sem).to_have_text('Sem gestor')
    pw.expect(sem.locator('.text-on-surface-variant')).to_have_count(1)
    # No celular a tabela vira cartao: o rotulo da coluna aparece junto do nome.
    if page.viewport_size['width'] < 700:
        rotulo = celula.evaluate("td => getComputedStyle(td, '::before').content")
        assert 'Gestor responsável' in rotulo

    lista.locator('tr[data-faz="0"]').click()
    detalhe = page.locator('#modalDetalhe')
    pw.expect(detalhe).to_contain_text('Gestor responsável')
    pw.expect(detalhe.locator('dd', has_text='joao.silva')).to_have_text('joao.silva, <b>maria</b>')


def test_detalhe_sem_gestor(painel):
    page, state = painel
    nav(page, 'fazendas')
    page.locator('#listaFazendas tr[data-faz="1"]').click()
    linha = page.locator('#modalDetalhe dt', has_text='Gestor responsável').locator('xpath=..')
    pw.expect(linha.locator('dd')).to_have_text('Sem gestor')
