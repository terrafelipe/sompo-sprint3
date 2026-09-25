"""`dias` fora de 1..365 vira 400 (antes 999999 estourava a data e dava 502)."""
from unittest.mock import patch

import pytest

import app

ROTAS = ['/eventos', '/resumo', '/scores', '/relatorio/bruto', '/relatorio/risco', '/relatorio/risco.pdf']


@pytest.mark.parametrize('rota', ROTAS)
@pytest.mark.parametrize('dias', ['999999', '0', '-3', 'abc', '366'])
def test_dias_invalido_da_400_sem_consultar_o_banco(rota, dias):
    client = app.app.test_client()
    with patch('app._dispositivo_para', return_value='ESP-1'), \
         patch('app.consultar_eventos') as eventos, patch('app.consultar_resumo') as resumo:
        resposta = client.get(f'{rota}?equipamento=1&dias={dias}')
    assert resposta.status_code == 400
    assert resposta.json == {'erro': 'dias_invalido'}
    eventos.assert_not_called()
    resumo.assert_not_called()


@pytest.mark.parametrize('rota,funcao', [('/eventos', 'consultar_eventos'), ('/resumo', 'consultar_resumo'),
                                         ('/scores', 'consultar_eventos')])
@pytest.mark.parametrize('dias', ['1', '90', '365'])
def test_dias_valido_segue(rota, funcao, dias):
    client = app.app.test_client()
    with patch('app._dispositivo_para', return_value='ESP-1'), patch(f'app.{funcao}', return_value=[]) as consulta:
        resposta = client.get(f'{rota}?equipamento=1&dias={dias}')
    assert resposta.status_code == 200
    assert consulta.call_args.kwargs['dias'] == int(dias)
