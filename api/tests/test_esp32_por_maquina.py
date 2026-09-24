"""ID do ESP32 editável e reaproveitável; o histórico de leituras acompanha a máquina."""
from unittest.mock import patch

from tests.test_frota import banco, gestor  # noqa: F401


def test_editar_o_esp32_da_maquina(banco):
    r = gestor().patch('/equipamentos/1', json={'dispositivo_id': 'ESP-NOVO'})
    assert r.status_code == 200
    assert banco['equipamentos'][0]['dispositivo_id'] == 'ESP-NOVO'


def test_tirar_o_esp32_da_maquina(banco):
    r = gestor().patch('/equipamentos/1', json={'dispositivo_id': ''})
    assert r.status_code == 200
    assert banco['equipamentos'][0]['dispositivo_id'] is None


def test_esp32_de_maquina_excluida_pode_ser_reaproveitado(banco):
    banco['equipamentos'][1]['excluido_em'] = '2026-09-24T12:00:00+00:00'
    r = gestor().post('/equipamentos', json={'nome': 'Trator novo', 'dispositivo_id': 'ESP-B'})
    assert r.status_code == 201
    assert r.json['equipamento']['dispositivo_id'] == 'ESP-B'


def test_esp32_de_maquina_ativa_continua_bloqueado(banco):
    r = gestor().patch('/equipamentos/1', json={'dispositivo_id': 'ESP-B'})
    assert r.status_code == 409 and r.json['erro'] == 'dispositivo_ja_vinculado'


def test_leituras_sao_filtradas_pela_maquina(banco):
    with patch('app.consultar_eventos', return_value=[]) as eventos, \
         patch('app.consultar_telemetria', return_value=[]) as tele, \
         patch('app.consultar_resumo', return_value=[]) as resumo:
        assert gestor().get('/eventos?equipamento=2&dias=7').status_code == 200
        assert gestor().get('/telemetria?equipamento=2').status_code == 200
        assert gestor().get('/resumo?equipamento=2&dias=7').status_code == 200
    assert eventos.call_args.kwargs['equipamento'] == 2
    assert tele.call_args.kwargs['equipamento'] == 2
    assert resumo.call_args.kwargs['equipamento'] == 2


def test_maquina_sem_esp32_ainda_mostra_o_historico_dela(banco):
    banco['equipamentos'][0]['dispositivo_id'] = None
    with patch('app.consultar_eventos', return_value=[{'id': 5, 'tipo': 'furto_capo'}]) as eventos:
        r = gestor().get('/eventos?equipamento=1&dias=7')
    assert r.status_code == 200 and len(r.json['dados']) == 1
    assert eventos.call_args.kwargs['equipamento'] == 1


def test_consulta_por_maquina_usa_equipamento_id_e_view_por_maquina():
    import supabase_client as db
    chamadas = []
    def query(method, tabela, params=None, payload=None):
        chamadas.append((tabela, dict(params)))
        return []
    with patch.object(db, '_request_json', side_effect=query):
        db.consultar_eventos(None, 7, equipamento=3)
        db.consultar_resumo('ESP-X', 7, equipamento=3)
        db.consultar_telemetria('ESP-X', 5, equipamento=3)
    assert all(p.get('equipamento_id') == 'eq.3' and 'dispositivo_id' not in p for _, p in chamadas)
    assert [t for t, _ in chamadas] == ['eventos', 'resumo_diario_maquina', 'telemetria']


def test_resumo_da_fazenda_liga_leituras_e_alertas_pela_maquina(banco):
    # O ESP-A saiu do Trator A e foi para o Trator B: os eventos gravados com equipamento_id 1
    # continuam no Trator A, mesmo com o ID do ESP32 agora apontando para o B.
    banco['equipamentos'][0]['dispositivo_id'] = None
    banco['equipamentos'][1]['dispositivo_id'] = 'ESP-A'
    eventos = [{'id': 1, 'dispositivo_id': 'ESP-A', 'equipamento_id': 1, 'tipo': 'furto_capo',
                'severidade': 2, 'criado_em': '2026-09-20T10:00:00+00:00'}]
    with patch('supabase_client.consultar_periodo', return_value=eventos) as periodo:
        r = gestor().get('/fazendas/1/resumo?dias=7')
    assert r.status_code == 200
    assert periodo.call_args.args[1] == {'equipamento_id': 'in.(1,2)'}
    alertas = r.json['alertas_recentes']
    assert [(a['id'], a['equipamento_nome']) for a in alertas] == [(1, 'Trator A')]
    maquinas = {m['id_equipamento']: m for m in r.json['equipamentos']}
    assert maquinas[1]['scores']['eventos_considerados']['total'] == 1
    assert maquinas[2]['scores']['eventos_considerados']['total'] == 0
    assert maquinas[1]['comunicacao'] == 'sem_dispositivo'
