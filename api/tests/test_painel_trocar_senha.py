"""Tela de troca de senha: a propria (menu do usuario) e a de outro usuario (detalhe, so Sompo)."""
from tests.test_painel import painel, pw, nav  # noqa: F401


def _logado_como(page, usuario='ana'):
    # O fixture responde /me sem usuario (modo demo); aqui o painel passa a ter login de verdade.
    page.route('**/me', lambda r: r.fulfill(json=dict(usuario=usuario, role='sompo', fazenda_id=None)))
    page.evaluate('aplicarPerfil()')


def _abrir_minha_senha(page):
    page.locator('[popovertarget="menuUsuario"]:visible').first.click()
    page.locator('#menuUsuario [data-minha-senha]').click()
    pw.expect(page.locator('#formMinhaSenha')).to_be_visible()


def test_trocar_a_propria_senha(painel):
    page, state = painel
    _logado_como(page)
    _abrir_minha_senha(page)
    page.fill('#msAtual', 'senha-atual-1')
    page.fill('#msNova', 'senha-nova-123')
    page.fill('#msConfirma', 'senha-nova-123')
    page.locator('#formMinhaSenha [type="submit"]').click()
    pw.expect(page.locator('#msMsg')).to_contain_text('Senha trocada')
    assert state['posts'][-1] == ('/me/senha', {'senha_atual': 'senha-atual-1', 'senha_nova': 'senha-nova-123'})


def test_confirmacao_diferente_nao_envia(painel):
    page, state = painel
    _logado_como(page)
    _abrir_minha_senha(page)
    antes = len(state['posts'])
    page.fill('#msAtual', 'senha-atual-1')
    page.fill('#msNova', 'senha-nova-123')
    page.fill('#msConfirma', 'outra-coisa-12')
    page.locator('#formMinhaSenha [type="submit"]').click()
    pw.expect(page.locator('#msMsg')).to_have_text('As duas senhas novas não conferem.')
    assert len(state['posts']) == antes


def test_erro_do_servidor_vira_frase(painel):
    page, state = painel
    _logado_como(page)
    page.route('**/me/senha', lambda r: r.fulfill(status=400, json={'erro': 'senha_atual_incorreta'}))
    _abrir_minha_senha(page)
    page.fill('#msAtual', 'errada-errada')
    page.fill('#msNova', 'senha-nova-123')
    page.fill('#msConfirma', 'senha-nova-123')
    page.locator('#formMinhaSenha [type="submit"]').click()
    pw.expect(page.locator('#msMsg')).to_have_text('A senha atual não confere.')


def test_modo_demo_nao_mostra_minha_senha(painel):
    page, state = painel
    page.locator('[popovertarget="menuUsuario"]:visible').first.click()
    pw.expect(page.locator('#menuUsuario [data-minha-senha]')).to_be_hidden()


def test_sompo_troca_a_senha_de_um_usuario(painel):
    page, state = painel
    nav(page, 'usuarios')
    page.locator('[data-usuario-detalhe="7"]').first.click()
    page.locator('[data-trocar-senha-usuario="7"]').click()
    page.fill('#suNova', 'senha-do-gestor-1')
    page.fill('#suConfirma', 'senha-do-gestor-1')
    page.locator('#formSenhaUsuario [type="submit"]').click()
    pw.expect(page.locator('#suMsg')).to_contain_text('Senha de gestor.teste trocada')
    assert state['posts'][-1] == ('/usuarios/7/senha', {'senha_nova': 'senha-do-gestor-1'})


def test_sessao_caida_durante_a_troca_volta_para_o_login(painel):
    page, state = painel
    _logado_como(page)
    page.route('**/me/senha', lambda r: r.fulfill(status=401, json={'erro': 'nao_autorizado'}))
    _abrir_minha_senha(page)
    page.fill('#msAtual', 'senha-atual-1')
    page.fill('#msNova', 'senha-nova-123')
    page.fill('#msConfirma', 'senha-nova-123')
    with page.expect_navigation(url='**/login'):
        page.locator('#formMinhaSenha [type="submit"]').click()
