"""Logo do cliente: link https validado no servidor, no cadastro (POST) e na troca (PATCH)."""
from unittest.mock import patch

import pytest

from app import app
from supabase_client import consultar_clientes
from tests.test_perfis import _login_como

CLIENTE = {'nome': 'Agro Um', 'cnpj': '00.000.000/0001-00', 'telefone': '11 9999-0000', 'endereco': 'Rua A'}
LOGO = 'https://exemplo.com/logo.png'
INVALIDOS = [
    'http://exemplo.com/logo.png',
    'javascript:alert(1)',
    'data:image/png;base64,AAAA',
    'https://' + 'a' * 493,  # 501 caracteres
    'https://exemplo.com/a b.png',
    'https://exemplo.com/"onerror=alert(1)',
    'https://exemplo.com/<script>',
    "https://exemplo.com/'x",
    123,
]


def _criar(corpo):
    with patch('app.inserir_tabela', side_effect=lambda tabela, dados: dados) as mock_inserir:
        response = app.test_client().post('/clientes', json=corpo)
    return response, mock_inserir


def _trocar(corpo, devolve=None):
    retorno = {'id_cliente': 5, 'logo_url': None} if devolve is None else devolve
    with patch('app.atualizar_tabela', return_value=retorno) as mock_atualizar:
        response = app.test_client().patch('/clientes/5', json=corpo)
    return response, mock_atualizar


def test_consulta_de_clientes_traz_o_logo():
    with patch('supabase_client.consultar_tabela', return_value=[]) as mock_consulta:
        consultar_clientes()
    assert 'logo_url' in mock_consulta.call_args.kwargs['select'].split(',')


def test_cadastro_aceita_logo_https():
    response, mock_inserir = _criar({**CLIENTE, 'logo_url': LOGO})
    assert response.status_code == 201
    assert mock_inserir.call_args.args[1]['logo_url'] == LOGO


def test_cadastro_limite_de_500_caracteres_aceito():
    logo = 'https://' + 'a' * 492
    assert len(logo) == 500
    response, mock_inserir = _criar({**CLIENTE, 'logo_url': logo})
    assert response.status_code == 201
    assert mock_inserir.call_args.args[1]['logo_url'] == logo


@pytest.mark.parametrize('logo', INVALIDOS)
def test_cadastro_rejeita_logo_invalido(logo):
    response, mock_inserir = _criar({**CLIENTE, 'logo_url': logo})
    assert response.status_code == 400
    assert response.get_json()['erro'] == 'logo_invalido'
    mock_inserir.assert_not_called()


@pytest.mark.parametrize('logo', ['', '   ', None])
def test_cadastro_logo_vazio_vira_nulo(logo):
    response, mock_inserir = _criar({**CLIENTE, 'logo_url': logo})
    assert response.status_code == 201
    assert mock_inserir.call_args.args[1].get('logo_url') is None


def test_troca_aceita_logo_https():
    response, mock_atualizar = _trocar({'logo_url': LOGO}, {'id_cliente': 5, 'logo_url': LOGO})
    assert response.status_code == 200
    assert response.get_json()['cliente']['logo_url'] == LOGO
    tabela, filtros, dados = mock_atualizar.call_args.args
    assert tabela == 'cliente'
    assert filtros == {'id_cliente': 'eq.5', 'excluido_em': 'is.null'}
    assert dados == {'logo_url': LOGO}


@pytest.mark.parametrize('logo', INVALIDOS)
def test_troca_rejeita_logo_invalido(logo):
    response, mock_atualizar = _trocar({'logo_url': logo})
    assert response.status_code == 400
    assert response.get_json()['erro'] == 'logo_invalido'
    mock_atualizar.assert_not_called()


@pytest.mark.parametrize('logo', ['', '  ', None])
def test_troca_logo_vazio_remove(logo):
    response, mock_atualizar = _trocar({'logo_url': logo})
    assert response.status_code == 200
    assert mock_atualizar.call_args.args[2] == {'logo_url': None}


def test_troca_muda_so_o_logo():
    response, mock_atualizar = _trocar({'logo_url': LOGO, 'nome': 'Outro', 'cnpj': 'x', 'excluido_em': None})
    assert response.status_code == 200
    assert mock_atualizar.call_args.args[2] == {'logo_url': LOGO}


def test_troca_sem_logo_no_corpo_nao_altera_nada():
    response, mock_atualizar = _trocar({'nome': 'Outro'})
    assert response.status_code == 400
    assert response.get_json()['erro'] == 'nada_para_atualizar'
    mock_atualizar.assert_not_called()


def test_troca_de_cliente_inexistente_da_404():
    response, _ = _trocar({'logo_url': LOGO}, {})
    assert response.status_code == 404


def test_gestor_nao_troca_logo():
    client = app.test_client()
    _login_como(client, 'gestor_fazenda', dispositivo='SOMPO-ESP32-SIM')
    with patch('app.atualizar_tabela') as mock_atualizar:
        response = client.patch('/clientes/5', json={'logo_url': LOGO})
    assert response.status_code == 403
    mock_atualizar.assert_not_called()


def test_gestor_nao_cadastra_cliente_com_logo():
    client = app.test_client()
    _login_como(client, 'gestor_fazenda', dispositivo='SOMPO-ESP32-SIM')
    with patch('app.inserir_tabela') as mock_inserir:
        response = client.post('/clientes', json={**CLIENTE, 'logo_url': LOGO})
    assert response.status_code == 403
    mock_inserir.assert_not_called()
