"""O texto de template (sem IA) e o prompt da IA mudam com o periodo, nao so com a classificacao."""
import re
from unittest.mock import patch

import llm
from relatorios import montar_fallback, montar_prompt, montar_relatorio_risco
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
    assert 'Período curto' in r7['limitacoes'] and 'Período curto' not in r90['limitacoes']
    # Tipo mais frequente com a contagem do periodo.
    assert '30x capô aberto' in ' '.join(r90['recomendacoes'])
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
    assert 'Nenhuma leitura de telemetria nos últimos 30 dia(s)' in r['limitacoes']


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
    assert 'Período curto' in r['limitacoes'] and 'Provedor de IA indisponível' in r['limitacoes']


# Palavras que o template escrevia sem acento. Texto exibido ao cliente e impresso no PDF.
SEM_ACENTO = re.compile(r'\b(ultimos?|periodo|incendio|ocorrencias?|analise|numeros|deterministicos|verificacao|'
                        r'apolice|proximas|cracha|capo|adulteracao|vibracao|critico|atencao|fumaca|maxima|'
                        r'indisponivel|so|MEDIO)\b', re.I)


def _textos(r):
    return [v for v in (*(r[c] for c in ('resumo', 'justificativa_furto', 'justificativa_incendio', 'limitacoes')),
                        *r['recomendacoes']) if isinstance(v, str)]


def test_template_sai_todo_acentuado():
    tipos = ['furto_adulteracao', 'furto_cerca', 'furto_capo', 'furto_tanque', 'operador_nao_autorizado',
             'sensor_falha', 'chama_detectada', 'escape_critico', 'escape_atencao', 'fumaca_detectada']
    scores = {'periodo_dias': 7, 'eventos_considerados': {'furto': 6, 'incendio': 4},
              'classificacao_furto': 'MEDIO', 'classificacao_incendio': 'ALTO', 'score_furto': 50, 'score_incendio': 80,
              'detalhamento': {t: {'eixo': 'incendio' if t in ('chama_detectada', 'escape_critico', 'escape_atencao',
                                                                'fumaca_detectada') else 'furto',
                                   'quantidade': 2, 'pontos': 20} for t in tipos}}
    textos = []
    for erro in (None, '429 Too Many Requests', 'falha qualquer'):
        r = montar_fallback(scores, erro=erro, resumo_por_dia=RESUMO_7)
        textos += _textos(r)
    textos += _textos(_sem_ia(7, RESUMO_7, EVENTOS_7)) + _textos(_sem_ia(90, RESUMO_90, EVENTOS_90))
    textos += _textos(_sem_ia(30, [], []))
    achados = {m.group(0) for t in textos for m in SEM_ACENTO.finditer(t)}
    assert not achados, f'texto do template sem acento: {sorted(achados)}'
    todo = ' '.join(textos)
    for esperado in ['últimos 7 dia(s)', 'incêndio', 'MÉDIO', 'Período curto', 'Análise gerada por template',
                     'números são determinísticos', 'é padronizado', 'Ocorrências:', 'capô aberto', 'partida sem crachá',
                     'escape crítico', 'fumaça', 'apólice', 'próximas leituras', 'só os eventos', 'máxima vista']:
        assert esperado in todo, esperado
