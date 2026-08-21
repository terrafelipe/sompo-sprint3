from unittest.mock import patch

import relatorios

print('LLM_API_KEY repr:', repr(relatorios.LLM_API_KEY))
res = relatorios.montar_relatorio_risco('SOMPO-ESP32', 7, [{'dia':'2026-08-19','amostras':10}], [{'id':1,'tipo':'furto_movimento','severidade':4}])
print('result:', res)
