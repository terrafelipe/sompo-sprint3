"""Linha do tempo de 24h do Painel da maquina: faixas de 15 min ate a ultima leitura."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app import app
from linha_do_tempo import agregar

FIM = datetime(2026, 9, 19, 20, 0, tzinfo=timezone.utc)


def _leitura(min_antes, motor=False, risco='SEGURO'):
    return {'criado_em': (FIM - timedelta(minutes=min_antes)).isoformat(),
            'motor_ligado': motor, 'nivel_risco': risco}


def test_agrega_em_faixas_de_15_min_ate_a_ultima_leitura():
    faixas = agregar([_leitura(0, True, 'ATENCAO'), _leitura(5, False, 'CRITICO'),
                      _leitura(20), _leitura(24 * 60 + 10)], FIM, horas=24, minutos=15)
    assert len(faixas) == 96
    assert faixas[0]['inicio'] == (FIM - timedelta(hours=24)).isoformat()
    ultima = faixas[-1]                      # [19:45, 20:00]: duas leituras
    assert ultima['leituras'] == 2
    assert ultima['motor_ligado'] is True    # basta uma leitura com motor ligado
    assert ultima['risco'] == 'CRITICO'      # pior nivel da faixa
    assert faixas[-2]['leituras'] == 1 and faixas[-2]['motor_ligado'] is False
    assert sum(f['leituras'] for f in faixas) == 3   # a de 24h10 atras fica fora
    assert faixas[10] == {'inicio': faixas[10]['inicio'], 'leituras': 0, 'motor_ligado': False, 'risco': None}


def test_rota_usa_a_janela_das_24h_ate_a_ultima_leitura():
    janelas = []
    def intervalo(_disp, inicio, fim):
        janelas.append((inicio, fim))
        return [_leitura(0, True)]
    with patch('app.consultar_telemetria', return_value=[{'criado_em': FIM.isoformat()}]), \
         patch('app.consultar_telemetria_intervalo', side_effect=intervalo):
        d = app.test_client().get('/telemetria/linha-do-tempo?dispositivo=SOMPO-ESP32&horas=24').get_json()
    assert janelas == [(FIM - timedelta(hours=24), FIM)]
    assert d['janela'] == {'inicio': (FIM - timedelta(hours=24)).isoformat(), 'fim': FIM.isoformat(), 'minutos': 15}
    assert len(d['faixas']) == 96 and d['faixas'][-1]['motor_ligado'] is True


def test_rota_sem_nenhuma_leitura():
    with patch('app.consultar_telemetria', return_value=[]):
        d = app.test_client().get('/telemetria/linha-do-tempo?dispositivo=SOMPO-ESP32').get_json()
    assert d['faixas'] == [] and d['janela'] is None
