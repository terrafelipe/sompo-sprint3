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


# ---------- GET /ao-vivo ----------

def leitura(seg, **extra):
    return _linha(AGORA, seg, **extra)


def fresca(seg, **extra):
    """Como `leitura`, mas com o relogio de agora: AGORA e fixado na importacao e envelhece numa suite longa."""
    return _linha(datetime.now(timezone.utc), seg, **extra)


def _linha(base, seg, **extra):
    t = base - timedelta(seconds=seg)
    return {'registro_id': f'r-{seg}', 'equipamento_id': 1, 'ocorrido_em': iso(t - timedelta(seconds=0.8)),
            'recebido_em': iso(t), 'criado_em': iso(t), 'temp_escape': 31, 'operador_id': None, **extra}


def test_exige_maquina(banco):
    r = cliente().get('/ao-vivo')
    assert r.status_code == 400 and r.json['erro'] == 'equipamento_obrigatorio'


def test_gestor_de_outra_fazenda_403(banco):
    assert gestor(1).get('/ao-vivo?equipamento=3').status_code == 403


@pytest.mark.parametrize('desde', ['ontem', '2026-10-06T12:00:00',              # sem fuso
                                   iso(AGORA + timedelta(minutes=1)),          # futuro
                                   iso(AGORA - timedelta(minutes=11))])        # antigo demais
def test_desde_invalido(banco, desde):
    r = cliente().get('/ao-vivo', query_string={'equipamento': 1, 'desde': desde})
    assert r.status_code == 400 and r.json['erro'] == 'desde_invalido'


def test_desde_com_mais_virado_espaco_e_aceito(banco):
    cru = iso(AGORA - timedelta(seconds=20)).replace('+00:00', ' 00:00')   # '+' sem encode vira espaco
    assert cliente().get(f'/ao-vivo?equipamento=1&desde={cru}').status_code == 200


def test_filtra_pela_maquina_e_pelo_recebido_em(banco):
    banco['telemetria'] += [leitura(40), leitura(10), {**leitura(5), 'registro_id': 'outra', 'equipamento_id': 3}]
    r = cliente().get('/ao-vivo', query_string={'equipamento': 1, 'desde': iso(AGORA - timedelta(seconds=30))})
    assert r.status_code == 200
    assert [x['registro_id'] for x in r.json['telemetria']] == ['r-10']
    consulta = next(c for c in banco['_chamadas'] if c['tabela'] == 'telemetria')
    assert consulta['filtros']['equipamento_id'] == 'eq.1'
    assert consulta['filtros']['recebido_em'].startswith('gt.')


def test_mais_novas_no_banco_e_crescente_na_resposta(banco):
    banco['telemetria'] += [leitura(s) for s in range(1, 60)]   # 59 leituras no ultimo minuto
    r = cliente().get('/ao-vivo', query_string={'equipamento': 1, 'desde': iso(AGORA - timedelta(minutes=2))})
    ids = [x['registro_id'] for x in r.json['telemetria']]
    assert len(ids) == 30 and ids[0] == 'r-30' and ids[-1] == 'r-1'


def test_sem_desde_olha_os_ultimos_30_segundos(banco):
    banco['telemetria'] += [leitura(45), leitura(20)]
    r = cliente().get('/ao-vivo?equipamento=1')
    assert [x['registro_id'] for x in r.json['telemetria']] == ['r-20']


def test_cursor_nunca_envelhece_e_recua_5s_mesmo_com_linha_nova(banco):
    desde = iso(datetime.now(timezone.utc) - timedelta(minutes=9))
    r = cliente().get('/ao-vivo', query_string={'equipamento': 1, 'desde': desde})
    cursor = datetime.fromisoformat(r.json['cursor'])
    assert datetime.now(timezone.utc) - cursor <= timedelta(seconds=6)    # placa parada: cursor nao envelhece
    banco['telemetria'].append(fresca(1))   # recebida ha 1 s
    r = cliente().get('/ao-vivo', query_string={'equipamento': 1, 'desde': r.json['cursor']})
    # O cursor nao salta ate a linha mais nova: uma linha confirmada (commit) depois dela, mas com
    # recebido_em anterior, ficaria para tras. O cliente deduplica pelo registro_id.
    folga = datetime.now(timezone.utc) - datetime.fromisoformat(r.json['cursor'])
    assert timedelta(seconds=4) <= folga <= timedelta(seconds=6)
    r = cliente().get('/ao-vivo', query_string={'equipamento': 1, 'desde': r.json['cursor']})
    assert [x['registro_id'] for x in r.json['telemetria']] == ['r-1']   # ainda dentro da janela do proximo pedido


def test_linha_confirmada_depois_de_outra_mais_nova_nao_se_perde(banco):
    banco['eventos'].append({**fresca(1), 'registro_id': 'e-1', 'tipo': 'chama_detectada', 'severidade': 4})   # o mais novo, ja visto
    r = cliente().get('/ao-vivo', query_string={'equipamento': 1, 'desde': iso(datetime.now(timezone.utc) - timedelta(seconds=30))})
    banco['telemetria'].append(fresca(2))   # recebida antes do evento, confirmada so agora
    r = cliente().get('/ao-vivo', query_string={'equipamento': 1, 'desde': r.json['cursor']})
    assert [x['registro_id'] for x in r.json['telemetria']] == ['r-2']


def test_eventos_e_operacoes_com_nome(banco):
    banco['eventos'].append({**leitura(3), 'registro_id': 'e-1', 'tipo': 'chama_detectada', 'severidade': 4})
    banco['registros_operacao'].append({**leitura(2), 'registro_id': 'o-1', 'tipo': 'inicio', 'uid': '04A1B2C3', 'operador_id': 7})
    r = cliente().get('/ao-vivo?equipamento=1')
    assert r.json['eventos'][0]['tipo'] == 'chama_detectada'
    assert r.json['operacoes'][0]['operador_nome'] == 'Ana Souza'


def test_devolve_estado_da_maquina_e_nao_cacheia(banco):
    banco['equipamentos'][0]['ao_vivo_ate'] = iso(AGORA + timedelta(hours=1))
    r = cliente().get('/ao-vivo?equipamento=1')
    assert r.json['ao_vivo_ate'] == banco['equipamentos'][0]['ao_vivo_ate']
    assert 'no-store' in r.headers['Cache-Control']


def test_falha_na_consulta_502_sem_detalhe(banco, monkeypatch):
    original = db.consultar_tabela
    def quebra(tabela, **k):
        if tabela == 'telemetria':
            raise db.SupabaseError(500, 'XX000')
        return original(tabela, **k)
    monkeypatch.setattr(db, 'consultar_tabela', quebra)
    r = cliente().get('/ao-vivo?equipamento=1')
    assert r.status_code == 502 and r.json == {'erro': 'falha_na_consulta'}
