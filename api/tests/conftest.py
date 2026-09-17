"""Configuração compartilhada dos testes."""
from unittest.mock import patch

import pytest

import llm


@pytest.fixture(autouse=True)
def _postgrest_offline():
    """Legados não têm cadastro; chamadas novas devem fornecer fixture explícita."""
    def responder(method, table, params=None, payload=None):
        if method == 'GET' and table == 'equipamentos':
            return []
        raise AssertionError(f'Consulta PostgREST sem fixture: {method} {table}')
    with patch('supabase_client._request_json', side_effect=responder):
        yield


@pytest.fixture(autouse=True)
def _limpar_cache_llm():
    # Zera o cache da analise antes e depois de cada teste, para um teste nao
    # reaproveitar a resposta (mockada) de outro.
    llm.limpar_cache()
    yield
    llm.limpar_cache()


@pytest.fixture(autouse=True)
def _auth_desligada_por_padrao():
    # Testes rodam em modo demo (sem API key e sem login do painel),
    # independente do que estiver no .env local. Os testes de auth
    # (test_auth.py) fazem patch proprio para ligar a trava quando precisam.
    with patch('app.SOMPO_API_KEY', ''), patch('app.PAINEL_SENHA', ''):
        yield
