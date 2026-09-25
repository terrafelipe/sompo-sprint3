"""Senhas do painel: o banco guarda hash; senha legada em texto puro vira hash no primeiro login."""
from unittest.mock import patch

from werkzeug.security import check_password_hash, generate_password_hash

import app

HASH_CERTO = generate_password_hash('certa-123')


def _login(guardada, digitada):
    usuario = {'id_usuario': 5, 'usuario': 'gestor.x', 'senha': guardada, 'role': 'sompo'}
    client = app.app.test_client()
    with patch('app.PAINEL_SENHA', 'liga-o-login'), \
         patch('app.buscar_usuario', return_value=usuario), patch('app.atualizar_tabela') as gravar:
        resposta = client.post('/login', data={'usuario': 'gestor.x', 'senha': digitada})
    return resposta.status_code, gravar


def test_senha_com_hash_entra():
    status, gravar = _login(HASH_CERTO, 'certa-123')
    assert status == 302
    gravar.assert_not_called()


def test_senha_errada_com_hash_nao_entra():
    status, _ = _login(HASH_CERTO, 'errada')
    assert status == 401


def test_digitar_o_proprio_hash_nao_entra():
    status, _ = _login(HASH_CERTO, HASH_CERTO)
    assert status == 401


def test_senha_legada_em_texto_entra_e_vira_hash():
    status, gravar = _login('antiga-texto', 'antiga-texto')
    assert status == 302
    tabela, filtros, dados = gravar.call_args.args
    assert tabela == 'usuario' and filtros == {'id_usuario': 'eq.5', 'and': '(senha.not.like.scrypt:*,senha.not.like.pbkdf2:*,senha.neq.!)'}
    assert dados['senha'] != 'antiga-texto' and check_password_hash(dados['senha'], 'antiga-texto')


def test_senha_legada_errada_nao_entra_nem_regrava():
    status, gravar = _login('antiga-texto', 'outra')
    assert status == 401
    gravar.assert_not_called()


def test_falha_ao_regravar_nao_impede_o_login():
    usuario = {'id_usuario': 5, 'usuario': 'gestor.x', 'senha': 'antiga-texto', 'role': 'sompo'}
    client = app.app.test_client()
    with patch('app.PAINEL_SENHA', 'liga-o-login'), \
         patch('app.buscar_usuario', return_value=usuario), \
         patch('app.atualizar_tabela', side_effect=RuntimeError('banco fora')):
        assert client.post('/login', data={'usuario': 'gestor.x', 'senha': 'antiga-texto'}).status_code == 302


def test_senha_bloqueada_nunca_entra():
    for digitada in ('!', '', 'qualquer'):
        status, _ = _login('!', digitada)
        assert status == 401


def test_cadastro_de_usuario_grava_hash_e_nunca_a_senha():
    client = app.app.test_client()
    with patch('app.inserir_tabela', return_value={'id_usuario': 9, 'usuario': 'novo'}) as inserir:
        resposta = client.post('/usuarios', json={'usuario': 'novo', 'senha': 'segredo-longo-9', 'role': 'sompo'})
    assert resposta.status_code == 201
    payload = inserir.call_args.args[1]
    assert payload['senha'] != 'segredo-longo-9' and check_password_hash(payload['senha'], 'segredo-longo-9')
