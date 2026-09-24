"""Logo do cliente na aba Clientes: imagem num circulo antes do nome, iniciais de reserva."""
import base64

from tests.test_painel import painel, pw, nav, captura  # noqa: F401

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')
LOGO = 'https://logos.test/agro.png'
QUEBRADO = 'https://logos.test/sumiu.png'
MALICIOSO = 'https://logos.test/x.png" onerror="window.__xss=1"><b id="injetado">oi</b>'


def _clientes(page, clientes):
    # Rotas registradas depois tem prioridade sobre a do fixture.
    page.route('**/logos.test/**', lambda r: r.fulfill(body=PNG, content_type='image/png')
               if r.request.url.startswith(LOGO) else r.fulfill(status=404, body=''))
    page.route('**/clientes', lambda r: r.fulfill(json={'dados': clientes}) if r.request.method == 'GET' else r.fallback())
    nav(page, 'clientes')
    pw.expect(page.locator('#listaClientes [data-cli]')).to_have_count(len(clientes))


def _circulo(page, i):
    return page.locator(f'#listaClientes [data-cli="{i}"] .logo-cliente')


def test_com_logo_mostra_imagem(painel):
    page, state = painel
    _clientes(page, [dict(id_cliente=1, nome='Agro Verde', logo_url=LOGO)])
    img = _circulo(page, 0).locator('img')
    pw.expect(img).to_have_attribute('src', LOGO)
    pw.expect(img).to_have_attribute('loading', 'lazy')
    pw.expect(img).to_have_attribute('referrerpolicy', 'no-referrer')
    pw.expect(img).to_have_attribute('alt', '')
    assert img.evaluate('e => getComputedStyle(e).objectFit') == 'cover'
    pw.expect(img).to_have_js_property('naturalWidth', 1)
    caixa = _circulo(page, 0).bounding_box()
    assert round(caixa['width']) == 28 and round(caixa['height']) == 28
    captura(page, 'clientes-logo')


def test_sem_logo_mostra_iniciais(painel):
    page, state = painel
    _clientes(page, [dict(id_cliente=1, nome='Agro Verde Ltda', logo_url=None), dict(id_cliente=2, nome='zeca', logo_url='')])
    pw.expect(_circulo(page, 0)).to_have_text('AV')
    pw.expect(_circulo(page, 1)).to_have_text('Z')
    pw.expect(_circulo(page, 0).locator('img')).to_have_count(0)
    # No celular (cartao) o circulo continua redondo e ao lado do nome, sem quebrar a linha.
    circulo, nome = _circulo(page, 0).bounding_box(), page.locator('#listaClientes [data-cli="0"] td').first.bounding_box()
    assert round(circulo['width']) == 28 and round(circulo['height']) == 28
    assert circulo['y'] >= nome['y'] and circulo['y'] + circulo['height'] <= nome['y'] + nome['height']
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_imagem_quebrada_vira_iniciais(painel):
    page, state = painel
    _clientes(page, [dict(id_cliente=1, nome='Boa Safra', logo_url=QUEBRADO)])
    pw.expect(_circulo(page, 0)).to_have_text('BS')
    pw.expect(_circulo(page, 0).locator('img')).to_have_count(0)


def test_logo_com_aspas_nao_injeta_html(painel):
    page, state = painel
    nome = 'Agro X <b id="injetado">oi</b>'
    _clientes(page, [dict(id_cliente=1, nome=nome, logo_url=MALICIOSO)])
    pw.expect(page.locator('#listaClientes [data-cli="0"]')).to_contain_text(nome)
    pw.expect(_circulo(page, 0)).to_have_text('AX')  # a imagem nao carrega e vira iniciais
    assert page.locator('#injetado').count() == 0
    assert page.evaluate('window.__xss') is None


def test_cadastro_envia_o_logo(painel):
    page, state = painel
    nav(page, 'clientes')
    page.locator('#btnNovoCliente').click()
    campo = page.locator('#clLogo')
    pw.expect(campo).to_have_attribute('type', 'url')
    pw.expect(campo).to_have_attribute('placeholder', 'https://...')
    pw.expect(page.locator('label[for="clLogo"]')).to_have_text('Logo (link da imagem)')
    page.locator('#clNome').fill('Agro Verde')
    page.locator('#clCnpj').fill('00.000.000/0001-00')
    page.locator('#clTel').fill('11 90000-0000')
    page.locator('#clEnd').fill('Rua A')
    campo.fill(LOGO)
    page.locator('#formCliente button[type=submit]').click()
    pw.expect(page.locator('#clMsg')).to_contain_text('Cliente cadastrado')
    assert ('/clientes', {'nome': 'Agro Verde', 'cnpj': '00.000.000/0001-00', 'telefone': '11 90000-0000',
                          'endereco': 'Rua A', 'email': '', 'logo_url': LOGO}) in state['posts']


def test_logo_invalido_vira_frase_no_cadastro(painel):
    page, state = painel
    page.route('**/clientes', lambda r: r.fulfill(status=400, json={'erro': 'logo_invalido'})
               if r.request.method == 'POST' else r.fallback())
    nav(page, 'clientes')
    page.locator('#btnNovoCliente').click()
    for campo, valor in [('#clNome', 'Agro'), ('#clCnpj', '1'), ('#clTel', '1'), ('#clEnd', 'Rua'), ('#clLogo', 'https://x.test/a b')]:
        page.locator(campo).fill(valor)
    page.locator('#formCliente button[type=submit]').click()
    msg = page.locator('#clMsg')
    pw.expect(msg).to_contain_text('O link do logo precisa começar com https://')
    assert '_' not in msg.text_content()


def test_detalhe_mostra_preview_e_troca_o_logo(painel):
    page, state = painel
    trocas = []

    clientes = [dict(id_cliente=1, nome='Agro Verde', logo_url=LOGO)]

    def patch(r):
        trocas.append(r.request.post_data_json)
        clientes[0].update(r.request.post_data_json)
        r.fulfill(json={'ok': True, 'cliente': dict(clientes[0])})
    page.route('**/clientes/1', lambda r: patch(r) if r.request.method == 'PATCH' else r.fallback())
    _clientes(page, clientes)
    page.locator('#listaClientes [data-cli="0"]').click()
    preview = page.locator('#detCorpo .logo-cliente')
    pw.expect(preview.locator('img')).to_have_attribute('src', LOGO)
    campo = page.locator('#clLogoEditar')
    pw.expect(campo).to_have_value(LOGO)
    campo.fill('')
    page.locator('[data-salvar-logo="1"]').click()
    pw.expect(page.locator('#clLogoMsg')).to_contain_text('Logo removido')
    assert trocas == [{'logo_url': None}]
    pw.expect(preview).to_have_text('AV')
    pw.expect(_circulo(page, 0)).to_have_text('AV')

    novo = 'https://logos.test/agro.png?v=2'
    campo.fill(novo)
    page.locator('[data-salvar-logo="1"]').click()
    pw.expect(page.locator('#clLogoMsg')).to_contain_text('Logo salvo')
    assert trocas[-1] == {'logo_url': novo}
    pw.expect(preview.locator('img')).to_have_attribute('src', novo)


def test_detalhe_logo_invalido_vira_frase(painel):
    page, state = painel
    page.route('**/clientes/1', lambda r: r.fulfill(status=400, json={'erro': 'logo_invalido'})
               if r.request.method == 'PATCH' else r.fallback())
    _clientes(page, [dict(id_cliente=1, nome='Agro Verde', logo_url=None)])
    page.locator('#listaClientes [data-cli="0"]').click()
    page.locator('#clLogoEditar').fill('https://x.test/a b')
    page.locator('[data-salvar-logo="1"]').click()
    msg = page.locator('#clLogoMsg')
    pw.expect(msg).to_contain_text('O link do logo precisa começar com https://')
    assert '_' not in msg.text_content()
