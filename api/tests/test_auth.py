"""Testes da trava de acesso por API key (header X-API-Key).

A auth e opt-in: so age quando SOMPO_API_KEY esta configurada. O before_request
'exigir_api_key' le a global SOMPO_API_KEY do modulo app, entao os testes fazem
patch em 'app.SOMPO_API_KEY' para ligar/desligar a trava sem tocar no .env.
"""
from unittest.mock import patch

from app import app

_CHAVE = 'chave-secreta-de-teste'


def test_sem_chave_configurada_libera_geral():
    # Modo demo: SOMPO_API_KEY vazia -> nenhuma rota exige header.
    client = app.test_client()
    with patch('app.SOMPO_API_KEY', ''), \
         patch('app.consultar_telemetria', return_value=[]):
        response = client.get('/telemetria')
    assert response.status_code == 200


def test_rota_protegida_sem_header_retorna_401():
    client = app.test_client()
    with patch('app.SOMPO_API_KEY', _CHAVE):
        response = client.get('/telemetria')
    assert response.status_code == 401
    assert response.get_json()['erro'] == 'nao_autorizado'


def test_rota_protegida_com_header_errado_retorna_401():
    client = app.test_client()
    with patch('app.SOMPO_API_KEY', _CHAVE):
        response = client.get('/telemetria', headers={'X-API-Key': 'chave-errada'})
    assert response.status_code == 401
    assert response.get_json()['erro'] == 'nao_autorizado'


def test_rota_protegida_com_header_correto_passa():
    client = app.test_client()
    with patch('app.SOMPO_API_KEY', _CHAVE), \
         patch('app.consultar_telemetria', return_value=[]):
        response = client.get('/telemetria', headers={'X-API-Key': _CHAVE})
    assert response.status_code == 200
    assert response.get_json()['total'] == 0


def test_saude_fica_de_fora_da_trava():
    # Health check e rota publica: responde mesmo com a auth ligada e sem header.
    client = app.test_client()
    with patch('app.SOMPO_API_KEY', _CHAVE), \
         patch('supabase_client.consultar_tabela', return_value=[{'id': 1}]):
        response = client.get('/saude')
    assert response.status_code == 200


def test_api_key_valida_passa_mesmo_com_login_ligado():
    # Login do painel + API key ligados: cliente de API (sem sessao) entra pela chave.
    client = app.test_client()
    with patch('app.PAINEL_SENHA', 'senha-do-painel'), \
         patch('app.SOMPO_API_KEY', _CHAVE), \
         patch('app.consultar_telemetria', return_value=[]):
        response = client.get('/telemetria', headers={'X-API-Key': _CHAVE})
    assert response.status_code == 200


def test_sem_sessao_e_sem_chave_com_login_ligado_retorna_401():
    # Sem navegador (sem sessao) e sem a chave: barrado.
    client = app.test_client()
    with patch('app.PAINEL_SENHA', 'senha-do-painel'), \
         patch('app.SOMPO_API_KEY', _CHAVE):
        response = client.get('/telemetria')
    assert response.status_code == 401
