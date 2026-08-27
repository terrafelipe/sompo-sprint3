"""Configuração compartilhada dos testes."""
import pytest

import llm


@pytest.fixture(autouse=True)
def _limpar_cache_llm():
    # Zera o cache da analise antes e depois de cada teste, para um teste nao
    # reaproveitar a resposta (mockada) de outro.
    llm.limpar_cache()
    yield
    llm.limpar_cache()
