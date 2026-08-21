"""Plano B (passo 6 do plano_final_sprint3.md): captura a resposta JSON de cada
endpoint e salva em arquivo, como seguro contra falha de Wi-Fi na apresentacao.

Uso (com a API rodando em localhost:5000):
    python scripts/salvar_plano_b.py
    python scripts/salvar_plano_b.py --dispositivo SOMPO-ESP32 --dias 7

Read-only: so faz GET e grava os JSONs em api/plano_b/.
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib import request, error

BASE_DIR = Path(__file__).resolve().parent.parent
SAIDA = BASE_DIR / 'plano_b'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5000')
    ap.add_argument('--dispositivo', default='SOMPO-ESP32')
    ap.add_argument('--dias', default='7')
    args = ap.parse_args()

    d, dias = args.dispositivo, args.dias
    endpoints = {
        'scores': f'/scores?dispositivo={d}&dias={dias}',
        'telemetria': f'/telemetria?dispositivo={d}&limite=50',
        'eventos': f'/eventos?dispositivo={d}&dias={dias}',
        'relatorio_bruto': f'/relatorio/bruto?dispositivo={d}&dias={dias}',
        'relatorio_risco': f'/relatorio/risco?dispositivo={d}&dias={dias}',
    }

    # Se a API estiver com auth ligada, manda a chave.
    headers = {}
    api_key = os.getenv('SOMPO_API_KEY', '').strip()
    if api_key:
        headers['X-API-Key'] = api_key

    SAIDA.mkdir(exist_ok=True)
    carimbo = datetime.now().strftime('%Y%m%d_%H%M%S')
    falhas = 0

    for nome, caminho in endpoints.items():
        url = args.base + caminho
        req = request.Request(url, headers=headers)
        arquivo = SAIDA / f'{nome}_{carimbo}.json'
        try:
            with request.urlopen(req, timeout=20) as resp:
                corpo = resp.read().decode('utf-8')
                payload = json.loads(corpo) if corpo else {}
            arquivo.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'[OK  {resp.status}] {nome:16} -> {arquivo}')
        except error.HTTPError as exc:
            print(f'[ERRO {exc.code}] {nome:16} -> {exc.read().decode("utf-8", "replace")[:120]}')
            falhas += 1
        except Exception as exc:
            print(f'[FALHA    ] {nome:16} -> {type(exc).__name__}: {exc}')
            falhas += 1

    print(f'\nArquivos em: {SAIDA}')
    return 1 if falhas else 0


if __name__ == '__main__':
    sys.exit(main())
