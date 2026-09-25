"""Troca de senha pelo painel: a propria (com a senha atual) e a de outro usuario (so Sompo)."""
import time
from unittest.mock import patch

from werkzeug.security import check_password_hash, generate_password_hash

import app

ATUAL = 'certa-12345'
HASH = generate_password_hash(ATUAL)


def _usuario(id_usuario=1, nome='ana', senha=HASH, role='sompo', **extra):
    return {'id_usuario': id_usuario, 'usuario': nome, 'senha': senha, 'role': role, **extra}


def _logado(client, usuario=None, role='sompo', impressao=True):
    u = usuario or _usuario(role=role)
    with client.session_transaction() as s:
        s.update(logado=True, login_em=time.time(), usuario=u['usuario'], usuario_id=u['id_usuario'], role=role,
                 fazenda_id=1 if role == 'gestor_fazenda' else None)
        if impressao:
            s['senha_fp'] = app._impressao_senha(u['senha'])
    return u


def _chamar(client, metodo, rota, corpo, banco):
    with patch('app.PAINEL_SENHA', 'liga-o-login'), patch('app.buscar_usuario', side_effect=banco), \
         patch('app.consultar_usuario', side_effect=lambda i: next((u for u in [banco(n) for n in ('ana', 'gil')]
                                                                    if u and str(u['id_usuario']) == str(i)), None)), \
         patch('app.atualizar_tabela') as gravar:
        resposta = getattr(client, metodo)(rota, json=corpo)
    return resposta, gravar


# --- a propria senha -------------------------------------------------------------------------

def test_trocar_a_propria_senha_grava_hash_e_mantem_a_sessao():
    client = app.app.test_client()
    u = _logado(client)
    resposta, gravar = _chamar(client, 'post', '/me/senha', {'senha_atual': ATUAL, 'senha_nova': 'nova-senha-123'},
                               lambda n: u if n == 'ana' else None)
    assert resposta.status_code == 200
    tabela, filtros, dados = gravar.call_args.args
    assert tabela == 'usuario' and filtros == {'id_usuario': 'eq.1'}
    assert check_password_hash(dados['senha'], 'nova-senha-123')
    # A sessao atual continua valendo com a senha nova (a impressao foi atualizada).
    novo = _usuario(senha=dados['senha'])
    app._revalidados.clear()
    with patch('app.PAINEL_SENHA', 'liga-o-login'), patch('app.buscar_usuario', return_value=novo):
        assert client.get('/me').status_code == 200


def test_senha_atual_errada_nao_troca():
    client = app.app.test_client()
    u = _logado(client)
    resposta, gravar = _chamar(client, 'post', '/me/senha', {'senha_atual': 'errada', 'senha_nova': 'nova-senha-123'},
                               lambda n: u if n == 'ana' else None)
    assert resposta.status_code == 400 and resposta.json == {'erro': 'senha_atual_incorreta'}
    gravar.assert_not_called()


def test_senha_atual_errada_conta_no_limite_de_tentativas():
    client = app.app.test_client()
    u = _logado(client)
    for _ in range(5):
        _chamar(client, 'post', '/me/senha', {'senha_atual': 'errada', 'senha_nova': 'nova-senha-123'},
                lambda n: u if n == 'ana' else None)
    resposta, gravar = _chamar(client, 'post', '/me/senha', {'senha_atual': ATUAL, 'senha_nova': 'nova-senha-123'},
                               lambda n: u if n == 'ana' else None)
    assert resposta.status_code == 429 and resposta.json == {'erro': 'muitas_tentativas'}
    gravar.assert_not_called()


def test_senha_nova_curta_ou_igual_a_atual_e_recusada():
    client = app.app.test_client()
    u = _logado(client)
    for nova, erro in [('curta', 'senha_curta'), (ATUAL, 'senha_igual'), (None, 'senha_curta')]:
        resposta, gravar = _chamar(client, 'post', '/me/senha', {'senha_atual': ATUAL, 'senha_nova': nova},
                                   lambda n: u if n == 'ana' else None)
        assert resposta.status_code == 400 and resposta.json == {'erro': erro}
        gravar.assert_not_called()


def test_sem_login_nao_troca():
    client = app.app.test_client()
    resposta, gravar = _chamar(client, 'post', '/me/senha', {'senha_atual': ATUAL, 'senha_nova': 'nova-senha-123'},
                               lambda n: None)
    assert resposta.status_code == 401
    gravar.assert_not_called()


def test_modo_demo_sem_usuario_nao_troca():
    # Login desligado (demo): nao ha usuario de verdade para trocar a senha.
    with patch('app.atualizar_tabela') as gravar:
        resposta = app.app.test_client().post('/me/senha', json={'senha_atual': 'a', 'senha_nova': 'nova-senha-123'})
    assert resposta.status_code == 409 and resposta.json == {'erro': 'sem_usuario'}
    gravar.assert_not_called()


# --- senha de outro usuario (Sompo) -----------------------------------------------------------

GIL = _usuario(id_usuario=7, nome='gil', role='gestor_fazenda')


def _banco(n):
    return {'ana': _usuario(), 'gil': GIL}.get(n)


def test_sompo_troca_a_senha_de_outro_usuario():
    client = app.app.test_client()
    _logado(client)
    resposta, gravar = _chamar(client, 'post', '/usuarios/7/senha', {'senha_nova': 'senha-do-gil-1'}, _banco)
    assert resposta.status_code == 200
    tabela, filtros, dados = gravar.call_args.args
    assert filtros == {'id_usuario': 'eq.7'} and check_password_hash(dados['senha'], 'senha-do-gil-1')


def test_gestor_nao_troca_senha_de_outro():
    client = app.app.test_client()
    _logado(client, usuario=GIL, role='gestor_fazenda')
    resposta, gravar = _chamar(client, 'post', '/usuarios/1/senha', {'senha_nova': 'senha-da-ana-1'}, _banco)
    assert resposta.status_code == 403
    gravar.assert_not_called()


def test_usuario_inexistente_ou_excluido_da_404():
    client = app.app.test_client()
    _logado(client)
    excluido = dict(GIL, excluido_em='2026-09-01')
    for banco in (lambda n: _usuario() if n == 'ana' else None,
                  lambda n: {'ana': _usuario(), 'gil': excluido}.get(n)):
        resposta, gravar = _chamar(client, 'post', '/usuarios/7/senha', {'senha_nova': 'senha-do-gil-1'}, banco)
        assert resposta.status_code == 404
        gravar.assert_not_called()


def test_senha_curta_para_outro_usuario_e_recusada():
    client = app.app.test_client()
    _logado(client)
    resposta, gravar = _chamar(client, 'post', '/usuarios/7/senha', {'senha_nova': 'curta'}, _banco)
    assert resposta.status_code == 400 and resposta.json == {'erro': 'senha_curta'}
    gravar.assert_not_called()


# --- sessao cai quando a senha muda -----------------------------------------------------------

def test_sessao_cai_quando_a_senha_foi_trocada_em_outro_lugar():
    client = app.app.test_client()
    _logado(client)
    trocada = _usuario(senha=generate_password_hash('outra-senha-99'))
    with patch('app.PAINEL_SENHA', 'liga-o-login'), patch('app.buscar_usuario', return_value=trocada):
        assert client.get('/me', headers={'Accept': 'application/json'}).status_code == 401
    with client.session_transaction() as s:
        assert not s.get('logado')


def test_sessao_antiga_sem_impressao_continua_valendo():
    client = app.app.test_client()
    _logado(client, impressao=False)
    with patch('app.PAINEL_SENHA', 'liga-o-login'), patch('app.buscar_usuario', return_value=_usuario()):
        assert client.get('/me').status_code == 200


def test_login_guarda_a_impressao_do_hash_e_nunca_a_senha():
    client = app.app.test_client()
    with patch('app.PAINEL_SENHA', 'liga-o-login'), patch('app.buscar_usuario', return_value=_usuario()):
        assert client.post('/login', data={'usuario': 'ana', 'senha': ATUAL}).status_code == 302
    with client.session_transaction() as s:
        assert s['senha_fp'] == app._impressao_senha(HASH)
        assert ATUAL not in str(dict(s))


def test_cadastro_com_senha_curta_e_recusado():
    with patch('app.inserir_tabela') as inserir:
        resposta = app.app.test_client().post('/usuarios', json={'usuario': 'novo', 'senha': 'curta', 'role': 'sompo'})
    assert resposta.status_code == 400 and resposta.json == {'erro': 'senha_curta'}
    inserir.assert_not_called()
