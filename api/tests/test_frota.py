"""Fluxos reais de Flask com a fronteira PostgREST substituída em memória."""
from copy import deepcopy
from unittest.mock import patch

import pytest
from app import app
import supabase_client as db


@pytest.fixture
def banco(monkeypatch):
    tabelas = {
        'fazenda': [
            {'id_fazenda': 1, 'nome': 'Santa Rita', 'fk_cliente_id_cliente': 10},
            {'id_fazenda': 2, 'nome': 'Vale Verde', 'fk_cliente_id_cliente': 20}],
        'equipamentos': [
            {'id_equipamento': 1, 'nome': 'Trator A', 'fk_fazenda_id_fazenda': 1,
             'fk_cliente_id_cliente': 10, 'dispositivo_id': 'ESP-A', 'ativo': True},
            {'id_equipamento': 2, 'nome': 'Trator B', 'fk_fazenda_id_fazenda': 1,
             'fk_cliente_id_cliente': 10, 'dispositivo_id': 'ESP-B', 'ativo': True},
            {'id_equipamento': 3, 'nome': 'Trator C', 'fk_fazenda_id_fazenda': 2,
             'fk_cliente_id_cliente': 20, 'dispositivo_id': 'ESP-C', 'ativo': True}],
        'operadores': [
            {'id_operador': 1, 'nome': 'Ana', 'uid': '01020304',
             'fk_fazenda_id_fazenda': 1, 'ativo': True},
            {'id_operador': 2, 'nome': 'Bia', 'uid': '05060708',
             'fk_fazenda_id_fazenda': 2, 'ativo': True}],
        'operador_equipamento': [], 'sessoes_operacao': [],
    }
    def consultar(tabela, *, filtros=None, limite=50, offset=0, **kwargs):
        rows = deepcopy(tabelas.get(tabela, []))
        for campo, expr in (filtros or {}).items():
            if expr.startswith('eq.'):
                value = expr[3:]
                rows = [r for r in rows if str(r.get(campo)).lower() == value.lower()]
            elif expr.startswith('in.('):
                values = expr[4:-1].split(',')
                rows = [r for r in rows if str(r.get(campo)) in values]
            elif expr == 'is.null':
                rows = [r for r in rows if r.get(campo) is None]
        return rows[offset:offset+limite]
    def inserir(tabela, dados):
        pk = {'equipamentos': 'id_equipamento', 'operadores': 'id_operador'}[tabela]
        row = {**dados, pk: len(tabelas[tabela])+1}
        tabelas[tabela].append(row)
        return deepcopy(row)
    def atualizar(tabela, filtros, dados):
        rows = consultar(tabela, filtros=filtros)
        pk = {'equipamentos': 'id_equipamento', 'operadores': 'id_operador'}[tabela]
        for row in tabelas[tabela]:
            if rows and row[pk] == rows[0][pk]:
                row.update(dados)
                return deepcopy(row)
        return {}
    monkeypatch.setattr(db, 'consultar_tabela', consultar)
    monkeypatch.setattr(db, 'inserir_tabela', inserir)
    monkeypatch.setattr(db, 'atualizar_tabela', atualizar, raising=False)
    return tabelas


def gestor(fazenda=1):
    client = app.test_client()
    with client.session_transaction() as s:
        s.update(logado=True, role='gestor_fazenda', fazenda_id=fazenda)
    return client


def test_gestor_lista_apenas_maquinas_da_fazenda(banco):
    r = gestor().get('/equipamentos?fazenda=2')
    assert r.status_code == 200
    assert [m['id_equipamento'] for m in r.json['dados']] == [1, 2]


@pytest.mark.parametrize('path', ['/equipamentos/3', '/fazendas/2/resumo',
                                 '/operadores/2', '/telemetria?equipamento=3',
                                 '/eventos?dispositivo=ESP-C', '/relatorio/risco.pdf?equipamento=3'])
def test_ids_de_outra_fazenda_sao_negados(banco, path):
    assert gestor().get(path).status_code == 403


def test_gestor_sem_fazenda_nao_tem_fallback_aberto(banco):
    assert gestor(None).get('/equipamentos').status_code == 403
    assert gestor(None).get('/telemetria?dispositivo=ESP-C').status_code == 403


def test_cadastro_equipamento_deriva_cliente_da_fazenda(banco):
    r = gestor().post('/equipamentos', json={'nome': 'Colheitadeira', 'fk_cliente_id_cliente': 999})
    assert r.status_code == 201
    assert r.json['equipamento']['fk_cliente_id_cliente'] == 10
    assert r.json['equipamento']['fk_fazenda_id_fazenda'] == 1
    assert r.json['equipamento']['dispositivo_id'] is None


def test_cadastro_nao_aceita_fazenda_alheia(banco):
    assert gestor().post('/equipamentos', json={
        'nome': 'Outra', 'fk_fazenda_id_fazenda': 2}).status_code == 403


def test_cadastro_operador_normaliza_uid_sem_criar_login(banco):
    r = gestor().post('/operadores', json={'nome': 'Carlos', 'uid': 'ab:cd:ef:12'})
    assert r.status_code == 201
    assert r.json['operador']['uid'] == 'ABCDEF12'
    assert 'senha' not in r.json['operador']
    assert r.json['operador']['matricula'] is None


def test_cadastro_maquina_completo(banco):
    r = gestor().post('/equipamentos', json={
        'nome': 'Colheitadeira', 'fabricacao': '2020-01-02',
        'ultima_manutencao': '2026-09-01', 'valor_segurado': '150000.50',
        'tipo': 'Colheitadeira', 'modelo': 'M1', 'dispositivo_id': 'ESP-TESTE'})
    assert r.status_code == 201
    eq = r.json['equipamento']
    assert eq['fabricacao'] == '2020-01-02'
    assert eq['ultima_manutencao'] == '2026-09-01'
    assert eq['valor_segurado'] == '150000.50'
    assert eq['fk_cliente_id_cliente'] == 10


def test_pdf_contem_apenas_maquina_selecionada(banco, pdf_aberto):
    with patch('app.consultar_resumo', return_value=[]) as resumo,          patch('app.consultar_eventos', return_value=[]) as eventos,          patch('llm.LLM_API_KEY', ''):
        r = gestor().get('/relatorio/risco.pdf?equipamento=2&dias=7')
    assert r.status_code == 200
    assert r.content_type == 'application/pdf'
    assert 'ESP-B' in r.headers['Content-Disposition']
    resumo.assert_called_once_with('ESP-B', dias=7)
    eventos.assert_called_once_with('ESP-B', dias=7)
    text = r.data.decode('latin-1')
    assert 'Trator B' in text and 'Santa Rita' in text and 'ESP-B' in text
    assert 'Trator A' not in text and 'ESP-A' not in text


def test_historico_vazio_diferente_de_falha(banco):
    with patch('supabase_client.consultar_periodo', return_value=[]):
        r = gestor().get('/operacoes')
        assert r.status_code == 200 and r.json['dados'] == []
    with patch('supabase_client.consultar_periodo', side_effect=RuntimeError('offline')):
        r = gestor().get('/operacoes')
        assert r.status_code == 502 and r.json['erro'] == 'frota_indisponivel'


@pytest.mark.parametrize('uid', ['', '123', 'GGGGGGGG', '01020304'])
def test_uid_invalido_ou_duplicado_nao_cria_operador(banco, uid):
    assert gestor().post('/operadores', json={'nome': 'Carlos', 'uid': uid}).status_code in (400, 409)
    assert len(banco['operadores']) == 2


def test_uid_de_operador_excluido_pode_ser_reaproveitado(banco):
    banco['operadores'][0]['excluido_em'] = '2026-09-24T12:00:00+00:00'
    r = gestor().post('/operadores', json={'nome': 'Felipe', 'uid': '01020304'})
    assert r.status_code == 201
    assert r.json['operador']['uid'] == '01020304'


def test_transferencia_e_remanejamento_nao_permitidos(banco):
    assert gestor().patch('/equipamentos/1', json={'dispositivo_id': 'OUTRO'}).status_code == 409
    assert gestor().patch('/equipamentos/1', json={'fk_fazenda_id_fazenda': 2}).status_code == 409


def test_desativacao_preserva_registro(banco):
    r = gestor().patch('/operadores/1', json={'ativo': False})
    assert r.status_code == 200
    assert banco['operadores'][0]['ativo'] is False
    assert len(banco['operadores']) == 2


def test_ativo_exige_booleano_json(banco):
    assert gestor().patch('/operadores/1', json={'ativo': 'false'}).status_code == 400


def test_autorizacao_de_operador_alheio_negada(banco):
    r = gestor().put('/equipamentos/1/operadores', json={'operador_ids': [2]})
    assert r.status_code == 403


def test_maquina_selecionada_e_usada_na_consulta(banco):
    with patch('app.consultar_telemetria', return_value=[{'dispositivo_id': 'ESP-B'}]):
        r = gestor().get('/telemetria?equipamento=2')
    assert r.status_code == 200
    assert r.json['equipamento']['id_equipamento'] == 2
    assert r.json['dados'][0]['dispositivo_id'] == 'ESP-B'


def test_sem_selecao_nao_consulta_dispositivo_padrao(banco):
    assert gestor().get('/telemetria').status_code == 400


def test_seletores_contraditorios_sao_rejeitados(banco):
    assert gestor().get('/telemetria?equipamento=1&dispositivo=ESP-C').status_code == 400


def test_registro_legado_nao_ganha_operador_atual(banco):
    with patch('app.consultar_eventos', return_value=[{'id': 9, 'tipo': 'furto_capo'}]):
        r = gestor().get('/eventos?equipamento=1')
    assert r.status_code == 200
    assert r.json['dados'][0]['operador_nome'] == 'Operador não identificado'


def test_ocorrencia_sem_relogio_nao_usa_hora_de_recebimento(banco):
    with patch('app.consultar_eventos', return_value=[{
        'registro_id': 'r1', 'criado_em': '2026-09-16T12:00:00Z', 'ocorrido_em': None,
        'tipo': 'furto_capo', 'operador_id': 1, 'sessao_id': 's1'}]):
        r = gestor().get('/eventos?equipamento=1')
    assert r.json['dados'][0]['horario_ocorrencia'] is None
    assert r.json['dados'][0]['operador_nome'] == 'Ana'


def test_credencial_nao_e_armazenada_em_texto_claro(banco, monkeypatch):
    calls = []
    monkeypatch.setattr(db, 'chamar_rpc', lambda name, payload: calls.append((name, payload)) or {}, raising=False)
    r = gestor().post('/equipamentos/1/credencial')
    assert r.status_code == 201
    token = r.json['token']
    assert len(token) >= 32
    assert token not in str(calls)
    assert len(calls[0][1]['p_token_hash']) == 64


def test_resumo_traz_os_10_alertas_mais_recentes_da_fazenda(banco):
    # 12 eventos alternando as duas máquinas; um veio de backlog (registro_id) e vale o ocorrido_em.
    eventos = [{'id': i, 'dispositivo_id': 'ESP-A' if i % 2 else 'ESP-B', 'tipo': 'furto_capo', 'severidade': 2,
                'criado_em': f'2026-09-20T10:{i:02d}:00+00:00'} for i in range(12)]
    eventos[0].update(registro_id=5, ocorrido_em='2026-09-20T11:00:00+00:00')
    with patch('supabase_client.consultar_periodo', return_value=eventos):
        r = gestor().get('/fazendas/1/resumo?dias=7')
    assert r.status_code == 200
    alertas = r.json['alertas_recentes']
    assert len(alertas) == 10
    assert alertas[0]['id'] == 0 and alertas[0]['horario_ocorrencia'] == '2026-09-20T11:00:00+00:00'
    assert [a['id'] for a in alertas[1:]] == list(range(11, 2, -1))
    assert alertas[1]['equipamento_id'] == 1 and alertas[1]['equipamento_nome'] == 'Trator A'
    assert alertas[2]['equipamento_id'] == 2 and alertas[2]['equipamento_nome'] == 'Trator B'


def test_alertas_recentes_seguem_a_maquina_gravada_no_evento(banco):
    # ESP-A mudou de fazenda: o evento antigo, gravado com a maquina 3 (Vale Verde), nao aparece
    # em Santa Rita; o evento gravado com a maquina 2 vale mesmo vindo de outro dispositivo.
    eventos = [{'id': 1, 'dispositivo_id': 'ESP-A', 'equipamento_id': 3, 'tipo': 'furto_capo', 'criado_em': '2026-09-20T10:00:00+00:00'},
               {'id': 2, 'dispositivo_id': 'ESP-A', 'equipamento_id': 2, 'tipo': 'furto_capo', 'criado_em': '2026-09-20T11:00:00+00:00'},
               {'id': 3, 'dispositivo_id': 'ESP-A', 'tipo': 'furto_capo', 'criado_em': '2026-09-20T12:00:00+00:00'}]
    with patch('supabase_client.consultar_periodo', return_value=eventos):
        alertas = gestor().get('/fazendas/1/resumo?dias=7').json['alertas_recentes']
    assert [(a['id'], a['equipamento_id']) for a in alertas] == [(3, 1), (2, 2)]
