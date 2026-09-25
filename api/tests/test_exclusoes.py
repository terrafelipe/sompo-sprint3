"""Authorization, session revocation and public deletion/detail contracts."""
import time
from unittest.mock import patch

import pytest

from app import app, _autenticar
import supabase_client as db


@pytest.mark.parametrize('tipo', ['clientes', 'fazendas', 'usuarios', 'operadores', 'equipamentos'])
def test_exclusao_envia_identidade_da_sessao(tipo):
    client = app.test_client()
    with client.session_transaction() as s:
        s.update(usuario='admin', role='sompo')
    with patch.object(db, 'consultar_tabela', return_value=[{'fk_fazenda_id_fazenda': 1}]), \
         patch.object(db, 'chamar_rpc', return_value={'ok': True}) as rpc:
        response = client.delete(f'/{tipo}/7', json={'p_usuario': 'outro'})
    assert response.status_code == 200
    rpc.assert_called_once_with('excluir_cadastro', {'p_tipo': tipo, 'p_id': 7, 'p_usuario': 'admin'})


@pytest.mark.parametrize('tipo', ['clientes', 'fazendas', 'usuarios'])
def test_gestor_nao_exclui_portfolio(tipo):
    client = app.test_client()
    with client.session_transaction() as s:
        s.update(role='gestor_fazenda', fazenda_id=1)
    with patch.object(db, 'chamar_rpc') as rpc:
        assert client.delete(f'/{tipo}/1').status_code == 403
        rpc.assert_not_called()


@pytest.mark.parametrize('tipo', ['operadores', 'equipamentos'])
@pytest.mark.parametrize('fazenda,status', [(1, 200), (2, 403)])
def test_gestor_exclusao_escopo_inclusive_repeticao(tipo, fazenda, status):
    client = app.test_client()
    with client.session_transaction() as s:
        s.update(role='gestor_fazenda', fazenda_id=1)
    with patch.object(db, 'consultar_tabela', return_value=[{
        'fk_fazenda_id_fazenda': fazenda, 'excluido_em': '2026-01-01'}]), \
         patch.object(db, 'chamar_rpc', return_value={'ok': True}) as rpc:
        assert client.delete(f'/{tipo}/1').status_code == status
        assert rpc.called == (status == 200)


@pytest.mark.parametrize('resultado,status', [
    ({'erro': 'cadastro_com_vinculos', 'dependencias': {'maquinas': 2}}, 409),
    ({'erro': 'propria_conta'}, 409), ({'erro': 'ultimo_sompo'}, 409),
    ({'erro': 'nao_encontrado'}, 404)])
def test_exclusao_respostas(resultado, status):
    with patch.object(db, 'chamar_rpc', return_value=resultado):
        response = app.test_client().delete('/usuarios/1')
    assert response.status_code == status
    assert response.json == resultado


def test_falha_banco_nao_vaza_detalhes():
    with patch.object(db, 'chamar_rpc', side_effect=RuntimeError('secret internal schema')):
        response = app.test_client().delete('/clientes/1')
    assert response.status_code == 502
    assert response.json == {'erro': 'falha_ao_excluir'}


def test_usuario_excluido_nao_usa_fallback():
    with patch('app.buscar_usuario', return_value={'excluido_em': '2026-01-01'}), \
         patch('app.PAINEL_SENHA', 'secret'):
        assert _autenticar('admin', 'secret') is None


def test_fallback_falha_fechado_sem_banco():
    with patch('app.buscar_usuario', side_effect=RuntimeError('offline')), \
         patch('app.PAINEL_SENHA', 'secret'):
        assert _autenticar('admin', 'secret') is None


def test_login_reserva_do_env_nao_entra_sem_usuario_cadastrado():
    # PAINEL_SENHA so liga o login; nao e senha de ninguem (era uma 2a senha de admin).
    with patch('app.buscar_usuario', return_value=None), \
         patch('app.PAINEL_SENHA', 'secret'):
        assert _autenticar('admin', 'secret') is None


def test_login_reserva_do_env_nao_entra_com_usuario_de_outra_senha():
    # Cenario de producao: 'sompo' no banco com senha nova e PAINEL_SENHA = senha antiga.
    from werkzeug.security import generate_password_hash
    usuario = {'id_usuario': 1, 'senha': generate_password_hash('nova-senha-1')}
    with patch('app.buscar_usuario', return_value=usuario), \
         patch('app.PAINEL_SENHA', 'antiga'):
        assert _autenticar('sompo', 'antiga') is None


@pytest.mark.parametrize('usuario_id', [None, 1])
def test_sessao_excluida_revogada_inclusive_cookie_legado(usuario_id):
    client = app.test_client()
    with client.session_transaction() as s:
        s.update(logado=True, usuario='admin', usuario_id=usuario_id, role='sompo', login_em=time.time())
    with patch('app.PAINEL_SENHA', 'secret'), \
         patch('app.buscar_usuario', return_value={'excluido_em': '2026-01-01'}):
        assert client.get('/me').status_code == 401
    with client.session_transaction() as s:
        assert not s.get('logado')


def test_detalhe_usuario_sem_segredos_e_restrito():
    def responder(method, table, params=None, payload=None):
        assert method == 'GET' and table == 'usuario'
        assert 'senha' not in params['select'] and '*' not in params['select']
        assert 'criado_em' in params['select'] and 'cliente(' in params['select']
        assert params['excluido_em'] == 'is.null'
        return [{'id_usuario': 1, 'usuario': 'admin', 'role': 'sompo'}]
    with patch.object(db, '_request_json', side_effect=responder):
        response = app.test_client().get('/usuarios/1')
    assert response.status_code == 200 and 'senha' not in response.json['usuario']
    client = app.test_client()
    with client.session_transaction() as s:
        s.update(role='gestor_fazenda', fazenda_id=1)
    assert client.get('/usuarios/1').status_code == 403
    with patch.object(db, 'consultar_usuario', return_value=None):
        assert app.test_client().get('/usuarios/99').status_code == 404


@pytest.mark.parametrize('path', ['/equipamentos/1', '/operadores/1'])
def test_cadastro_excluido_nao_pode_ser_editado(path):
    with patch.object(db, 'consultar_tabela', return_value=[{
        'fk_fazenda_id_fazenda': 1, 'excluido_em': '2026-01-01'}]), \
         patch.object(db, 'atualizar_tabela') as atualizar:
        assert app.test_client().patch(path, json={'ativo': True}).status_code == 404
        atualizar.assert_not_called()


@pytest.mark.parametrize('path', ['/clientes', '/fazendas', '/usuarios', '/equipamentos', '/operadores'])
def test_listas_ocultam_excluidos(path):
    with patch.object(db, '_request_json', return_value=[]) as request:
        assert app.test_client().get(path).status_code == 200
    assert request.call_args.kwargs['params']['excluido_em'] == 'is.null'


def test_historico_ainda_consulta_maquina_excluida():
    def consultar(tabela, **kwargs):
        if tabela == 'fazenda':
            return [{'id_fazenda': 1, 'nome': 'Antiga fazenda'}]
        return [{'id_equipamento': 1, 'nome': 'Antiga', 'fk_fazenda_id_fazenda': 1,
                 'dispositivo_id': 'OLD', 'excluido_em': '2026-01-01'}] if tabela == 'equipamentos' else []
    with patch.object(db, 'consultar_tabela', side_effect=consultar), \
         patch('app.consultar_eventos', return_value=[]):
        response = app.test_client().get('/eventos?equipamento=1')
    assert response.status_code == 200
    assert response.json['equipamento']['nome'] == 'Antiga'
