"""Janela de periodo (?de=&ate=) nas rotas /eventos, /resumo e /operacoes, em horario de Brasilia."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

import supabase_client as db
from tests.test_frota import banco, gestor  # noqa: F401

BRT = timezone(timedelta(hours=-3))
ROTAS = ['/eventos', '/resumo', '/operacoes']


def _chamar(rota, query, **kw):
    """Chama a rota com a consulta falsa certa e devolve (resposta, mock)."""
    if rota == '/operacoes':
        alvo, nome = db, 'consultar_periodo'
    else:
        alvo, nome = 'app', 'consultar_eventos' if rota == '/eventos' else 'consultar_resumo'
    ctx = patch.object(alvo, nome, return_value=[]) if alvo is db else patch(f'{alvo}.{nome}', return_value=[])
    with ctx as consulta:
        r = gestor().get(f'{rota}?equipamento=1&{query}')
    return r, consulta


def test_eventos_com_de_ate_passa_a_janela_em_brasilia(banco):
    r, consulta = _chamar('/eventos', 'de=2026-09-21&ate=2026-10-01')
    assert r.status_code == 200
    assert consulta.call_args.kwargs['janela'] == (datetime(2026, 9, 21, tzinfo=BRT), datetime(2026, 10, 2, tzinfo=BRT))
    assert consulta.call_args.kwargs['dias'] is None


def test_resumo_com_de_ate_passa_a_janela(banco):
    r, consulta = _chamar('/resumo', 'de=2026-09-21&ate=2026-10-01')
    assert r.status_code == 200
    assert consulta.call_args.kwargs['janela'] == (datetime(2026, 9, 21, tzinfo=BRT), datetime(2026, 10, 2, tzinfo=BRT))
    assert consulta.call_args.kwargs['dias'] is None


def test_operacoes_com_de_ate_filtra_recebido_em_pela_janela(banco):
    r, consulta = _chamar('/operacoes', 'de=2026-09-21&ate=2026-10-01')
    assert r.status_code == 200
    assert consulta.call_args.kwargs['campo'] == 'recebido_em'
    assert consulta.call_args.kwargs['janela'] == (datetime(2026, 9, 21, tzinfo=BRT), datetime(2026, 10, 2, tzinfo=BRT))
    assert consulta.call_args.args[2] is None


@pytest.mark.parametrize('de,ate,fim', [
    ('2028-02-28', '2028-03-01', datetime(2028, 3, 2, tzinfo=BRT)),      # 29 de fevereiro (ano bissexto)
    ('2026-12-30', '2027-01-02', datetime(2027, 1, 3, tzinfo=BRT)),      # virada de ano
])
def test_janela_atravessa_29_de_fevereiro_e_virada_de_ano(banco, de, ate, fim):
    r, consulta = _chamar('/eventos', f'de={de}&ate={ate}')
    assert r.status_code == 200
    assert consulta.call_args.kwargs['janela'][1] == fim


@pytest.mark.parametrize('rota', ROTAS)
@pytest.mark.parametrize('qs', [
    'de=2026-10-01',                         # falta o ate
    'ate=2026-10-01',                        # falta o de
    'de=21/09/2026&ate=21/10/2026',          # formato errado
    'de=2026-02-30&ate=2026-03-01',          # dia inexistente
    'de=2026-10-21&ate=2026-09-21',          # invertido
    'de=2025-10-20&ate=2026-10-21',          # 366 dias de diferenca
    'de=9999-12-31&ate=9999-12-31',          # ate + 1 dia estoura o calendario
    'de=2026-10-01&ate=2026-10-02&dias=7',   # dias junto com de/ate
])
def test_de_ate_invalidos_dao_400(banco, rota, qs):
    r, consulta = _chamar(rota, qs)
    assert r.status_code == 400
    assert r.json['erro'] == 'periodo_invalido'
    consulta.assert_not_called()


@pytest.mark.parametrize('rota', ROTAS)
def test_sem_de_ate_o_comportamento_por_dias_continua(banco, rota):
    r, consulta = _chamar(rota, 'dias=30')
    assert r.status_code == 200
    if rota == '/operacoes':
        assert consulta.call_args.args[2] == 30
    else:
        assert consulta.call_args.kwargs['dias'] == 30
    assert consulta.call_args.kwargs.get('janela') is None


def test_limite_de_365_dias_de_diferenca_e_aceito(banco):
    r, _ = _chamar('/eventos', 'de=2025-10-21&ate=2026-10-21')
    assert r.status_code == 200


def test_consultar_periodo_com_janela_filtra_gte_e_lt():
    chamadas = []

    def query(method, table, params=None, payload=None):
        chamadas.append(dict(params))
        return []
    janela = (datetime(2026, 9, 21, tzinfo=BRT), datetime(2026, 10, 2, tzinfo=BRT))
    with patch.object(db, '_request_json', side_effect=query):
        db.consultar_periodo('sessoes_operacao', {'equipamento_id': 'eq.1'}, None, campo='recebido_em', janela=janela)
    p = chamadas[0]
    assert p['equipamento_id'] == 'eq.1'
    assert p['recebido_em'] == f'gte.{janela[0].isoformat()}'
    assert p['and'] == f'(recebido_em.lt.{janela[1].isoformat()})'


def test_consultar_resumo_com_janela_usa_dia_do_primeiro_ao_ultimo_dia():
    chamadas = []

    def query(method, table, params=None, payload=None):
        chamadas.append((table, dict(params)))
        return []
    janela = (datetime(2026, 9, 21, tzinfo=BRT), datetime(2026, 10, 2, tzinfo=BRT))   # 21/09 a 01/10 inclusivos
    with patch.object(db, '_request_json', side_effect=query):
        db.consultar_resumo('ESP-A', equipamento=3, janela=janela)
    tabela, p = chamadas[0]
    assert tabela == 'resumo_diario_maquina'
    assert p['dia'] == 'gte.2026-09-21'
    assert p['and'] == '(dia.lte.2026-10-01)'
