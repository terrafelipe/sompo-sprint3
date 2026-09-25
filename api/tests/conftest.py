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
def _limpar_cache_de_revalidacao():
    # A revalidacao da sessao fica 20 s em cache por usuario: um teste nao herda a do outro.
    import app as app_mod
    app_mod._revalidados.clear()
    app_mod._falhas_login.clear()   # limite de tentativas do /login: um teste nao herda o do outro
    yield
    app_mod._revalidados.clear()
    app_mod._falhas_login.clear()


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


@pytest.fixture
def pdf_aberto(monkeypatch):
    """Gera o PDF sem compressão, para o teste ler o texto direto dos bytes."""
    import documento

    class SemCompressao(documento.RelatorioPDF):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.compress = False

    monkeypatch.setattr(documento, 'RelatorioPDF', SemCompressao)
