"""Os tres cenarios do /relatorio/risco (passo 4 do plano_final_sprint3.md).
Todos devem responder HTTP 200; so muda o campo origem_da_analise."""
from unittest.mock import patch

from app import app

EVENTOS = [{'id': 1, 'tipo': 'furto_movimento', 'severidade': 4}]   # furto -> score 40


def _get():
    client = app.test_client()
    return client.get('/relatorio/risco?dispositivo=SOMPO-ESP32&dias=7')


def test_origem_prompt_apenas_sem_chave():
    with patch('app.consultar_resumo', return_value=[]), \
         patch('app.consultar_eventos', return_value=EVENTOS), \
         patch('llm.LLM_API_KEY', ''):
        r = _get()
    assert r.status_code == 200
    data = r.get_json()
    assert data['origem_da_analise'] == 'prompt_apenas'
    assert 'prompt_gerado' in data


def test_origem_llm_com_provedor_ok():
    # Provedor devolve numeros proprios (score_furto=999); devem ser IGNORADOS -
    # o score final vem do calculo deterministico (40).
    fake = {
        'justificativa_furto': 'texto do llm',
        'justificativa_incendio': '',
        'recomendacoes': ['r1'],
        'limitacoes': '',
        'score_furto': 999,
    }
    with patch('app.consultar_resumo', return_value=[]), \
         patch('app.consultar_eventos', return_value=EVENTOS), \
         patch('llm.LLM_API_KEY', 'chave-fake'), \
         patch('llm._chamar_provedor', return_value=fake):
        r = _get()
    assert r.status_code == 200
    data = r.get_json()
    assert data['origem_da_analise'] == 'llm'
    assert data['justificativa_furto'] == 'texto do llm'
    assert data['score_furto'] == 40   # forcado do scores.py, nao os 999 do LLM


def test_origem_fallback_provedor_fora():
    def explode(_prompt):
        raise RuntimeError('provedor fora do ar')

    with patch('app.consultar_resumo', return_value=[]), \
         patch('app.consultar_eventos', return_value=EVENTOS), \
         patch('llm.LLM_API_KEY', 'chave-fake'), \
         patch('llm._chamar_provedor', side_effect=explode):
        r = _get()
    assert r.status_code == 200
    data = r.get_json()
    assert data['origem_da_analise'] == 'fallback'
    assert data['score_furto'] == 40
    assert 'provedor fora do ar' in data['limitacoes']
