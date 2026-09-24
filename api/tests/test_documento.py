import re
from unittest.mock import patch

import documento
from app import app


RELATORIO = {
    'dispositivo': 'SOMPO-ESP32', 'periodo_dias': 7, 'origem_da_analise': 'llm',
    'equipamento': {'id_equipamento': 1, 'nome': 'Trator A'},
    'fazenda': {'nome': 'Fazenda Boa Vista'},
    'gerado_em': '2026-08-21T17:04:04+00:00',
    'score_furto': 40, 'classificacao_furto': 'MEDIO',
    'score_incendio': 0, 'classificacao_incendio': 'BAIXO',
    'justificativa_furto': 'Duas partidas sem crachá.', 'justificativa_incendio': 'Nada no período.',
    'detalhamento': {'operador_nao_autorizado': {'eixo': 'furto', 'quantidade': 2, 'pontos': 40}},
    'pontos_acumulados': {'furto': 40, 'incendio': 0},
    'recomendacoes': ['Cadastrar os crachás da equipe.'], 'limitacoes': 'Poucos dias de dados.',
}
EVENTO = {'criado_em': '2026-08-21T17:04:04+00:00', 'tipo': 'operador_nao_autorizado', 'severidade': 3}


def texto(conteudo: bytes) -> str:
    return conteudo.decode('latin-1')


def paginas(conteudo: bytes) -> int:
    return len(re.findall(rb'/Type /Page\b', conteudo))


def test_para_brasilia_converte_utc_para_menos_3():
    # 17:04 UTC deve virar 14:04 em Brasília (UTC-3).
    assert documento.para_brasilia('2026-08-21T17:04:04+00:00') == '21/08/2026 14:04'


def test_para_brasilia_valor_vazio():
    assert documento.para_brasilia(None) == '—'
    assert documento.para_brasilia('') == '—'


def test_montar_pdf_gera_arquivo_valido():
    conteudo = documento.montar_pdf(RELATORIO, [EVENTO])
    assert conteudo.startswith(b'%PDF-')
    assert conteudo.rstrip().endswith(b'%%EOF')
    assert paginas(conteudo) == 1


def test_pdf_tem_identificacao_scores_detalhamento_e_eventos(pdf_aberto):
    t = texto(documento.montar_pdf(RELATORIO, [EVENTO]))
    for esperado in ['Relatório de risco', 'Trator A', 'Fazenda Boa Vista', 'SOMPO-ESP32',
                     'Últimos 7 dias', '21/08/2026 14:04', 'Furto', 'Incêndio', 'Médio', 'Baixo',
                     'Duas partidas sem crachá.', 'Partida sem crachá', '3 · Média',
                     'Cadastrar os crachás da equipe.', 'Poucos dias de dados.', 'Data e hora']:
        assert esperado in t, esperado
    assert 'operador_nao_autorizado' not in t


def test_pdf_troca_nomes_tecnicos_e_caracteres_fora_do_latin1(pdf_aberto):
    relatorio = {**RELATORIO, 'justificativa_furto': 'O rc522 falhou — “duas vezes”… 🔥'}
    evento = {**EVENTO, 'tipo': 'furto_adulteracao'}
    t = texto(documento.montar_pdf(relatorio, [evento]))
    assert 'leitor de crachá' in t and 'rc522' not in t
    assert 'falhou - "duas vezes"...' in t
    assert 'Adulteração/vibração' in t and 'furto_adulteracao' not in t


def test_pdf_sem_eventos_avisa(pdf_aberto):
    t = texto(documento.montar_pdf(RELATORIO, []))
    assert 'Nenhum evento registrado no período.' in t


def test_pdf_com_muitos_eventos_quebra_pagina_e_repete_cabecalho(pdf_aberto):
    conteudo = documento.montar_pdf(RELATORIO, [EVENTO] * 120)
    n = paginas(conteudo)
    assert n >= 3
    # A tabela pode começar na 1ª página ou na 2ª; o cabeçalho acompanha cada página dela.
    assert texto(conteudo).count('Data e hora') >= n - 1


def test_endpoint_pdf_retorna_arquivo():
    client = app.test_client()
    # LLM_API_KEY='' força o caminho offline (prompt_apenas): sem rede, determinístico.
    with patch('app.consultar_resumo', return_value=[]), \
         patch('app.consultar_eventos', return_value=[]), \
         patch('llm.LLM_API_KEY', ''):
        response = client.get('/relatorio/risco.pdf?dispositivo=SOMPO-ESP32&dias=30')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'application/pdf'
    disposicao = response.headers['Content-Disposition']
    assert disposicao.startswith('attachment') and disposicao.rstrip('"').endswith('.pdf')
    assert response.data.startswith(b'%PDF-')


def test_word_nao_existe_mais():
    assert app.test_client().get('/relatorio/risco.docx').status_code == 404
