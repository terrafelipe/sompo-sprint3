import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')


def _get_env(name: str, default: str = '') -> str:
    return os.getenv(name, default).strip()


SUPABASE_URL = _get_env('SUPABASE_URL')
SUPABASE_SECRET_KEY = _get_env('SUPABASE_SECRET_KEY')
LLM_API_KEY = _get_env('LLM_API_KEY')
LLM_MODEL = _get_env('LLM_MODEL', 'gemini-flash-lite-latest')
FLASK_HOST = _get_env('FLASK_HOST', '127.0.0.1')
FLASK_PORT = int(_get_env('FLASK_PORT', '5000'))
FLASK_DEBUG = _get_env('FLASK_DEBUG', 'false').lower() in {'1', 'true', 'yes', 'y'}

# Seguranca da API (ver docs/SEGURANCA.md)
# SOMPO_API_KEY vazia = autenticacao desligada (modo demo). Definida = toda rota
# (menos /saude) exige o header 'X-API-Key' com esse valor.
SOMPO_API_KEY = _get_env('SOMPO_API_KEY')
# Login do painel publico (HTTP Basic Auth). PAINEL_SENHA vazia = login desligado
# (demo local aberta). Definida = TODO o site (painel + endpoints) exige usuario/senha.
PAINEL_USUARIO = _get_env('PAINEL_USUARIO', 'sompo')
PAINEL_SENHA = _get_env('PAINEL_SENHA')
# CORS_ORIGINS: lista separada por virgula. Vazia = nenhuma origem cross-origin
# liberada (padrao seguro). Ex.: "http://localhost:3000,https://painel.exemplo.com".
CORS_ORIGINS = [o.strip() for o in _get_env('CORS_ORIGINS').split(',') if o.strip()]


def validate_supabase_config() -> None:
    if not SUPABASE_URL:
        raise ValueError('SUPABASE_URL não configurada')
    if not SUPABASE_SECRET_KEY:
        raise ValueError('SUPABASE_SECRET_KEY não configurada')


def get_supabase_headers() -> dict:
    validate_supabase_config()
    return {
        'apikey': SUPABASE_SECRET_KEY,
        'Authorization': f'Bearer {SUPABASE_SECRET_KEY}',
        'Content-Type': 'application/json',
    }
