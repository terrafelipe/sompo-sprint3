from unittest.mock import patch

import documento
from app import app


def test_para_brasilia_converte_utc_para_menos_3():
    # 17:04 UTC deve virar 14:04 em Brasília (UTC-3).
    assert documento.para_brasilia('2026-08-21T17:04:04+00:00') == '21/08/2026 14:04'


def test_para_brasilia_valor_vazio():
    assert documento.para_brasilia(None) == '—'
    assert documento.para_brasilia('') == '—'


def test_montar_docx_gera_arquivo_valido():
    relatorio = {
        'dispositivo': 'SOMPO-ESP32', 'periodo_dias': 7, 'origem_da_analise': 'llm',
        'score_furto': 40, 'classificacao_furto': 'MEDIO',
        'score_incendio': 10, 'classificacao_incendio': 'BAIXO',
        'justificativa_furto': 'x', 'justificativa_incendio': 'y',
        'recomendacoes': ['a', 'b'], 'limitacoes': 'z',
    }
    eventos = [{'criado_em': '2026-08-21T17:04:04+00:00', 'tipo': 'furto_movimento', 'severidade': 2}]
    conteudo = documento.montar_docx(relatorio, eventos)
    # .docx é um zip: começa com a assinatura 'PK'.
    assert conteudo[:2] == b'PK'
    assert len(conteudo) > 1000


def test_endpoint_docx_retorna_word():
    client = app.test_client()
    # LLM_API_KEY='' força o caminho offline (prompt_apenas): sem rede, determinístico.
    with patch('app.consultar_resumo', return_value=[]), \
         patch('app.consultar_eventos', return_value=[]), \
         patch('llm.LLM_API_KEY', ''):
        response = client.get('/relatorio/risco.docx?dias=7')
    assert response.status_code == 200
    assert 'wordprocessingml' in response.headers['Content-Type']
    assert response.headers['Content-Disposition'].startswith('attachment')
    assert response.data[:2] == b'PK'
