"""Últimas leituras por período (De/Até), em páginas, no horário de Brasília."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import supabase_client as db
from tests.test_frota import banco, gestor  # noqa: F401

BRT = timezone(timedelta(hours=-3))


def test_cliente_pede_uma_linha_a_mais_para_saber_se_ha_proxima_pagina():
    chamadas = []

    def query(method, table, params=None, payload=None):
        chamadas.append(params.copy())
        return []
    inicio = datetime(2026, 9, 21, tzinfo=BRT)
    fim = datetime(2026, 10, 22, tzinfo=BRT)
    with patch.object(db, '_request_json', side_effect=query):
        db.consultar_telemetria_periodo('ESP-A', inicio, fim, pagina=3, por_pagina=50, equipamento=2)
    p = chamadas[0]
    assert p['equipamento_id'] == 'eq.2'
    assert p['criado_em'] == f'gte.{inicio.isoformat()}'
    assert p['and'] == f'(criado_em.lt.{fim.isoformat()})'
    assert p['order'] == 'criado_em.desc,id.desc'     # desempate: leituras com o mesmo criado_em nao se repetem entre paginas
    assert (p['limit'], p['offset']) == ('51', '100')
    assert p['select'] == '*'


def test_periodo_fecha_o_dia_final_inteiro_no_horario_de_brasilia(banco):
    with patch('app.consultar_telemetria_periodo', return_value=[]) as consulta:
        r = gestor().get('/telemetria?equipamento=1&de=2026-09-21&ate=2026-10-01')
    assert r.status_code == 200
    args = consulta.call_args
    assert args.args[1] == datetime(2026, 9, 21, tzinfo=BRT)
    assert args.args[2] == datetime(2026, 10, 2, tzinfo=BRT)       # 01/10 inclusive: corta em 02/10 00:00
    assert args.kwargs['pagina'] == 1


def test_sem_corte_o_servidor_usa_o_agora_e_devolve_o_corte_para_as_proximas_paginas(banco):
    antes = datetime.now(timezone.utc)
    with patch('app.consultar_telemetria_periodo', return_value=[]) as consulta:
        r = gestor().get('/telemetria?equipamento=1&de=2026-10-01&ate=2027-01-01')   # "ate" no futuro: fim cai no agora
    fim = consulta.call_args.args[2]
    assert antes <= fim <= datetime.now(timezone.utc)
    assert datetime.fromisoformat(r.json['corte']) == fim


def test_periodo_passado_devolve_como_corte_o_fim_do_periodo(banco):
    with patch('app.consultar_telemetria_periodo', return_value=[]):
        r = gestor().get('/telemetria?equipamento=1&de=2026-09-21&ate=2026-10-01')
    assert datetime.fromisoformat(r.json['corte']) == datetime(2026, 10, 2, tzinfo=BRT)


def test_corte_congela_o_limite_superior_para_a_paginacao_nao_repetir_linhas(banco):
    with patch('app.consultar_telemetria_periodo', return_value=[]) as consulta:
        r = gestor().get('/telemetria?equipamento=1&de=2026-10-01&ate=2026-10-21&corte=2026-10-05T12:00:00.000Z')
    assert r.status_code == 200
    assert consulta.call_args.args[2] == datetime(2026, 10, 5, 12, tzinfo=timezone.utc)


def test_corte_depois_do_fim_do_periodo_nao_amplia_o_periodo(banco):
    with patch('app.consultar_telemetria_periodo', return_value=[]) as consulta:
        r = gestor().get('/telemetria?equipamento=1&de=2026-10-01&ate=2026-10-01&corte=2026-12-01T00:00:00Z')
    assert r.status_code == 200
    assert consulta.call_args.args[2] == datetime(2026, 10, 2, tzinfo=BRT)


def test_corte_invalido_ou_sem_fuso_da_400(banco):
    for corte in ('ontem', '2026-10-05T12:00:00', '2026-13-05T12:00:00Z'):
        with patch('app.consultar_telemetria_periodo', return_value=[]) as consulta:
            r = gestor().get(f'/telemetria?equipamento=1&de=2026-10-01&ate=2026-10-21&corte={corte}')
        assert (r.status_code, r.json['erro']) == (400, 'periodo_invalido'), corte
        consulta.assert_not_called()


def test_resposta_traz_pagina_e_tem_mais_sem_a_linha_extra(banco):
    linhas = [{'criado_em': f'2026-10-01T00:{i % 60:02d}:00+00:00'} for i in range(51)]
    with patch('app.consultar_telemetria_periodo', return_value=linhas):
        r = gestor().get('/telemetria?equipamento=1&de=2026-10-01&ate=2026-10-01&pagina=2')
    assert r.status_code == 200
    assert (r.json['pagina'], r.json['tem_mais']) == (2, True)
    assert len(r.json['dados']) == r.json['total'] == 50


def test_ultima_pagina_nao_tem_mais(banco):
    with patch('app.consultar_telemetria_periodo', return_value=[{'criado_em': '2026-10-01T00:00:00+00:00'}]):
        r = gestor().get('/telemetria?equipamento=1&de=2026-10-01&ate=2026-10-01')
    assert (r.json['pagina'], r.json['tem_mais'], r.json['total']) == (1, False, 1)


def test_periodos_invalidos_dao_400(banco):
    for qs in ('de=2026-10-01',                                # falta o Até
               'ate=2026-10-01',                               # falta o De
               'de=21/09/2026&ate=21/10/2026',                 # formato errado
               'de=2026-02-30&ate=2026-03-01',                 # dia inexistente
               'de=2026-10-21&ate=2026-09-21',                 # invertido
               'de=2025-01-01&ate=2026-10-01',                 # mais de 1 ano
               'de=2025-10-20&ate=2026-10-21',                 # 366 dias de diferenca: logo acima do limite
               'de=9999-12-31&ate=9999-12-31',                 # "ate"+1 dia estoura o calendario
               'de=2026-10-01&ate=2026-10-02&pagina=0',
               'de=2026-10-01&ate=2026-10-02&pagina=abc',
               'de=2026-10-01&ate=2026-10-02&pagina=1000001'): # offset absurdo vira 502 no PostgREST
        with patch('app.consultar_telemetria_periodo', return_value=[]) as consulta:
            r = gestor().get(f'/telemetria?equipamento=1&{qs}')
        assert r.status_code == 400, qs
        assert r.json['erro'] in {'periodo_invalido', 'pagina_invalido'}, qs
        consulta.assert_not_called()


def test_limite_de_um_ano_aceita_365_dias_de_diferenca(banco):
    with patch('app.consultar_telemetria_periodo', return_value=[]):
        r = gestor().get('/telemetria?equipamento=1&de=2025-10-21&ate=2026-10-21')
    assert r.status_code == 200


def test_pagina_cheia_sem_linha_extra_nao_tem_mais(banco):
    linhas = [{'criado_em': '2026-10-01T00:00:00+00:00'} for _ in range(50)]
    with patch('app.consultar_telemetria_periodo', return_value=linhas):
        r = gestor().get('/telemetria?equipamento=1&de=2026-10-01&ate=2026-10-01')
    assert (r.json['total'], r.json['tem_mais']) == (50, False)


def test_falha_do_banco_no_periodo_vira_502(banco):
    with patch('app.consultar_telemetria_periodo', side_effect=RuntimeError('banco fora')):
        r = gestor().get('/telemetria?equipamento=1&de=2026-10-01&ate=2026-10-01')
    assert r.status_code == 502


def test_gestor_nao_le_periodo_de_maquina_de_outra_fazenda(banco):
    with patch('app.consultar_telemetria_periodo', return_value=[]) as consulta:
        r = gestor(1).get('/telemetria?equipamento=3&de=2026-10-01&ate=2026-10-02')
    assert r.status_code == 403
    consulta.assert_not_called()


def test_sem_de_e_ate_o_comportamento_antigo_continua(banco):
    with patch('app.consultar_telemetria', return_value=[{'dispositivo_id': 'ESP-A'}]) as antiga, \
         patch('app.consultar_telemetria_periodo') as nova:
        r = gestor().get('/telemetria?equipamento=1&limite=30')
    assert r.status_code == 200 and 'pagina' not in r.json
    antiga.assert_called_once()
    nova.assert_not_called()


# ---------- total de leituras e de paginas (so na pagina 1) ----------

from unittest.mock import MagicMock  # noqa: E402

_REQUEST_JSON = db._request_json   # o conftest troca _request_json em todo teste; aqui queremos o original


def _resposta_contagem(status, content_range, corpo='[{"id": 1}]'):
    r = MagicMock(status_code=status, text=corpo, headers={'Content-Range': content_range})
    r.json.return_value = [{'id': 1}]
    return r


def test_contar_le_o_total_do_content_range():
    inicio, fim = datetime(2026, 9, 21, tzinfo=BRT), datetime(2026, 10, 2, tzinfo=BRT)
    with patch.object(db, 'validate_supabase_config'), patch.object(db, '_request_json', _REQUEST_JSON), \
         patch.object(db, 'get_supabase_headers', return_value={'apikey': 'k'}), \
         patch.object(db._sessao, 'request', return_value=_resposta_contagem(206, '0-0/268000')) as req:
        assert db.contar_telemetria_periodo('ESP-A', inicio, fim, equipamento=2) == 268000
    kw = req.call_args.kwargs
    assert kw['headers']['Prefer'] == 'count=exact' and kw['headers']['Range'] == '0-0'
    assert kw['timeout'] == 3
    assert kw['params']['equipamento_id'] == 'eq.2'
    assert kw['params']['criado_em'] == f'gte.{inicio.isoformat()}'
    assert kw['params']['and'] == f'(criado_em.lt.{fim.isoformat()})'


def test_contar_sem_leituras_da_zero_em_200_e_em_416():
    inicio, fim = datetime(2026, 9, 21, tzinfo=BRT), datetime(2026, 10, 2, tzinfo=BRT)
    for status in (200, 416):
        with patch.object(db, 'validate_supabase_config'), patch.object(db, '_request_json', _REQUEST_JSON), \
             patch.object(db, 'get_supabase_headers', return_value={'apikey': 'k'}), \
             patch.object(db._sessao, 'request', return_value=_resposta_contagem(status, '*/0', '[]')):
            assert db.contar_telemetria_periodo('ESP-A', inicio, fim) == 0, status


def test_pagina_1_traz_total_leituras_e_total_paginas(banco):
    with patch('app.consultar_telemetria_periodo', return_value=[]), \
         patch('app.contar_telemetria_periodo', return_value=8928) as contar:
        r = gestor().get('/telemetria?equipamento=1&de=2026-09-21&ate=2026-10-01')
    assert (r.json['total_leituras'], r.json['total_paginas']) == (8928, 179)
    janela = contar.call_args.args
    assert janela[1] == datetime(2026, 9, 21, tzinfo=BRT) and janela[2] == datetime(2026, 10, 2, tzinfo=BRT)
    assert contar.call_args.kwargs['equipamento'] == 1


def test_periodo_sem_leituras_tem_uma_pagina(banco):
    with patch('app.consultar_telemetria_periodo', return_value=[]), patch('app.contar_telemetria_periodo', return_value=0):
        r = gestor().get('/telemetria?equipamento=1&de=2026-09-21&ate=2026-10-01')
    assert (r.json['total_leituras'], r.json['total_paginas']) == (0, 1)


def test_pagina_2_nao_conta_nem_traz_totais(banco):
    with patch('app.consultar_telemetria_periodo', return_value=[]), \
         patch('app.contar_telemetria_periodo') as contar:
        r = gestor().get('/telemetria?equipamento=1&de=2026-09-21&ate=2026-10-01&pagina=2')
    assert r.status_code == 200
    assert 'total_leituras' not in r.json and 'total_paginas' not in r.json
    contar.assert_not_called()


def test_falha_da_contagem_vira_none_e_a_tabela_segue(banco):
    linhas = [{'criado_em': '2026-10-01T00:00:00+00:00'}]
    with patch('app.consultar_telemetria_periodo', return_value=linhas), \
         patch('app.contar_telemetria_periodo', side_effect=RuntimeError('contagem demorou')):
        r = gestor().get('/telemetria?equipamento=1&de=2026-09-21&ate=2026-10-01')
    assert r.status_code == 200
    assert len(r.json['dados']) == 1
    assert (r.json['total_leituras'], r.json['total_paginas']) == (None, None)
