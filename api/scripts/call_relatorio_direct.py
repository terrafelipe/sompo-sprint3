import os
import sys

# Permite rodar de qualquer lugar: poe a raiz da API (pasta pai de scripts/) no path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import llm
import relatorios

# Nao imprime a chave em si (segredo) - so se esta configurada.
print('LLM_API_KEY configurada:', bool(llm.LLM_API_KEY))
res = relatorios.montar_relatorio_risco(
    'SOMPO-ESP32', 7,
    [{'dia': '2026-08-19', 'amostras': 10}],
    [{'id': 1, 'tipo': 'furto_movimento', 'severidade': 4}],
)
print('result:', res)
