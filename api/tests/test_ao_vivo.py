"""Modo ao vivo: liga/desliga por maquina e entrega o que chegou desde um instante."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from app import app
import supabase_client as db

AGORA = datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat()


@pytest.fixture
def banco(monkeypatch):
    tabelas = {
        'fazenda': [{'id_fazenda': 1, 'nome': 'Santa Rita'}, {'id_fazenda': 2, 'nome': 'Vale Verde'}],
        'equipamentos': [
            {'id_equipamento': 1, 'nome': 'Trator A', 'fk_fazenda_id_fazenda': 1, 'dispositivo_id': 'ESP-A', 'ativo': True, 'ao_vivo_ate': None},
            {'id_equipamento': 2, 'nome': 'Trator B', 'fk_fazenda_id_fazenda': 1, 'dispositivo_id': None, 'ativo': True, 'ao_vivo_ate': None},
            {'id_equipamento': 3, 'nome': 'Trator C', 'fk_fazenda_id_fazenda': 2, 'dispositivo_id': 'ESP-C', 'ativo': True, 'ao_vivo_ate': None},
            {'id_equipamento': 4, 'nome': 'Trator D', 'fk_fazenda_id_fazenda': 1, 'dispositivo_id': 'ESP-D', 'ativo': True,
             'ao_vivo_ate': None, 'excluido_em': '2026-09-01T00:00:00+00:00'}],
        'operadores': [{'id_operador': 7, 'nome': 'Ana Souza', 'fk_fazenda_id_fazenda': 1}],
        'telemetria': [], 'eventos': [], 'registros_operacao': [],
    }
    chamadas = []

    def consultar(tabela, *, filtros=None, limite=50, offset=0, select='*', order=None):
        chamadas.append(dict(tabela=tabela, filtros=dict(filtros or {}), limite=limite, select=select, order=order))
        rows = deepcopy(tabelas.get(tabela, []))
        for campo, expr in (filtros or {}).items():
            if expr.startswith('eq.'):
                rows = [r for r in rows if str(r.get(campo)).lower() == expr[3:].lower()]
            elif expr.startswith('in.('):
                rows = [r for r in rows if str(r.get(campo)) in expr[4:-1].split(',')]
            elif expr == 'is.null':
                rows = [r for r in rows if r.get(campo) is None]
            elif expr.startswith('gt.'):
                corte = datetime.fromisoformat(expr[3:])
                rows = [r for r in rows if r.get(campo) and datetime.fromisoformat(r[campo]) > corte]
        if order and order.startswith('recebido_em.'):
            rows.sort(key=lambda r: r['recebido_em'], reverse=order.startswith('recebido_em.desc'))
        return rows[offset:offset + limite]

    def atualizar(tabela, filtros, dados):
        chamadas.append(dict(tabela=tabela, filtros=dict(filtros), dados=dict(dados), metodo='PATCH'))
        alvo = int(filtros['id_equipamento'][3:])
        for row in tabelas[tabela]:
            if row['id_equipamento'] == alvo:
                row.update(dados)
                return deepcopy(row)
        return {}

    monkeypatch.setattr(db, 'consultar_tabela', consultar)
    monkeypatch.setattr(db, 'atualizar_tabela', atualizar)
    tabelas['_chamadas'] = chamadas
    return tabelas


def cliente(role='sompo', fazenda=None):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logado=True, role=role, fazenda_id=fazenda)
    return c


def gestor(fazenda=1):
    return cliente('gestor_fazenda', fazenda)


# ---------- POST /equipamentos/<id>/ao-vivo ----------

def test_ligar_grava_ate_daqui_a_duas_horas(banco):
    r = cliente().post('/equipamentos/1/ao-vivo', json={'ligar': True})
    assert r.status_code == 200 and r.json['ok'] is True
    ate = datetime.fromisoformat(r.json['ao_vivo_ate'])
    assert timedelta(hours=1, minutes=59) < ate - datetime.now(timezone.utc) <= timedelta(hours=2)
    assert banco['equipamentos'][0]['ao_vivo_ate'] == r.json['ao_vivo_ate']


def test_desligar_limpa(banco):
    banco['equipamentos'][0]['ao_vivo_ate'] = iso(AGORA + timedelta(hours=1))
    r = gestor().post('/equipamentos/1/ao-vivo', json={'ligar': False})
    assert r.status_code == 200 and r.json['ao_vivo_ate'] is None
    assert banco['equipamentos'][0]['ao_vivo_ate'] is None


@pytest.mark.parametrize('corpo', [{'ligar': 'sim'}, {'ligar': 1}, {}, {'ligar': None}])
def test_ligar_precisa_ser_booleano(banco, corpo):
    r = cliente().post('/equipamentos/1/ao-vivo', json=corpo)
    assert r.status_code == 400 and r.json['erro'] == 'ligar_invalido'


def test_corpo_que_nao_e_json(banco):
    r = cliente().post('/equipamentos/1/ao-vivo', data='ligar=true')
    assert r.status_code == 400 and r.json['erro'] == 'json_invalido'


def test_maquina_sem_esp32(banco):
    r = cliente().post('/equipamentos/2/ao-vivo', json={'ligar': True})
    assert r.status_code == 409 and r.json['erro'] == 'equipamento_sem_dispositivo'


def test_gestor_nao_liga_maquina_de_outra_fazenda(banco):
    assert gestor(1).post('/equipamentos/3/ao-vivo', json={'ligar': True}).status_code == 403
    assert banco['equipamentos'][2]['ao_vivo_ate'] is None


def test_maquina_excluida_404(banco):
    assert cliente().post('/equipamentos/4/ao-vivo', json={'ligar': True}).status_code == 404


def test_falha_no_banco_vira_502_sem_detalhe(banco, monkeypatch):
    def quebra(*a, **k):
        raise db.SupabaseError(500, 'XX000')
    monkeypatch.setattr(db, 'atualizar_tabela', quebra)
    r = cliente().post('/equipamentos/1/ao-vivo', json={'ligar': True})
    assert r.status_code == 502 and r.json == {'erro': 'falha_na_consulta'}
