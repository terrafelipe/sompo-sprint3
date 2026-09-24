"""Ocorrências como no Trello: arrastar o cartão entre as colunas muda a situação."""
from tests.test_painel import painel, pw, nav, arrastar, _ocorrencia, captura  # noqa: F401


def _quadro(page, state):
    state['ocorrencias'] = [_ocorrencia(1, 'Capô aberto', 'aberta'), _ocorrencia(2, 'Cerca', 'em_verificacao')]
    nav(page, 'ocorrencias')
    pw.expect(page.locator('[data-coluna="aberta"] [data-oc]')).to_have_count(1)


def test_arrastar_para_verificacao_e_de_volta(painel):
    page, state = painel
    _quadro(page, state)
    arrastar(page, '[data-oc="1"]', '[data-lista-oc="em_verificacao"]')
    pw.expect(page.locator('[data-lista-oc="em_verificacao"] [data-oc]')).to_have_count(2)
    assert ('/ocorrencias/1', {'status': 'em_verificacao'}) in state['posts']
    pw.expect(page.locator('#ocResumo')).to_contain_text('0 abertas · 2 em verificação')
    captura(page, 'quadro-arrastado')
    arrastar(page, '[data-oc="1"]', '[data-lista-oc="aberta"]')
    pw.expect(page.locator('[data-lista-oc="aberta"] [data-oc="1"]')).to_have_count(1)
    assert ('/ocorrencias/1', {'status': 'aberta'}) in state['posts']
    assert not state['errors']


def test_soltar_na_mesma_coluna_nao_salva(painel):
    page, state = painel
    _quadro(page, state)
    antes = len(state['posts'])
    arrastar(page, '[data-oc="1"]', '[data-lista-oc="aberta"]')
    pw.expect(page.locator('[data-lista-oc="aberta"] [data-oc="1"]')).to_have_count(1)
    assert len(state['posts']) == antes


def test_clique_sem_arrastar_abre_o_detalhe(painel):
    page, state = painel
    _quadro(page, state)
    page.locator('[data-oc="2"] [data-abrir-oc]').click()
    pw.expect(page.locator('#ocStatus')).to_have_value('em_verificacao')


def test_falha_ao_salvar_volta_o_cartao_e_avisa(painel):
    page, state = painel
    _quadro(page, state)
    page.route('**/ocorrencias/1', lambda r: r.fulfill(status=502, json={'erro': 'indisponivel'})
               if r.request.method == 'PATCH' else r.fallback())
    arrastar(page, '[data-oc="1"]', '[data-lista-oc="resolvida"]')
    pw.expect(page.locator('#ocAviso')).to_contain_text('Não foi possível mover')
    pw.expect(page.locator('[data-lista-oc="aberta"] [data-oc="1"]')).to_have_count(1)
    pw.expect(page.locator('[data-lista-oc="resolvida"] [data-oc]')).to_have_count(0)
