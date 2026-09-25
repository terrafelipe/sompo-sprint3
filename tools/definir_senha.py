"""Define a senha de um login do painel. Grava so o hash; a senha nunca aparece na tela.

Uso (na raiz do repo, com o api/.env preenchido):
    .venv\\Scripts\\python.exe tools\\definir_senha.py <usuario>
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))

from werkzeug.security import generate_password_hash  # noqa: E402

import supabase_client as db  # noqa: E402

TAMANHO_MINIMO = 10


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    usuario = db.buscar_usuario(argv[1])
    if not usuario or usuario.get('excluido_em'):
        print(f'Usuario {argv[1]!r} nao encontrado.')
        return 1
    senha = getpass.getpass('Nova senha: ')
    if len(senha) < TAMANHO_MINIMO:
        print(f'Senha curta: use pelo menos {TAMANHO_MINIMO} caracteres.')
        return 1
    if senha != getpass.getpass('Repita a senha: '):
        print('As duas senhas nao conferem.')
        return 1
    db.atualizar_tabela('usuario', {'id_usuario': f"eq.{usuario['id_usuario']}"},
                        {'senha': generate_password_hash(senha)})
    print(f'Senha de {argv[1]} definida.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
