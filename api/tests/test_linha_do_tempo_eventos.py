"""Calculos puros da linha do tempo: faixa pela janela, severidade, limites, eventos de rotina e corte."""
from datetime import datetime, timedelta, timezone

from linha_do_tempo import (agregar, cortar, eixo, eventos_rotina, limites, minutos_para,
                            normalizar_alarme, resumo, severidade)

BRT = timezone(timedelta(hours=-3))
DIA = datetime(2026, 10, 22, tzinfo=BRT)


def _h(h, m=0):
    return DIA + timedelta(hours=h, minutes=m)


def _faixas(de, ate, minutos=5, motor=(), vazias=(), temps=None):
    """Faixas de `de` ate `ate` (exclusivo). motor/vazias: listas de (inicio, fim) em datetime."""
    dentro = lambda t, trechos: any(a <= t < b for a, b in trechos)
    out, t = [], de
    while t < ate:
        vazia = dentro(t, vazias)
        out.append({'inicio': t.isoformat(), 'leituras': 0 if vazia else 30,
                    'motor_ligado': (not vazia) and dentro(t, motor),
                    'temp_max': None if vazia else (temps or {}).get(t, 30.0), 'risco': None})
        t += timedelta(minutes=minutos)
    return out


def _alarme(tipo, em, limiar=None, sev=None):
    return normalizar_alarme({'id': 1, 'tipo': tipo, 'criado_em': em.isoformat(), 'severidade': sev,
                              'temp_escape': None, 'detalhes': {'limiar_c': limiar} if limiar else None})


def _de(eventos, tipo):
    return [e for e in eventos if e['tipo'] == tipo]


def test_minutos_para_escolhe_a_faixa_pela_janela():
    assert minutos_para(_h(0), _h(24)) == 5
    assert minutos_para(_h(0), _h(0) + timedelta(hours=168)) == 30
    assert minutos_para(_h(0), _h(0) + timedelta(days=31)) == 120
    assert minutos_para(_h(0), _h(0) + timedelta(days=365)) == 1440
    assert minutos_para(_h(0), _h(2)) == 5


def test_agregar_traz_a_temperatura_maxima_da_faixa():
    fim = _h(20)
    linhas = [{'criado_em': (fim - timedelta(minutes=m)).isoformat(), 'motor_ligado': False,
               'nivel_risco': 'SEGURO', 'temp_escape': t} for m, t in ((1, 40), (2, 63))]
    faixas = agregar(linhas, fim, horas=24, minutos=15)
    assert faixas[-1]['temp_max'] == 63
    assert faixas[0]['temp_max'] is None


def test_agregar_aceita_o_inicio_do_periodo():
    faixas = agregar([], _h(24), minutos=60, inicio=_h(0))
    assert len(faixas) == 24 and faixas[0]['inicio'] == _h(0).isoformat()


def test_severidade_pelo_numero_e_pelo_tipo():
    assert severidade({'tipo': 'escape_atencao', 'severidade': 4}) == 'critico'
    assert severidade({'tipo': 'escape_critico', 'severidade': 2}) == 'atencao'
    assert severidade({'tipo': 'sensor_falha'}) == 'critico'
    assert severidade({'tipo': 'furto_capo'}) == 'atencao'


def test_eixo_do_tipo():
    assert eixo('chama_detectada') == 'incendio' and eixo('escape_atencao') == 'incendio'
    assert eixo('furto_capo') == 'furto' and eixo('operador_nao_autorizado') == 'furto'


def test_limites_do_ultimo_alarme_de_cada_tipo_e_padrao():
    assert limites([_alarme('escape_atencao', _h(9), 35), _alarme('escape_atencao', _h(10), 40),
                    _alarme('escape_critico', _h(10), 60)]) == {'atencao': 40, 'critico': 60}
    assert limites([]) == {'atencao': 450, 'critico': 550}
    assert limites([_alarme('escape_atencao', _h(9), 40)]) == {'atencao': 40, 'critico': 550}


def test_motor_liga_e_para_nas_bordas_dos_trechos():
    faixas = _faixas(_h(6), _h(13), motor=[(_h(7), _h(11, 40))])
    sessao = [{'inicio': _h(6, 58).isoformat(), 'fim': _h(11, 42).isoformat(), 'operador_nome': 'João', 'status': 'encerrada'}]
    ev = eventos_rotina(faixas, 5, sessao, [], limites([]))
    (liga,), (para,) = _de(ev, 'motor_ligou'), _de(ev, 'motor_parou')
    assert liga['em'] == _h(7).isoformat() and liga['com_cracha'] is True
    assert para['em'] == _h(11, 40).isoformat() and para['duracao_min'] == 280
    assert _de(eventos_rotina(faixas, 5, [], [], limites([])), 'motor_ligou')[0]['com_cracha'] is False
    assert _de(eventos_rotina(faixas, 5, None, [], limites([])), 'motor_ligou')[0]['com_cracha'] is None


def test_motor_ligado_desde_o_inicio_da_janela_nao_vira_partida():
    ev = eventos_rotina(_faixas(_h(7), _h(13), motor=[(_h(7), _h(9))]), 5, [], [], limites([]))
    assert _de(ev, 'motor_ligou') == [] and len(_de(ev, 'motor_parou')) == 1


def test_lacuna_de_envio_nao_quebra_o_trecho_de_motor():
    faixas = _faixas(_h(6), _h(13), motor=[(_h(7), _h(11))], vazias=[(_h(9), _h(9, 20))])
    ev = eventos_rotina(faixas, 5, [], [], limites([]))
    assert len(_de(ev, 'motor_ligou')) == 1 and len(_de(ev, 'motor_parou')) == 1
    (parou,), (voltou,) = _de(ev, 'envio_parou'), _de(ev, 'envio_voltou')
    assert parou['em'] == _h(9).isoformat() and parou['duracao_min'] == 20
    assert voltou['em'] == _h(9, 20).isoformat()


def test_lacuna_curta_nao_vira_evento():
    curta = _faixas(_h(6), _h(13), vazias=[(_h(9), _h(9, 10))])
    assert _de(eventos_rotina(curta, 5, [], [], limites([])), 'envio_parou') == []
    uma_faixa = _faixas(_h(0), _h(24), minutos=30, vazias=[(_h(9), _h(9, 30))])
    assert _de(eventos_rotina(uma_faixa, 30, [], [], limites([])), 'envio_parou') == []
    nas_bordas = _faixas(_h(6), _h(13), vazias=[(_h(6), _h(8)), (_h(11), _h(13))])
    assert _de(eventos_rotina(nas_bordas, 5, [], [], limites([])), 'envio_parou') == []


def test_temperatura_volta_ao_normal_depois_do_alarme():
    temps = {_h(9, 30): 63.0, _h(9, 35): 55.0, _h(9, 40): 45.0, _h(9, 45): 38.0}
    faixas = _faixas(_h(8), _h(11), temps=temps)
    for f in faixas:   # antes do pico, quente; o 30 padrao so depois do 38
        if f['inicio'] < _h(9, 30).isoformat():
            f['temp_max'] = 50.0
    alarmes = [_alarme('escape_atencao', _h(9, 12), 40), _alarme('escape_critico', _h(9, 31), 60)]
    (normal,) = _de(eventos_rotina(faixas, 5, [], alarmes, limites(alarmes)), 'temp_normal')
    assert normal['em'] == _h(9, 45).isoformat() and normal['temp'] == 38
    quente = _faixas(_h(8), _h(11), temps={})
    for f in quente:
        f['temp_max'] = 70.0
    assert _de(eventos_rotina(quente, 5, [], alarmes, limites(alarmes)), 'temp_normal') == []


def test_cortar_mantem_todos_os_alarmes():
    alarmes = [{'tipo': 'furto_capo', 'eixo': 'furto', 'em': _h(0, i).isoformat()} for i in range(5)]
    rotina = [{'tipo': 'motor_ligou', 'eixo': 'rotina', 'em': (_h(0) + timedelta(minutes=i)).isoformat()} for i in range(2000)]
    eventos, omitidos = cortar(rotina + alarmes, maximo=1000)
    assert len(eventos) == 1000 and omitidos == 1005
    assert sum(e['eixo'] != 'rotina' for e in eventos) == 5
    assert min(e['em'] for e in eventos if e['eixo'] == 'rotina') == (_h(0) + timedelta(minutes=1005)).isoformat()
    assert [e['em'] for e in eventos] == sorted(e['em'] for e in eventos)


def test_resumo_conta_alarmes_motor_e_lacuna():
    faixas = _faixas(_h(6), _h(13), motor=[(_h(7), _h(8))], vazias=[(_h(9), _h(9, 30))])
    alarmes = [_alarme('escape_atencao', _h(7)), _alarme('chama_detectada', _h(7)), _alarme('furto_capo', _h(2))]
    assert resumo(alarmes, faixas, 5) == {'incendio': 2, 'furto': 1, 'motor_min': 60, 'sem_envio_min': 30}


def test_normalizar_alarme():
    a = normalizar_alarme({'id': 9, 'tipo': 'escape_critico', 'criado_em': '2026-10-22T12:31:00+00:00',
                           'severidade': 4, 'temp_escape': 63.2, 'detalhes': {'limiar_c': 60}})
    assert a == {'id': 'a9', 'tipo': 'escape_critico', 'eixo': 'incendio', 'sev': 'critico',
                 'em': '2026-10-22T12:31:00+00:00', 'temp': 63.2, 'limiar_c': 60}
