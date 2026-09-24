"""/relatorio/risco?ia=0: medidores rapidos, sem esperar o LLM.
O refresh de 5 s do painel usa ia=0; o texto da IA e pedido a parte."""
from unittest.mock import patch

from app import app

EVENTOS = [{'id': 1, 'tipo': 'furto_adulteracao', 'severidade': 4}]   # furto -> score 40


def _get(url):
    with patch('app.consultar_resumo', return_value=[]), \
         patch('app.consultar_eventos', return_value=EVENTOS):
        return app.test_client().get(url)


def _nao_chamar(*_a, **_k):
    raise AssertionError('ia=0 nao pode chamar o LLM')


def test_ia_0_nao_chama_o_llm_e_devolve_os_scores():
    with patch('llm.LLM_API_KEY', 'chave-fake'), patch('llm.analisar_risco', side_effect=_nao_chamar):
        r = _get('/relatorio/risco?dispositivo=SOMPO-ESP32&dias=7&ia=0')
    assert r.status_code == 200
    d = r.get_json()
    assert d['score_furto'] == 40 and d['score_incendio'] == 0
    assert d['classificacao_furto'] == 'MEDIO'
    assert d['origem_da_analise'] == 'prompt_apenas'
    # Mesmo formato de hoje: detalhamento, faixas, anterior e texto de template.
    for campo in ('detalhamento', 'pontos_acumulados', 'faixas', 'anterior', 'eventos_considerados',
                  'resumo', 'justificativa_furto', 'justificativa_incendio', 'recomendacoes', 'limitacoes'):
        assert campo in d, campo
    assert d['resumo'] and d['recomendacoes']
    assert 'template' in d['limitacoes']


def test_ia_0_ignora_novo():
    with patch('llm.LLM_API_KEY', 'chave-fake'), patch('llm.analisar_risco', side_effect=_nao_chamar):
        r = _get('/relatorio/risco?dispositivo=SOMPO-ESP32&dias=7&ia=0&novo=1')
    assert r.status_code == 200


def test_sem_ia_0_continua_chamando_o_llm():
    chamado = {}

    def fake(prompt, forcar=False):
        chamado['forcar'] = forcar
        return {'origem': 'llm', 'analise': {'resumo': 'texto da ia'}, 'gerado_em': '2026-09-24T12:00:00+00:00'}

    with patch('llm.analisar_risco', side_effect=fake):
        r = _get('/relatorio/risco?dispositivo=SOMPO-ESP32&dias=7&novo=1')
    assert r.status_code == 200
    d = r.get_json()
    assert chamado == {'forcar': True}
    assert d['origem_da_analise'] == 'llm' and d['resumo'] == 'texto da ia'
    assert d['score_furto'] == 40
