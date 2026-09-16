"""Testes da aba Usuários: listagem e criação de logins do painel.

Rodam em modo demo (fixture autouse em conftest.py desliga API key + login), então
o perfil padrão é 'sompo' e o @somente_sompo libera. As funções de banco são mockadas.
"""
from unittest.mock import patch

from app import app


def test_usuarios_listar():
    client = app.test_client()
    fake = [{'id_usuario': 1, 'usuario': 'sompo', 'role': 'sompo',
             'fk_fazenda_id_fazenda': None, 'fazenda': None}]
    with patch('app.consultar_usuarios', return_value=fake):
        response = client.get('/usuarios')
    assert response.status_code == 200
    data = response.get_json()
    assert data['total'] == 1
    assert data['dados'][0]['usuario'] == 'sompo'


def test_criar_usuario_sompo_ok():
    client = app.test_client()
    retorno = {'id_usuario': 2, 'usuario': 'novo', 'role': 'sompo', 'senha': 'x'}
    with patch('app.inserir_tabela', return_value=retorno) as ins:
        response = client.post('/usuarios', json={'usuario': 'novo', 'senha': 'segredo', 'role': 'sompo'})
    assert response.status_code == 201
    corpo = response.get_json()
    assert corpo['ok'] is True
    # A senha nunca volta na resposta.
    assert 'senha' not in corpo['usuario']
    # Inseriu na tabela 'usuario'.
    assert ins.call_args[0][0] == 'usuario'


def test_criar_usuario_gestor_exige_fazenda():
    client = app.test_client()
    with patch('app.inserir_tabela') as ins:
        response = client.post('/usuarios', json={'usuario': 'g', 'senha': 's', 'role': 'gestor_fazenda'})
    assert response.status_code == 400
    assert response.get_json()['erro'] == 'fazenda_obrigatoria'
    ins.assert_not_called()


def test_criar_usuario_gestor_com_fazenda_ok():
    client = app.test_client()
    retorno = {'id_usuario': 3, 'usuario': 'g', 'role': 'gestor_fazenda'}
    with patch('app.inserir_tabela', return_value=retorno) as ins:
        response = client.post('/usuarios', json={
            'usuario': 'g', 'senha': 's', 'role': 'gestor_fazenda', 'fk_fazenda_id_fazenda': 5})
    assert response.status_code == 201
    # A fazenda vai no payload já como int.
    assert ins.call_args[0][1]['fk_fazenda_id_fazenda'] == 5


def test_criar_usuario_sem_usuario_400():
    client = app.test_client()
    with patch('app.inserir_tabela') as ins:
        response = client.post('/usuarios', json={'senha': 's', 'role': 'sompo'})
    assert response.status_code == 400
    assert response.get_json()['erro'] == 'usuario_obrigatorio'
    ins.assert_not_called()


def test_criar_usuario_role_invalida_400():
    client = app.test_client()
    with patch('app.inserir_tabela') as ins:
        response = client.post('/usuarios', json={'usuario': 'x', 'senha': 's', 'role': 'admin'})
    assert response.status_code == 400
    assert response.get_json()['erro'] == 'role_invalida'
    ins.assert_not_called()


def test_criar_usuario_duplicado_409():
    client = app.test_client()
    erro = RuntimeError('Erro ao inserir no Supabase: 409 - duplicate key value (23505)')
    with patch('app.inserir_tabela', side_effect=erro):
        response = client.post('/usuarios', json={'usuario': 'sompo', 'senha': 's', 'role': 'sompo'})
    assert response.status_code == 409
    assert response.get_json()['erro'] == 'usuario_ja_existe'


def test_usuarios_proibido_para_gestor():
    # O perfil gestor_fazenda não acessa o cadastro de usuários (@somente_sompo).
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['role'] = 'gestor_fazenda'
    response = client.get('/usuarios')
    assert response.status_code == 403
    assert response.get_json()['erro'] == 'proibido'
