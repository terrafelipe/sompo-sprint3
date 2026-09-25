"""Troca por hash as senhas do painel que ainda estao em texto puro.

Rode DEPOIS de publicar o codigo que entende hash (senao ninguem entra ate o deploy).
    .venv\\Scripts\\python.exe tools\\migrar_senhas_hash.py --simular   # so lista
    .venv\\Scripts\\python.exe tools\\migrar_senhas_hash.py             # grava
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))

from werkzeug.security import generate_password_hash  # noqa: E402

import supabase_client as db  # noqa: E402

# Mesmas regras de app._senha_confere: hash conhecido ou conta bloqueada ('!') ficam como estao.
PREFIXOS_HASH = ('scrypt:', 'pbkdf2:')
SENHA_BLOQUEADA = '!'


def main(argv):
    simular = '--simular' in argv[1:]
    usuarios = db.consultar_todos('usuario', select='id_usuario,usuario,senha', order='id_usuario.asc')
    pendentes = [u for u in usuarios
                 if u.get('senha') and u['senha'] != SENHA_BLOQUEADA and not u['senha'].startswith(PREFIXOS_HASH)]
    for u in pendentes:
        if not simular:
            db.atualizar_tabela('usuario', {'id_usuario': f"eq.{u['id_usuario']}"},
                                {'senha': generate_password_hash(u['senha'])})
        print(f"{'(simulado) ' if simular else ''}{u['usuario']}: senha em texto -> hash")
    print(f'{len(pendentes)} de {len(usuarios)} logins {"precisam de" if simular else "passaram para"} hash.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
