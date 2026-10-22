"""Rota /telemetria/linha-do-tempo: faixas do banco, alarmes, sessoes e crachas recusados numa resposta."""
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app import app
from supabase_client import FuncaoAusente

FIM = datetime(2026, 10, 23, 1, 20, tzinfo=timezone.utc)   # 22/10 22:20 em Brasilia
BRT = timezone(timedelta(hours=-3))


def _faixas(inicio, fim, minutos, motor=False):
    out, t = [], inicio
    while t < fim:
        out.append({'inicio': t.isoformat(), 'leituras': 3, 'motor_ligado': motor, 'temp_max': 30.0, 'risco': None})
        t += timedelta(minutes=minutos)
    return out


def _get(url, eq=None, faixas=None, eventos=(), sessoes=(), negadas=(), ultima=FIM, ausente=False, linhas=()):
    chamadas = {}

    def f_faixas(dispositivo, equipamento, inicio, fim, minutos):
        chamadas['faixas'] = (equipamento, inicio, fim, minutos)
        if ausente:
            raise FuncaoAusente()
        return faixas(inicio, fim, minutos) if callable(faixas) else _faixas(inicio, fim, minutos)

    def f_eventos(dispositivo, dias=7, equipamento=None, janela=None):
        chamadas['eventos'] = janela
        return list(eventos)

    with ExitStack() as s:
        s.enter_context(patch('frota.id_selecionado', return_value=eq))
        s.enter_context(patch('app.consultar_telemetria', return_value=[{'criado_em': ultima.isoformat()}] if ultima else []))
        s.enter_context(patch('app.consultar_faixas', side_effect=f_faixas))
        s.enter_context(patch('app.consultar_eventos', side_effect=f_eventos))
        s.enter_context(patch('app.consultar_sessoes_janela', return_value=list(sessoes)))
        s.enter_context(patch('app.consultar_negadas', return_value=list(negadas)))
        s.enter_context(patch('app.consultar_telemetria_intervalo', return_value=list(linhas)))
        r = app.test_client().get(url)
    return r, chamadas


def test_rota_24h_usa_a_funcao_com_faixas_de_5_min():
    r, c = _get('/telemetria/linha-do-tempo?dispositivo=SOMPO-ESP32&horas=24')
    d = r.get_json()
    assert r.status_code == 200
    assert c['faixas'] == (None, FIM - timedelta(hours=24), FIM, 5)
    assert d['janela'] == {'inicio': (FIM - timedelta(hours=24)).isoformat(), 'fim': FIM.isoformat(), 'minutos': 5, 'tipo': 'horas'}
    assert len(d['faixas']) == 288
    assert d['limites'] == {'atencao': 450, 'critico': 550} and d['omitidos'] == 0


def test_rota_7_dias_usa_faixas_de_30_min():
    r, c = _get('/telemetria/linha-do-tempo?dispositivo=SOMPO-ESP32&horas=168')
    assert c['faixas'][3] == 30 and len(r.get_json()['faixas']) == 336


def test_rota_periodo_usa_dias_de_brasilia():
    r, c = _get('/telemetria/linha-do-tempo?dispositivo=SOMPO-ESP32&de=2026-09-21&ate=2026-10-21')
    d = r.get_json()
    assert c['faixas'][1] == datetime(2026, 9, 21, tzinfo=BRT)
    assert c['faixas'][2] == datetime(2026, 10, 22, tzinfo=BRT)   # o fim ja passou: nao corta no agora
    assert c['faixas'][3] == 120 and d['janela']['tipo'] == 'periodo'


def test_rota_periodo_sem_leituras_tem_janela():
    r, _ = _get('/telemetria/linha-do-tempo?dispositivo=SOMPO-ESP32&de=2026-09-21&ate=2026-09-21', ultima=None,
                faixas=lambda i, f, m: [{**x, 'leituras': 0, 'temp_max': None} for x in _faixas(i, f, m)])
    d = r.get_json()
    assert d['janela']['minutos'] == 5 and len(d['faixas']) == 288 and d['eventos'] == []


def test_rota_sem_nenhuma_leitura_em_horas():
    r, _ = _get('/telemetria/linha-do-tempo?dispositivo=SOMPO-ESP32', ultima=None)
    d = r.get_json()
    assert d['faixas'] == [] and d['janela'] is None


def test_rota_junta_alarmes_sessoes_negadas_e_rotina_em_ordem():
    t = lambda h, m: (FIM - timedelta(hours=24) + timedelta(hours=h, minutes=m)).isoformat()
    eventos = [{'id': 5, 'tipo': 'escape_critico', 'criado_em': t(11, 31), 'severidade': 4, 'temp_escape': 63, 'detalhes': {'limiar_c': 60}},
               {'id': 6, 'tipo': 'furto_capo', 'criado_em': t(4, 0), 'severidade': 2, 'temp_escape': None, 'detalhes': None}]
    sessoes = [{'sessao_id': 'abc', 'inicio_em': t(8, 58), 'fim_em': t(13, 42), 'operador_nome': 'João Silva', 'status': 'encerrada'}]
    negadas = [{'registro_id': 'n1', 'ocorrido_em': None, 'recebido_em': t(15, 4), 'uid': '4A1F9C02', 'motivo': None}]
    r, c = _get('/telemetria/linha-do-tempo?dispositivo=SOMPO-ESP32&horas=24', eq=1, eventos=eventos, sessoes=sessoes, negadas=negadas)
    d = r.get_json()
    ems = [e['em'] for e in d['eventos']]
    assert ems == sorted(ems, key=lambda s: datetime.fromisoformat(s))
    por_tipo = {e['tipo']: e for e in d['eventos']}
    assert por_tipo['escape_critico']['eixo'] == 'incendio' and por_tipo['escape_critico']['sev'] == 'critico'
    assert por_tipo['furto_capo']['sev'] == 'atencao'
    assert por_tipo['cracha_inicio']['operador_nome'] == 'João Silva' and por_tipo['cracha_inicio']['eixo'] == 'rotina'
    assert por_tipo['cracha_fim']['duracao_min'] == 284
    assert por_tipo['cracha_negado'] == {**por_tipo['cracha_negado'], 'em': t(15, 4), 'eixo': 'furto', 'sev': 'atencao', 'uid': '4A1F9C02'}
    assert d['sessoes'] == [{'inicio': t(8, 58), 'fim': t(13, 42), 'operador_nome': 'João Silva', 'status': 'encerrada'}]
    assert d['resumo']['incendio'] == 1 and d['resumo']['furto'] == 2   # o cracha recusado conta como furto
    assert d['limites']['critico'] == 60
    assert len({e['id'] for e in d['eventos']}) == len(d['eventos'])
    assert c['eventos'][0] == FIM - timedelta(hours=24) and c['eventos'][1] > FIM


def test_rota_corta_rotina_e_conta_omitidos():
    base = FIM - timedelta(hours=24)
    sessoes = [{'sessao_id': str(i), 'inicio_em': (base + timedelta(seconds=20 * i)).isoformat(),
                'fim_em': (base + timedelta(seconds=20 * i + 10)).isoformat(), 'operador_nome': 'A', 'status': 'encerrada'}
               for i in range(3000)]
    eventos = [{'id': i, 'tipo': 'furto_capo', 'criado_em': (base + timedelta(hours=1, minutes=i)).isoformat(),
                'severidade': 2, 'temp_escape': None, 'detalhes': None} for i in range(7)]
    d = _get('/telemetria/linha-do-tempo?dispositivo=SOMPO-ESP32&horas=24', eq=1, eventos=eventos, sessoes=sessoes)[0].get_json()
    assert len(d['eventos']) == 1000 and d['omitidos'] == 5007
    assert sum(e['tipo'] == 'furto_capo' for e in d['eventos']) == 7
    assert d['resumo']['furto'] == 7


def test_sem_maquina_nao_busca_sessoes_nem_negadas():
    with patch('app.consultar_sessoes_janela') as ses, patch('app.consultar_negadas') as neg:
        r, _ = _get('/telemetria/linha-do-tempo?dispositivo=SOMPO-ESP32&horas=24')
    assert r.status_code == 200 and not ses.called and not neg.called
    assert r.get_json()['sessoes'] == []


def test_sem_funcao_24h_cai_no_python():
    linhas = [{'criado_em': (FIM - timedelta(minutes=1)).isoformat(), 'motor_ligado': True, 'nivel_risco': 'SEGURO', 'temp_escape': 41}]
    r, _ = _get('/telemetria/linha-do-tempo?dispositivo=SOMPO-ESP32&horas=24', ausente=True, linhas=linhas)
    d = r.get_json()
    assert r.status_code == 200 and len(d['faixas']) == 288 and d['faixas'][-1]['temp_max'] == 41


def test_sem_funcao_7_dias_devolve_sql_pendente():
    r, _ = _get('/telemetria/linha-do-tempo?dispositivo=SOMPO-ESP32&horas=168', ausente=True)
    assert r.status_code == 409 and r.get_json()['erro'] == 'sql_pendente'


def test_horas_fora_do_limite_e_periodo_invalido():
    _, c = _get('/telemetria/linha-do-tempo?dispositivo=SOMPO-ESP32&horas=169')
    assert c['faixas'][1] == FIM - timedelta(hours=24)   # como o _parse_int de hoje: fora do limite volta ao padrao
    r, _ = _get('/telemetria/linha-do-tempo?dispositivo=SOMPO-ESP32&de=2026-09-21')
    assert r.status_code == 400 and r.get_json()['erro'] == 'periodo_invalido'
