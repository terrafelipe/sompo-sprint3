"""API de ocorrencias com um banco em memoria (nunca toca o Supabase)."""
from copy import deepcopy

import pytest

import supabase_client as db
from app import app


@pytest.fixture
def banco(monkeypatch):
    t = {
        'fazenda': [{'id_fazenda': 1, 'nome': 'Santa Rita'}, {'id_fazenda': 2, 'nome': 'Vale Verde'}],
        'equipamentos': [
            {'id_equipamento': 1, 'nome': 'Trator A', 'fk_fazenda_id_fazenda': 1, 'dispositivo_id': 'ESP-A'},
            {'id_equipamento': 3, 'nome': 'Trator C', 'fk_fazenda_id_fazenda': 2, 'dispositivo_id': 'ESP-C'}],
        'eventos': [{'id': 10, 'dispositivo_id': 'ESP-A', 'tipo': 'furto_capo', 'severidade': 2},
                    {'id': 11, 'dispositivo_id': 'ESP-C', 'tipo': 'chama_detectada', 'severidade': 5}],
        'usuario': [
            {'id_usuario': 1, 'usuario': 'ana.sompo', 'role': 'sompo', 'fk_fazenda_id_fazenda': None},
            {'id_usuario': 2, 'usuario': 'gestor.rita', 'role': 'gestor_fazenda', 'fk_fazenda_id_fazenda': 1},
            {'id_usuario': 3, 'usuario': 'gestor.vale', 'role': 'gestor_fazenda', 'fk_fazenda_id_fazenda': 2},
            {'id_usuario': 4, 'usuario': 'antigo', 'role': 'sompo', 'fk_fazenda_id_fazenda': None,
             'excluido_em': '2026-01-01T00:00:00Z'}],
        'ocorrencias': [],
    }

    def filtrar(rows, filtros):
        for campo, expr in (filtros or {}).items():
            if expr == 'is.null':
                rows = [r for r in rows if r.get(campo) is None]
            elif expr.startswith('eq.'):
                rows = [r for r in rows if str(r.get(campo)) == expr[3:]]
            elif expr.startswith('in.('):
                valores = expr[4:-1].split(',')
                rows = [r for r in rows if str(r.get(campo)) in valores]
        return rows

    def consultar(tabela, *, filtros=None, limite=50, offset=0, **kwargs):
        return deepcopy(filtrar(t[tabela], filtros))[offset:offset + limite]

    def inserir(tabela, dados):
        row = {'id_ocorrencia': len(t[tabela]) + 1, 'status': 'aberta', 'criado_em': '2026-09-20T10:00:00Z', **dados}
        t[tabela].append(row)
        return deepcopy(row)

    def atualizar(tabela, filtros, dados):
        rows = filtrar(t[tabela], filtros)
        for r in rows:
            r.update(dados)
        return deepcopy(rows[0]) if rows else {}

    monkeypatch.setattr(db, 'consultar_tabela', consultar)
    monkeypatch.setattr(db, 'inserir_tabela', inserir)
    monkeypatch.setattr(db, 'atualizar_tabela', atualizar)
    return t


def cliente(role='sompo', fazenda=None, usuario='ana.sompo'):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logado=True, role=role, fazenda_id=fazenda, usuario=usuario)
    return c


def gestor(fazenda=1):
    return cliente('gestor_fazenda', fazenda, 'gestor.rita')


def test_sompo_abre_ocorrencia_a_partir_do_alerta(banco):
    r = cliente().post('/ocorrencias', json={'equipamento_id': 1, 'evento_id': 10, 'titulo': ' Capô aberto '})
    assert r.status_code == 201
    oc = banco['ocorrencias'][0]
    assert (oc['fazenda_id'], oc['equipamento_id'], oc['evento_id'], oc['tipo']) == (1, 1, 10, 'furto_capo')
    assert oc['titulo'] == 'Capô aberto' and oc['criado_por'] == 'ana.sompo'


def test_um_alerta_vira_uma_ocorrencia_so(banco):
    cliente().post('/ocorrencias', json={'equipamento_id': 1, 'evento_id': 10, 'titulo': 'Capô'})
    r = cliente().post('/ocorrencias', json={'equipamento_id': 1, 'evento_id': 10, 'titulo': 'Capô de novo'})
    assert r.status_code == 409
    assert r.json == {'erro': 'ocorrencia_ja_existe', 'id_ocorrencia': 1}
    assert len(banco['ocorrencias']) == 1


def test_alerta_precisa_ser_da_maquina_informada(banco):
    r = cliente().post('/ocorrencias', json={'equipamento_id': 1, 'evento_id': 11, 'titulo': 'Chama'})
    assert r.status_code == 400 and r.json['erro'] == 'evento_de_outra_maquina'
    r = cliente().post('/ocorrencias', json={'evento_id': 10, 'fazenda_id': 1, 'titulo': 'Sem maquina'})
    assert r.status_code == 400 and r.json['erro'] == 'evento_sem_maquina'


def test_relato_manual_por_fazenda_e_titulo_obrigatorio(banco):
    r = cliente().post('/ocorrencias', json={'fazenda_id': 2, 'titulo': 'Cerca quebrada', 'descricao': 'Lado norte'})
    assert r.status_code == 201
    assert banco['ocorrencias'][0]['fazenda_id'] == 2 and banco['ocorrencias'][0]['equipamento_id'] is None
    assert cliente().post('/ocorrencias', json={'fazenda_id': 2, 'titulo': '  '}).json['erro'] == 'titulo_obrigatorio'
    assert cliente().post('/ocorrencias', json={'titulo': 'x'}).json['erro'] == 'fazenda_invalido'


def test_gestor_fica_na_propria_fazenda(banco):
    assert gestor().post('/ocorrencias', json={'equipamento_id': 3, 'titulo': 'x'}).status_code == 403
    assert gestor().post('/ocorrencias', json={'fazenda_id': 2, 'titulo': 'x'}).status_code == 403
    cliente().post('/ocorrencias', json={'fazenda_id': 2, 'titulo': 'Da outra fazenda'})
    gestor().post('/ocorrencias', json={'fazenda_id': 1, 'titulo': 'Minha'})
    r = gestor().get('/ocorrencias')
    assert [o['titulo'] for o in r.json['dados']] == ['Minha']
    assert gestor().get('/ocorrencias?fazenda=2').status_code == 403
    assert gestor().patch('/ocorrencias/1', json={'status': 'resolvida'}).status_code == 403


def test_lista_traz_nomes_e_filtra_status(banco):
    cliente().post('/ocorrencias', json={'equipamento_id': 1, 'evento_id': 10, 'titulo': 'Capô'})
    cliente().post('/ocorrencias', json={'fazenda_id': 2, 'titulo': 'Cerca'})
    cliente().patch('/ocorrencias/1', json={'responsavel_id': 2, 'status': 'em_verificacao'})
    dados = cliente().get('/ocorrencias').json['dados']
    capo = next(o for o in dados if o['titulo'] == 'Capô')
    assert (capo['fazenda_nome'], capo['equipamento_nome'], capo['responsavel_nome']) == ('Santa Rita', 'Trator A', 'gestor.rita')
    so_abertas = cliente().get('/ocorrencias?status=aberta').json['dados']
    assert [o['titulo'] for o in so_abertas] == ['Cerca']
    assert cliente().get('/ocorrencias?status=fechada').status_code == 400


def test_patch_valida_status_responsavel_e_nota(banco):
    cliente().post('/ocorrencias', json={'fazenda_id': 1, 'titulo': 'Capô'})
    assert cliente().patch('/ocorrencias/1', json={'status': 'fechada'}).json['erro'] == 'status_invalido'
    # Responsavel: Sompo ou gestor DESTA fazenda, e nao excluido.
    assert cliente().patch('/ocorrencias/1', json={'responsavel_id': 3}).json['erro'] == 'responsavel_invalido'
    assert cliente().patch('/ocorrencias/1', json={'responsavel_id': 4}).json['erro'] == 'responsavel_invalido'
    assert cliente().patch('/ocorrencias/1', json={}).json['erro'] == 'nada_para_atualizar'
    r = cliente().patch('/ocorrencias/1', json={'status': 'resolvida', 'responsavel_id': 1, 'nota': ' Trava trocada '})
    assert r.status_code == 200
    assert {k: banco['ocorrencias'][0][k] for k in ('status', 'responsavel_id', 'nota')} == \
        {'status': 'resolvida', 'responsavel_id': 1, 'nota': 'Trava trocada'}
    assert cliente().patch('/ocorrencias/1', json={'responsavel_id': None}).status_code == 200
    assert cliente().patch('/ocorrencias/99', json={'status': 'aberta'}).status_code == 404


def test_responsaveis_possiveis_da_fazenda(banco):
    nomes = [u['usuario'] for u in cliente().get('/ocorrencias/responsaveis?fazenda=1').json['dados']]
    assert nomes == ['ana.sompo', 'gestor.rita']
    assert gestor().get('/ocorrencias/responsaveis?fazenda=2').status_code == 403


def test_sem_migracao_avisa(banco, monkeypatch):
    def sem_tabela(tabela, **kwargs):
        raise db.SupabaseError(404, 'PGRST205')
    monkeypatch.setattr(db, 'consultar_tabela', sem_tabela)
    r = cliente().get('/ocorrencias')
    assert r.status_code == 409 and r.json['erro'] == 'migracao_pendente'


def test_corrida_no_mesmo_alerta_vira_409(banco, monkeypatch):
    # Duas abas ao mesmo tempo: a checagem passa nas duas e o indice unico barra a segunda.
    def unico(tabela, dados):
        raise RuntimeError('Erro ao inserir no Supabase: 409 - {"code":"23505","message":"duplicate key"}')
    monkeypatch.setattr(db, 'inserir_tabela', unico)
    r = cliente().post('/ocorrencias', json={'equipamento_id': 1, 'evento_id': 10, 'titulo': 'Capô'})
    assert r.status_code == 409 and r.json['erro'] == 'ocorrencia_ja_existe'


def test_corpo_que_nao_e_objeto_e_rejeitado(banco):
    assert cliente().post('/ocorrencias', json=[1]).status_code == 400
    assert cliente().post('/ocorrencias', json={'fazenda_id': 1, 'titulo': ['x']}).json['erro'] == 'dados_invalidos'
    cliente().post('/ocorrencias', json={'fazenda_id': 1, 'titulo': 'Capô'})
    assert cliente().patch('/ocorrencias/1', json='resolvida').json['erro'] == 'nada_para_atualizar'


def test_tipo_errado_e_400_e_nao_apaga_o_dado(banco):
    cliente().post('/ocorrencias', json={'fazenda_id': 1, 'titulo': 'Capô', 'descricao': 'Original'})
    cliente().patch('/ocorrencias/1', json={'nota': 'Primeira nota'})
    r = cliente().patch('/ocorrencias/1', json={'nota': 42})
    assert r.status_code == 400 and r.json['erro'] == 'dados_invalidos'
    assert banco['ocorrencias'][0]['nota'] == 'Primeira nota'
    assert cliente().post('/ocorrencias', json={'fazenda_id': 1, 'titulo': 'x', 'descricao': {'a': 1}}).status_code == 400


def test_codigo_de_erro_so_vale_no_campo_code(banco, monkeypatch):
    # Um id de evento com "23505" na URL de um erro de rede nao pode virar "ja existe".
    def fora_do_ar(tabela, dados):
        raise RuntimeError('Max retries exceeded with url: /rest/v1/ocorrencias?evento_id=eq.123505')
    monkeypatch.setattr(db, 'inserir_tabela', fora_do_ar)
    r = cliente().post('/ocorrencias', json={'fazenda_id': 1, 'titulo': 'x'})
    assert r.status_code == 502 and r.json['erro'] == 'ocorrencias_indisponiveis'
