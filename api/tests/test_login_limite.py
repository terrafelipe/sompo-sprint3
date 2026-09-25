"""Limite de tentativas no /login: 5 falhas em 15 min travam o usuario (por IP de conexao)."""
from unittest.mock import patch

from werkzeug.security import generate_password_hash

import app

SENHA = 'certa-12345'
USUARIOS = {
    'ana': {'id_usuario': 1, 'usuario': 'ana', 'senha': generate_password_hash(SENHA), 'role': 'sompo'},
    'bia': {'id_usuario': 2, 'usuario': 'bia', 'senha': generate_password_hash(SENHA), 'role': 'sompo'},
}


def _tentar(client, usuario, senha, agora=1_000_000.0):
    with patch('app.PAINEL_SENHA', 'liga-o-login'), patch('app.buscar_usuario', side_effect=USUARIOS.get), \
         patch('app.time.time', return_value=agora):
        return client.post('/login', data={'usuario': usuario, 'senha': senha})


def test_sexta_falha_seguida_e_bloqueada_com_retry_after():
    client = app.app.test_client()
    for _ in range(5):
        assert _tentar(client, 'ana', 'errada').status_code == 401
    bloqueada = _tentar(client, 'ana', 'errada')
    assert bloqueada.status_code == 429
    assert int(bloqueada.headers['Retry-After']) > 0
    assert 'Muitas tentativas' in bloqueada.get_data(as_text=True)


def test_bloqueio_vale_ate_para_a_senha_certa():
    client = app.app.test_client()
    for _ in range(5):
        _tentar(client, 'ana', 'errada')
    assert _tentar(client, 'ana', SENHA).status_code == 429


def test_acertar_zera_o_contador():
    client = app.app.test_client()
    for _ in range(4):
        _tentar(client, 'ana', 'errada')
    assert _tentar(client, 'ana', SENHA).status_code == 302
    outro = app.app.test_client()
    for _ in range(5):
        assert _tentar(outro, 'ana', 'errada').status_code == 401


def test_outro_usuario_nao_e_afetado():
    client = app.app.test_client()
    for _ in range(6):
        _tentar(client, 'ana', 'errada')
    assert _tentar(client, 'bia', SENHA).status_code == 302


def test_passada_a_janela_libera_de_novo():
    client = app.app.test_client()
    for _ in range(5):
        _tentar(client, 'ana', 'errada', agora=1_000_000.0)
    assert _tentar(client, 'ana', SENHA, agora=1_000_000.0 + 15 * 60 + 1).status_code == 302
