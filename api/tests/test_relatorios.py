from unittest.mock import patch

from app import app


def test_relatorio_bruto():
    client = app.test_client()
    with patch('app.consultar_resumo', return_value=[{'dia': '2026-08-19', 'amostras': 10}]), \
         patch('app.consultar_eventos', return_value=[{'id': 1, 'tipo': 'chama_detectada'}]):
        response = client.get('/relatorio/bruto?dispositivo=SOMPO-ESP32&dias=7')
    assert response.status_code == 200
    data = response.get_json()
    assert data['tipo'] == 'relatorio_bruto'
    assert data['dispositivo'] == 'SOMPO-ESP32'
    assert data['periodo_dias'] == 7
    assert data['total_eventos'] == 1


def test_relatorio_risco_sem_llm_key():
    # Sem LLM_API_KEY a origem e 'prompt_apenas' e o endpoint continua 200.
    client = app.test_client()
    with patch('app.consultar_resumo', return_value=[{'dia': '2026-08-19', 'amostras': 10}]), \
         patch('app.consultar_eventos', return_value=[{'id': 1, 'tipo': 'furto_movimento', 'severidade': 4}]), \
         patch('llm.LLM_API_KEY', ''):
        response = client.get('/relatorio/risco?dispositivo=SOMPO-ESP32&dias=7')
    assert response.status_code == 200
    data = response.get_json()
    assert data['tipo'] == 'relatorio_risco'
    assert data['origem_da_analise'] == 'prompt_apenas'
    assert 'prompt_gerado' in data
    # score vem do calculo deterministico (furto_movimento sev 4 -> 40)
    assert data['score_furto'] == 40
