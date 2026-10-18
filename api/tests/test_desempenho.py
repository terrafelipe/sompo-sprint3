"""Desempenho em producao: cold start menor, ping de aquecimento, revalidacao de sessao em cache
e carteira (fazendas + resumos) numa chamada so."""
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import app as app_mod
from app import app
from tests.test_frota import banco, gestor  # noqa: F401


def test_importar_o_app_nao_carrega_o_gerador_de_pdf():
    # fpdf2 (com Pillow e fontTools) custava ~1 s de import em todo cold start da Lambda.
    codigo = "import app, sys; print('fpdf' in sys.modules)"
    saida = subprocess.run([sys.executable, '-c', codigo], cwd=Path(__file__).parents[1],
                           capture_output=True, text=True, timeout=120)
    assert saida.stdout.strip() == 'False', saida.stderr[-500:]


def test_ping_de_aquecimento_responde_sem_login_e_sem_banco():
    client = app.test_client()
    with patch('app.PAINEL_SENHA', 'secret'), patch('app.SOMPO_API_KEY', 'chave'), \
         patch('app.buscar_usuario', side_effect=AssertionError('ping nao consulta o banco')):
        r = client.post('/events', json={'source': 'aws.events'})
    assert r.status_code == 204
    assert client.get('/events').status_code == 405


def test_revalidacao_da_sessao_consulta_o_banco_no_maximo_a_cada_20s():
    client = app.test_client()
    with client.session_transaction() as s:
        s.update(logado=True, usuario='ana', usuario_id=3, role='sompo', login_em=time.time())
    with patch('app.PAINEL_SENHA', 'secret'), \
         patch('app.buscar_usuario', return_value={'id_usuario': 3, 'usuario': 'ana'}) as busca:
        for _ in range(3):
            assert client.get('/me').status_code == 200
        assert busca.call_count == 1
        # Passados os 20 s, revalida de novo.
        with patch('app.time.time', return_value=time.time() + 21):
            assert client.get('/me').status_code == 200
        assert busca.call_count == 2


def test_exclusao_limpa_o_cache_de_revalidacao():
    app_mod._revalidados['ana'] = (time.time() + 60, {'id_usuario': 3})
    with patch('app.chamar_rpc', return_value={'ok': True}, create=True), \
         patch('supabase_client.chamar_rpc', return_value={'ok': True}):
        app.test_client().delete('/usuarios/3')
    assert 'ana' not in app_mod._revalidados


def test_carteira_traz_todas_as_fazendas_com_o_mesmo_resumo_da_rota_individual(banco):
    eventos = [{'id': 1, 'dispositivo_id': 'ESP-A', 'equipamento_id': 1, 'tipo': 'furto_capo', 'severidade': 2,
                'criado_em': '2026-09-20T10:00:00+00:00'}]
    with patch('supabase_client.consultar_periodo', return_value=eventos):
        carteira = app.test_client().get('/carteira?dias=7')
        individual = app.test_client().get('/fazendas/1/resumo?dias=7')
    assert carteira.status_code == 200
    dados = carteira.json['dados']
    assert [d['fazenda']['id_fazenda'] for d in dados] == [1, 2]
    santa_rita = dados[0]
    assert [m['id_equipamento'] for m in santa_rita['equipamentos']] == [1, 2]
    assert santa_rita['equipamentos'] == individual.json['equipamentos']
    assert santa_rita['alertas_recentes'] == individual.json['alertas_recentes']
    assert [al['id'] for al in santa_rita['alertas_recentes']] == [1]
    assert dados[1]['alertas_recentes'] == []          # o evento do ESP-A nao vaza para a Vale Verde


def test_carteira_e_so_da_sompo(banco):
    assert gestor().get('/carteira').status_code == 403


# ---- cache curto da maquina e da fazenda (as 2 consultas de permissao de cada endpoint) ----

def _contar_consultas():
    """Conta as chamadas de consultar_tabela por tabela, sem trocar o que ela devolve."""
    import supabase_client as db
    contagem = {}
    original = db.consultar_tabela

    def espiao(tabela, **kw):
        contagem[tabela] = contagem.get(tabela, 0) + 1
        return original(tabela, **kw)
    return contagem, patch.object(db, 'consultar_tabela', espiao)


def test_maquina_e_fazenda_nao_sao_buscadas_de_novo_em_20s(banco):
    contagem, espiao = _contar_consultas()
    with espiao:
        cliente = gestor()
        for _ in range(3):
            assert cliente.get('/telemetria?equipamento=1').status_code == 200
    # antes: 3 chamadas de cada (uma por requisicao); agora so a primeira vai ao banco
    assert contagem['equipamentos'] == 1
    assert contagem['fazenda'] == 1


def test_cache_nao_vaza_permissao_entre_fazendas(banco):
    # A Sompo le a maquina 1 (fica no cache); o gestor da fazenda 2 continua barrado.
    sompo = app.test_client()
    assert sompo.get('/telemetria?equipamento=1').status_code == 200
    assert gestor(2).get('/telemetria?equipamento=1').status_code == 403
    assert gestor(1).get('/telemetria?equipamento=1').status_code == 200


def test_cache_expira_depois_de_20s(banco):
    contagem, espiao = _contar_consultas()
    with espiao:
        cliente = gestor()
        cliente.get('/telemetria?equipamento=1')
        with patch('frota.time.time', return_value=time.time() + 21):
            cliente.get('/telemetria?equipamento=1')
    assert contagem['equipamentos'] == 2


def test_editar_a_maquina_limpa_o_cache(banco):
    contagem, espiao = _contar_consultas()
    with espiao:
        cliente = gestor()
        cliente.get('/telemetria?equipamento=1')
        assert cliente.patch('/equipamentos/1', json={'nome': 'Trator Novo'}).status_code == 200
        antes = contagem['equipamentos']
        cliente.get('/telemetria?equipamento=1')
    assert contagem['equipamentos'] > antes   # a leitura depois da edicao foi ao banco
