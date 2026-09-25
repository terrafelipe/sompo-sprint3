"""Achados da revisao cruzada no /login: memoria do limite, IP atras do adapter, timing e regravacao."""
from unittest.mock import patch

from werkzeug.security import generate_password_hash

import app

SENHA = 'certa-12345'
ANA = {'id_usuario': 1, 'usuario': 'ana', 'senha': generate_password_hash(SENHA), 'role': 'sompo'}


def _post(client, usuario, senha, xff=None, buscar=None):
    headers = {'X-Forwarded-For': xff} if xff else {}
    with patch('app.PAINEL_SENHA', 'liga-o-login'), \
         patch('app.buscar_usuario', side_effect=buscar or (lambda u: ANA if u == 'ana' else None)):
        return client.post('/login', data={'usuario': usuario, 'senha': senha}, headers=headers)


def test_usuario_gigante_nao_vira_chave_gigante():
    _post(app.app.test_client(), 'x' * 100_000, 'errada')
    assert app._falhas_login and all(len(u) <= app._TAMANHO_MAX_USUARIO for u, _ip in app._falhas_login)


def test_registro_de_falhas_tem_teto():
    client = app.app.test_client()
    with patch('app._LIMITE_CHAVES_LOGIN', 10):
        for i in range(30):
            _post(client, f'user{i}', 'errada')
        assert len(app._falhas_login) <= 10


def test_atras_do_adapter_o_ip_vem_do_x_forwarded_for():
    # O Lambda Web Adapter conecta pelo localhost; a AWS acrescenta o IP real ao X-Forwarded-For.
    client = app.app.test_client()
    for _ in range(5):
        _post(client, 'ana', 'errada', xff='1.1.1.1')
    assert _post(client, 'ana', 'errada', xff='1.1.1.1').status_code == 429
    assert _post(client, 'ana', SENHA, xff='2.2.2.2').status_code == 302


def test_x_forwarded_for_falsificado_nao_escapa_do_limite():
    # O cliente pode escrever o que quiser no inicio; o ultimo IP e o que a AWS viu.
    client = app.app.test_client()
    for i in range(5):
        _post(client, 'ana', 'errada', xff=f'9.9.9.{i}, 1.1.1.1')
    assert _post(client, 'ana', 'errada', xff='8.8.8.8, 1.1.1.1').status_code == 429


def test_usuario_inexistente_tambem_calcula_hash():
    # Sem isso o tempo de resposta revela se o usuario existe.
    with patch('app.check_password_hash', wraps=app.check_password_hash) as conferir:
        _post(app.app.test_client(), 'ninguem', 'qualquer')
        _post(app.app.test_client(), 'ana', 'errada')
    assert conferir.call_count == 2


def test_regravacao_so_troca_se_a_senha_ainda_nao_for_hash_e_sem_a_senha_na_url():
    legada = {'id_usuario': 5, 'usuario': 'leo', 'senha': 'antiga, (texto)', 'role': 'sompo'}
    with patch('app.atualizar_tabela') as gravar:
        _post(app.app.test_client(), 'leo', 'antiga, (texto)', buscar=lambda u: legada)
    _tabela, filtros, _dados = gravar.call_args.args
    assert filtros == {'id_usuario': 'eq.5', 'and': '(senha.not.like.scrypt:*,senha.not.like.pbkdf2:*,senha.neq.!)'}
    assert 'antiga' not in str(filtros)


def test_enxurrada_de_nomes_nao_despeja_um_alvo_bloqueado():
    client = app.app.test_client()
    with patch('app._LIMITE_CHAVES_LOGIN', 10):
        for _ in range(5):
            _post(client, 'ana', 'errada', xff='1.1.1.1')
        for i in range(40):
            _post(client, f'enxurrada{i}', 'errada', xff=f'2.2.{i}.1')
        assert len(app._falhas_login) <= 10
        assert _post(client, 'ana', SENHA, xff='1.1.1.1').status_code == 429


def test_enxurrada_nao_zera_um_alvo_com_quatro_falhas():
    # Cenario da revisao: 4 falhas no alvo, enxurrada de nomes (de IPs diferentes) ate o teto,
    # e a 5a falha ainda tem de travar.
    client = app.app.test_client()
    with patch('app._LIMITE_CHAVES_LOGIN', 10):
        for _ in range(4):
            _post(client, 'ana', 'errada', xff='1.1.1.1')
        for i in range(40):
            _post(client, str(i) + 'x' * 200, 'errada', xff=f'2.2.{i}.1')
        assert _post(client, 'ana', 'errada', xff='1.1.1.1').status_code == 401
        assert _post(client, 'ana', SENHA, xff='1.1.1.1').status_code == 429


def test_um_ip_com_muitas_falhas_em_nomes_variados_e_travado():
    client = app.app.test_client()
    for i in range(app._TENTATIVAS_MAX_IP):
        assert _post(client, f'nome{i}', 'errada', xff='3.3.3.3').status_code == 401
    assert _post(client, 'outro-nome', 'errada', xff='3.3.3.3').status_code == 429
    assert _post(client, 'ana', SENHA, xff='4.4.4.4').status_code == 302


def _post_proxy(client, usuario, senha, cf_ip, segredo):
    headers = {'CF-Connecting-IP': cf_ip, 'X-Forwarded-For': '172.64.0.1'}
    if segredo is not None:
        headers['X-Sompo-Proxy'] = segredo
    with patch('app.PAINEL_SENHA', 'liga-o-login'), patch('app.PROXY_SEGREDO', 's3gredo'), \
         patch('app.buscar_usuario', side_effect=lambda u: ANA if u == 'ana' else None):
        return client.post('/login', data={'usuario': usuario, 'senha': senha}, headers=headers)


def test_pelo_worker_com_segredo_o_ip_e_o_do_visitante():
    # Pelo Worker o ultimo X-Forwarded-For e o IP do Worker (compartilhado); com o segredo,
    # vale o CF-Connecting-IP: um visitante nao trava o login do outro.
    client = app.app.test_client()
    for _ in range(5):
        _post_proxy(client, 'ana', 'errada', '1.1.1.1', 's3gredo')
    assert _post_proxy(client, 'ana', 'errada', '1.1.1.1', 's3gredo').status_code == 429
    assert _post_proxy(client, 'ana', SENHA, '2.2.2.2', 's3gredo').status_code == 302


def test_cf_connecting_ip_sem_o_segredo_e_ignorado():
    # Chamando a Function URL direto da para inventar o CF-Connecting-IP: sem segredo nao vale.
    client = app.app.test_client()
    for i in range(5):
        _post_proxy(client, 'ana', 'errada', f'9.9.9.{i}', 'errado')
    assert _post_proxy(client, 'ana', 'errada', '8.8.8.8', None).status_code == 429
