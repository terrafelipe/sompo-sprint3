"""Gestor responsavel na lista de fazendas: nome de quem contatar, nunca a senha."""
import json
from unittest.mock import patch

from app import app

FAZENDAS = [
    {'id_fazenda': 1, 'nome': 'Santa Rita', 'excluido_em': None, 'cliente': {'nome': 'Cliente 1'}},
    {'id_fazenda': 2, 'nome': 'Boa Vista', 'excluido_em': None, 'cliente': {'nome': 'Cliente 2'}},
]
USUARIOS = [
    {'id_usuario': 7, 'usuario': 'joao', 'senha': 'hash-joao', 'role': 'gestor_fazenda',
     'fk_fazenda_id_fazenda': 1, 'excluido_em': None},
    {'id_usuario': 8, 'usuario': 'maria', 'senha': 'hash-maria', 'role': 'gestor_fazenda',
     'fk_fazenda_id_fazenda': 1, 'excluido_em': None},
    {'id_usuario': 9, 'usuario': 'antigo', 'senha': 'hash-antigo', 'role': 'gestor_fazenda',
     'fk_fazenda_id_fazenda': 2, 'excluido_em': '2026-09-01T00:00:00Z'},
    {'id_usuario': 10, 'usuario': 'sompo', 'senha': 'hash-sompo', 'role': 'sompo',
     'fk_fazenda_id_fazenda': 2, 'excluido_em': None},
]


def _casa(valor, filtro):
    # Subconjunto dos operadores do PostgREST usados pela rota.
    if filtro == 'is.null':
        return valor is None
    if filtro.startswith('eq.'):
        return str(valor) == filtro[3:]
    if filtro.startswith('in.('):
        return str(valor) in filtro[4:-1].split(',')
    raise AssertionError(f'filtro nao simulado: {filtro}')


def _banco(pedidos):
    # PostgREST falso: aplica os filtros e devolve so as colunas do select ('*' traz a senha).
    tabelas = {'fazenda': FAZENDAS, 'usuario': USUARIOS}

    def responder(method, table, params=None, payload=None):
        pedidos.append((table, dict(params or {})))
        params = dict(params or {})
        select = params.pop('select', '*')
        for chave in ('order', 'limit', 'offset'):
            params.pop(chave, None)
        linhas = [r for r in tabelas[table] if all(_casa(r.get(k), f) for k, f in params.items())]
        if select.startswith('*'):
            return [dict(r) for r in linhas]
        colunas = select.split(',')
        return [{c: r.get(c) for c in colunas} for r in linhas]
    return responder


def _listar(pedidos):
    client = app.test_client()
    with patch('supabase_client._request_json', side_effect=_banco(pedidos)):
        response = client.get('/fazendas')
    assert response.status_code == 200
    return response


def test_fazenda_traz_os_gestores():
    pedidos = []
    dados = _listar(pedidos).get_json()['dados']
    santa_rita = next(f for f in dados if f['id_fazenda'] == 1)
    assert santa_rita['gestores'] == [{'id_usuario': 7, 'usuario': 'joao'},
                                      {'id_usuario': 8, 'usuario': 'maria'}]


def test_senha_nunca_sai_nem_e_pedida_ao_banco():
    pedidos = []
    response = _listar(pedidos)
    assert 'senha' not in response.get_data(as_text=True)
    assert 'hash-' not in json.dumps(response.get_json())
    consultas_usuario = [p for t, p in pedidos if t == 'usuario']
    assert consultas_usuario, 'os gestores vem da tabela usuario'
    for params in consultas_usuario:
        assert params['select'] == 'id_usuario,usuario,fk_fazenda_id_fazenda'


def test_uma_consulta_so_para_todas_as_fazendas():
    pedidos = []
    _listar(pedidos)
    consultas_usuario = [p for t, p in pedidos if t == 'usuario']
    assert len(consultas_usuario) == 1
    assert consultas_usuario[0]['role'] == 'eq.gestor_fazenda'
    assert consultas_usuario[0]['excluido_em'] == 'is.null'


def test_gestor_excluido_nao_aparece_e_fazenda_sem_gestor_vem_vazia():
    pedidos = []
    dados = _listar(pedidos).get_json()['dados']
    boa_vista = next(f for f in dados if f['id_fazenda'] == 2)
    # 'antigo' foi excluido e 'sompo' nao e gestor: a lista fica vazia.
    assert boa_vista['gestores'] == []
