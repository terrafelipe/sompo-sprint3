"""tools/definir_senha.py e tools/migrar_senhas_hash.py (banco simulado)."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import check_password_hash, generate_password_hash

TOOLS = Path(__file__).resolve().parents[2] / 'tools'


def _carregar(nome):
    spec = importlib.util.spec_from_file_location(nome, TOOLS / f'{nome}.py')
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


USUARIOS = [
    {'id_usuario': 1, 'usuario': 'texto', 'senha': 'antiga-123'},
    {'id_usuario': 2, 'usuario': 'hash', 'senha': generate_password_hash('x')},
    {'id_usuario': 3, 'usuario': 'bloqueado', 'senha': '!'},
    {'id_usuario': 4, 'usuario': 'vazio', 'senha': None},
]


def test_migracao_so_troca_senha_em_texto_puro():
    migrar = _carregar('migrar_senhas_hash')
    with patch.object(migrar.db, 'consultar_todos', return_value=USUARIOS), \
         patch.object(migrar.db, 'atualizar_tabela') as gravar:
        assert migrar.main(['migrar_senhas_hash.py']) == 0
    assert gravar.call_count == 1
    tabela, filtros, dados = gravar.call_args.args
    assert tabela == 'usuario' and filtros == {'id_usuario': 'eq.1'}
    assert check_password_hash(dados['senha'], 'antiga-123')


def test_migracao_simulada_nao_grava():
    migrar = _carregar('migrar_senhas_hash')
    with patch.object(migrar.db, 'consultar_todos', return_value=USUARIOS), \
         patch.object(migrar.db, 'atualizar_tabela') as gravar:
        assert migrar.main(['migrar_senhas_hash.py', '--simular']) == 0
    gravar.assert_not_called()


def test_definir_senha_grava_hash():
    definir = _carregar('definir_senha')
    with patch.object(definir.db, 'buscar_usuario', return_value={'id_usuario': 8, 'usuario': 'ana'}), \
         patch.object(definir.getpass, 'getpass', side_effect=['nova-senha-forte', 'nova-senha-forte']), \
         patch.object(definir.db, 'atualizar_tabela') as gravar:
        assert definir.main(['definir_senha.py', 'ana']) == 0
    tabela, filtros, dados = gravar.call_args.args
    assert filtros == {'id_usuario': 'eq.8'} and check_password_hash(dados['senha'], 'nova-senha-forte')


def test_definir_senha_recusa_curta_ou_diferente():
    definir = _carregar('definir_senha')
    for digitadas in (['curta', 'curta'], ['nova-senha-forte', 'outra-senha-forte']):
        with patch.object(definir.db, 'buscar_usuario', return_value={'id_usuario': 8, 'usuario': 'ana'}), \
             patch.object(definir.getpass, 'getpass', side_effect=digitadas), \
             patch.object(definir.db, 'atualizar_tabela') as gravar:
            assert definir.main(['definir_senha.py', 'ana']) == 1
        gravar.assert_not_called()


def test_definir_senha_de_usuario_inexistente_falha():
    definir = _carregar('definir_senha')
    with patch.object(definir.db, 'buscar_usuario', return_value=None), \
         patch.object(definir.db, 'atualizar_tabela') as gravar:
        assert definir.main(['definir_senha.py', 'ninguem']) == 1
    gravar.assert_not_called()
