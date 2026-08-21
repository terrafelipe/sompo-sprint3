import os
import sys

# Permite rodar de qualquer lugar: poe a raiz da API (pasta pai de scripts/) no path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch

from app import app


with patch('app.consultar_resumo', return_value=[{'dia': '2026-08-19', 'amostras': 10}]), \
     patch('app.consultar_eventos', return_value=[{'id': 1, 'tipo': 'furto_movimento', 'severidade': 4}]), \
     patch('llm.LLM_API_KEY', ''):
    client = app.test_client()
    response = client.get('/relatorio/risco?dispositivo=SOMPO-ESP32&dias=7')
    print('status:', response.status_code)
    try:
        print('json:', response.get_json())
    except Exception:
        print('raw:', response.data)
