import json
import sys
from urllib import request, error

URLS = [
    'http://localhost:5000/saude',
    'http://localhost:5000/telemetria?limite=5',
    'http://localhost:5000/eventos?dias=7',
    'http://localhost:5000/resumo?dias=10',
    'http://localhost:5000/relatorio/bruto?dias=7',
    'http://localhost:5000/relatorio/risco?dias=7',
]


for url in URLS:
    try:
        with request.urlopen(url, timeout=20) as response:
            body = response.read().decode('utf-8')
            status = response.status
            payload = json.loads(body) if body else {}
            ok = status < 400
            print(f'URL: {url}')
            print(f'Status HTTP: {status}')
            print(f'JSON: {payload}')
            print('Resultado: PASSOU' if ok else 'Resultado: FALHOU')
            print('-' * 60)
    except Exception as exc:
        print(f'URL: {url}')
        print(f'Status HTTP: ERRO')
        print(f'JSON: {str(exc)}')
        print('Resultado: FALHOU')
        print('-' * 60)
