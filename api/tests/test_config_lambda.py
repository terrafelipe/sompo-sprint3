"""Na Lambda o app nao sobe com configuracao que abre tudo (login desligado, cookie sem Secure...)."""
import importlib

import pytest

import config

SEGURA = {'AWS_LAMBDA_FUNCTION_NAME': 'sompo-painel', 'PAINEL_SENHA': 'liga', 'SECRET_KEY': 'fixa' * 16,
          'COOKIE_SEGURO': 'true', 'PROXY_SEGREDO': 'segredo-do-worker'}


@pytest.fixture
def recarregar(monkeypatch):
    def _recarregar(**env):
        for nome in SEGURA:
            monkeypatch.delenv(nome, raising=False)
        for nome, valor in env.items():
            monkeypatch.setenv(nome, valor)
        # load_dotenv nao sobrescreve o que ja esta no ambiente; o .env local nao interfere
        # porque as variaveis que faltam foram removidas ANTES e o teste so as define aqui.
        monkeypatch.setattr('dotenv.load_dotenv', lambda *a, **k: False)
        return importlib.reload(config)
    yield _recarregar
    monkeypatch.undo()
    importlib.reload(config)


def test_na_lambda_com_tudo_configurado_sobe(recarregar):
    assert recarregar(**SEGURA).PAINEL_SENHA == 'liga'


@pytest.mark.parametrize('falta', ['PAINEL_SENHA', 'SECRET_KEY', 'COOKIE_SEGURO', 'PROXY_SEGREDO'])
def test_na_lambda_sem_configuracao_segura_nao_sobe(recarregar, falta):
    env = {k: v for k, v in SEGURA.items() if k != falta}
    with pytest.raises(RuntimeError, match=falta):
        recarregar(**env)


def test_fora_da_lambda_modo_demo_continua_aberto(recarregar):
    assert recarregar().PAINEL_SENHA == ''
