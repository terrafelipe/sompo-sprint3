"""O texto de template (sem IA) e o prompt da IA mudam com o periodo, nao so com a classificacao."""
from unittest.mock import patch

import llm
from relatorios import montar_prompt, montar_relatorio_risco
from scores import calcular_scores

# 7 dias: 2 eventos fortes (furto 80 -> ALTO), leitura em 3 dos 7 dias.
EVENTOS_7 = [{'tipo': 'furto_cerca', 'severidade': 4}] * 2
RESUMO_7 = [{'dia': f'2026-09-2{i}', 'amostras': 10, 'temp_escape_max': 180} for i in range(3)]
# 90 dias: 40 eventos (furto 100 -> ALTO), leitura nos 90 dias, escape em atencao.
EVENTOS_90 = [{'tipo': 'furto_capo', 'severidade': 2}] * 30 + [{'tipo': 'escape_atencao', 'severidade': 1}] * 10
RESUMO_90 = [{'dia': f'd{i}', 'amostras': 50, 'temp_escape_max': 300 + i} for i in range(90)]


def _sem_ia(dias, resumo, eventos):
    with patch('llm.analisar_risco', side_effect=AssertionError('sem IA nao chama o provedor')), \
         patch('llm._chamar_provedor', side_effect=AssertionError('sem IA nao chama o provedor')):
        return montar_relatorio_risco('SOMPO-ESP32', dias, resumo, eventos, usar_ia=False)


def test_mesma_classificacao_com_periodos_diferentes_gera_texto_diferente():
    r7, r90 = _sem_ia(7, RESUMO_7, EVENTOS_7), _sem_ia(90, RESUMO_90, EVENTOS_90)
    assert r7['classificacao_furto'] == r90['classificacao_furto'] == 'ALTO'
    assert r7['recomendacoes'] != r90['recomendacoes']
    assert r7['limitacoes'] != r90['limitacoes']


def test_template_usa_os_dados_do_periodo():
    r7, r90 = _sem_ia(7, RESUMO_7, EVENTOS_7), _sem_ia(90, RESUMO_90, EVENTOS_90)
    # Cobertura: dias com leitura e dias sem leitura.
    assert 'sem leitura em 4 de 7 dia(s)' in ' '.join(r7['recomendacoes'])
    assert 'Leituras em 90 de 90 dia(s)' in r90['limitacoes']
    # Periodo curto avisa amostra pequena; o longo nao.
    assert 'Periodo curto' in r7['limitacoes'] and 'Periodo curto' not in r90['limitacoes']
    # Tipo mais frequente com a contagem do periodo.
    assert '30x capo aberto' in ' '.join(r90['recomendacoes'])
    assert '2x cerca virtual' in ' '.join(r7['recomendacoes'])
    # Temperatura maxima vista (so quando houve alerta de escape).
    assert '389' in ' '.join(r90['recomendacoes'])
    assert not any('escape' in r.lower() for r in r7['recomendacoes'])


def test_template_mantem_frases_fixas_e_sem_travessao():
    r = _sem_ia(7, RESUMO_7, EVENTOS_7)
    assert 'template' in r['limitacoes']
    assert r['limitacoes'].endswith('Identificação por crachá não comprova condução contínua nem responsabilidade pelo acidente.')
    texto = ' '.join(r['recomendacoes']) + r['limitacoes']
    assert '—' not in texto and '–' not in texto


def test_sem_leitura_nenhuma_no_periodo():
    r = _sem_ia(30, [], [])
    assert 'Nenhuma leitura de telemetria nos ultimos 30 dia(s)' in r['limitacoes']


def test_prompt_da_ia_traz_o_periodo_explicito():
    prompt = montar_prompt('SOMPO-ESP32', 90, calcular_scores('SOMPO-ESP32', 90, EVENTOS_90), EVENTOS_90)
    assert 'ultimos 90 dias' in prompt
    assert prompt != montar_prompt('SOMPO-ESP32', 7, calcular_scores('SOMPO-ESP32', 7, EVENTOS_90), EVENTOS_90)


def test_fallback_de_erro_da_ia_tambem_segue_o_periodo():
    llm.limpar_cache()
    with patch('llm.LLM_API_KEY', 'chave-fake'), patch('llm._chamar_provedor', side_effect=RuntimeError('fora')):
        r = montar_relatorio_risco('SOMPO-ESP32', 7, RESUMO_7, EVENTOS_7)
    llm.limpar_cache()
    assert r['origem_da_analise'] == 'fallback'
    assert 'Periodo curto' in r['limitacoes'] and 'Provedor de IA indisponivel' in r['limitacoes']
