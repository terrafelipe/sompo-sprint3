"""Erros de cadastro aparecem como frases no formulário, nunca como o código da API."""
from tests.test_painel import painel, pw, nav, captura  # noqa: F401


def _responder_erro(page, caminho, metodo, codigo, status=409):
    page.route('**' + caminho, lambda r: r.fulfill(status=status, json={'erro': codigo})
               if r.request.method == metodo else r.fallback())


def _novo_operador(page):
    nav(page, 'operadores')
    page.locator('#btnNovoOperador').click()
    page.locator('#opNome').fill('Felipe')
    page.locator('#opUid').fill('AB CD EF 12')
    page.locator('#formOperador button[type=submit]').click()


def test_cracha_ja_cadastrado_vira_frase(painel):
    page, state = painel
    _responder_erro(page, '/operadores', 'POST', 'cracha_ja_cadastrado')
    _novo_operador(page)
    msg = page.locator('#opMsg')
    pw.expect(msg).to_contain_text('crachá já pertence a outro operador')
    assert '_' not in msg.text_content()
    pw.expect(page.locator('#formOperador')).to_be_visible()
    captura(page, 'erro-cracha')


def test_codigo_desconhecido_nao_aparece_cru(painel):
    page, state = painel
    _responder_erro(page, '/operadores', 'POST', 'erro_que_nao_existe', status=400)
    _novo_operador(page)
    msg = page.locator('#opMsg')
    pw.expect(msg).to_contain_text('Não foi possível salvar')
    assert '_' not in msg.text_content()


def test_esp32_ja_vinculado_vira_frase(painel):
    page, state = painel
    _responder_erro(page, '/equipamentos', 'POST', 'dispositivo_ja_vinculado')
    nav(page, 'maquinas')
    page.locator('#btnNovaMaquina').click()
    page.locator('#maqNome').fill('Colheitadeira teste')
    page.locator('#maqDispositivo').fill('ESP-1')
    page.locator('#formMaquina button[type=submit]').click()
    msg = page.locator('#maqMsg')
    pw.expect(msg).to_contain_text('ESP32 já está vinculado a outra máquina')
    assert '_' not in msg.text_content()
    assert not state['errors']
