"""Testes do controle de acesso por perfil (role-based).

O role vem da sessao (setado no login). Aqui usamos client.session_transaction()
para simular cada perfil. A conftest ja roda em modo demo (PAINEL_SENHA vazia), entao
o gate de login nao interfere - o que testamos e a camada de perfil (somente_sompo e
o escopo de dispositivo do gestor).
"""
from unittest.mock import patch

from app import app


def _login_como(client, role, dispositivo=None, fazenda_nome=None):
    with client.session_transaction() as sess:
        sess['logado'] = True
        sess['usuario'] = role
        sess['role'] = role
        sess['dispositivo_forcado'] = dispositivo
        sess['fazenda_nome'] = fazenda_nome


def test_gestor_nao_cadastra_fazenda():
    client = app.test_client()
    _login_como(client, 'gestor_fazenda', dispositivo='SOMPO-ESP32-SIM')
    with patch('app.inserir_tabela') as mock_inserir:
        response = client.post('/fazendas', json={'nome': 'Nova'})
    assert response.status_code == 403
    assert response.get_json()['erro'] == 'proibido'
    mock_inserir.assert_not_called()


def test_gestor_nao_cadastra_cliente():
    client = app.test_client()
    _login_como(client, 'gestor_fazenda', dispositivo='SOMPO-ESP32-SIM')
    with patch('app.inserir_tabela') as mock_inserir:
        response = client.post('/clientes', json={'nome': 'Fulano'})
    assert response.status_code == 403
    mock_inserir.assert_not_called()


def test_gestor_nao_lista_fazendas():
    client = app.test_client()
    _login_como(client, 'gestor_fazenda')
    response = client.get('/fazendas')
    assert response.status_code == 403


def test_sompo_cadastra_fazenda():
    client = app.test_client()
    _login_como(client, 'sompo')
    with patch('app.inserir_tabela', return_value={'id_fazenda': 1, 'nome': 'Nova'}):
        response = client.post('/fazendas', json={
            'nome': 'Nova', 'localizacao': 'SP', 'area_ha': '100', 'fk_cliente_id_cliente': '1',
        })
    assert response.status_code == 201


def test_sessao_legada_sem_fazenda_nao_libera_dispositivo():
    # Sessão antiga sem fazenda exige novo login; não reutiliza escopo de ESP32.
    client = app.test_client()
    _login_como(client, 'gestor_fazenda', dispositivo='SOMPO-ESP32-SIM')
    with patch('app.consultar_telemetria', return_value=[]) as mock_tel:
        response = client.get('/telemetria?dispositivo=SOMPO-ESP32')
    assert response.status_code == 403
    mock_tel.assert_not_called()


def test_sompo_ve_o_dispositivo_pedido():
    client = app.test_client()
    _login_como(client, 'sompo')
    with patch('app.consultar_telemetria', return_value=[]) as mock_tel:
        response = client.get('/telemetria?dispositivo=SOMPO-ESP32-SIM')
    assert response.status_code == 200
    assert mock_tel.call_args.args[0] == 'SOMPO-ESP32-SIM'


def test_me_reflete_o_perfil():
    client = app.test_client()
    _login_como(client, 'gestor_fazenda', dispositivo='SOMPO-ESP32-SIM', fazenda_nome='Vale Verde')
    response = client.get('/me')
    assert response.status_code == 200
    data = response.get_json()
    assert data['role'] == 'gestor_fazenda'
    assert data['fazenda_nome'] == 'Vale Verde'
    assert data['dispositivo'] == 'SOMPO-ESP32-SIM'
