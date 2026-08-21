import os
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

SUPABASE_URL = os.getenv('SUPABASE_URL', '').strip()
SUPABASE_SECRET_KEY = os.getenv('SUPABASE_SECRET_KEY', '').strip()

if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
    raise SystemExit('Configure SUPABASE_URL e SUPABASE_SECRET_KEY no arquivo .env')

headers = {
    'apikey': SUPABASE_SECRET_KEY,
    'Authorization': f'Bearer {SUPABASE_SECRET_KEY}',
    'Content-Type': 'application/json',
}

base_url = f'{SUPABASE_URL.rstrip("/")}/rest/v1'

for tabela in ['telemetria', 'eventos', 'resumo_diario']:
    url = f'{base_url}/{tabela}?select=*' 
    try:
        response = requests.get(url, headers=headers, timeout=20)
        print(f'Tabela: {tabela}')
        print(f'Status: {response.status_code}')
        print(response.text[:300])
        print('-' * 60)
    except Exception as exc:
        print(f'Tabela: {tabela}')
        print(f'Erro: {exc}')
        print('-' * 60)
