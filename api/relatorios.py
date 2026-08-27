from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List

import llm
from scores import calcular_scores


# ---------------------------------------------------------------------------
# Relatório bruto (factual) - inalterado
# ---------------------------------------------------------------------------

def montar_relatorio_bruto(dispositivo: str, dias: int, resumo_por_dia: List[Dict[str, Any]], eventos: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        'tipo': 'relatorio_bruto',
        'dispositivo': dispositivo,
        'gerado_em': datetime.now(timezone.utc).isoformat(),
        'periodo_dias': dias,
        'resumo_por_dia': resumo_por_dia,
        'eventos': eventos,
        'total_eventos': len(eventos),
    }


# ---------------------------------------------------------------------------
# Prompt: os scores JA vem calculados e entram como fato dado
# ---------------------------------------------------------------------------

def montar_prompt(dispositivo: str, dias: int, scores: Dict[str, Any], eventos: List[Dict[str, Any]]) -> str:
    dados = json.dumps(
        {
            'dispositivo': dispositivo,
            'dias': dias,
            'scores_ja_calculados': {
                'score_furto': scores['score_furto'],
                'classificacao_furto': scores['classificacao_furto'],
                'score_incendio': scores['score_incendio'],
                'classificacao_incendio': scores['classificacao_incendio'],
                'detalhamento': scores['detalhamento'],
            },
            'eventos': eventos,
        },
        ensure_ascii=False,
        indent=2,
    )

    header = (
        "Voce e um analista de risco de seguros. Escreva a analise para o dispositivo "
        + dispositivo + " com base nos dados abaixo.\n\n"
        "Regras obrigatorias:\n"
        "1. Os scores JA foram calculados de forma deterministica e sao FATO DADO. "
        "NAO recalcule, NAO altere e NAO conteste esses numeros - apenas os justifique.\n"
        "2. Toda afirmacao deve citar o numero (score ou contagem de eventos) que a sustenta.\n"
        "3. Se os dados nao permitirem uma conclusao, informe explicitamente.\n"
        "4. Nao invente causas.\n"
        "5. Escreva em portugues, com linguagem adequada para seguros.\n\n"
        "Dados:\n"
    )

    exemplo = (
        "Retorne APENAS um JSON valido com este formato (use os scores dados, nao os recalcule):\n"
        "{\n"
        '  "justificativa_furto": "",\n'
        '  "justificativa_incendio": "",\n'
        '  "recomendacoes": [],\n'
        '  "limitacoes": ""\n'
        "}\n"
    )

    return (header + dados + "\n\n" + exemplo).strip()


# ---------------------------------------------------------------------------
# Narrativa por template (fallback deterministico a partir dos scores)
# ---------------------------------------------------------------------------

def _recomendacoes_por_classificacao(classificacao: str, eixo: str) -> List[str]:
    if classificacao == 'ALTO':
        return [f'Risco de {eixo} ALTO: acionar verificacao imediata e revisar a apolice.']
    if classificacao == 'MEDIO':
        return [f'Risco de {eixo} MEDIO: monitorar de perto nas proximas leituras.']
    return [f'Risco de {eixo} BAIXO: manter o monitoramento de rotina.']


def montar_fallback(scores: Dict[str, Any], erro: str | None = None) -> Dict[str, Any]:
    n_furto = scores['eventos_considerados']['furto']
    n_incendio = scores['eventos_considerados']['incendio']
    dias = scores['periodo_dias']

    limitacoes = ('Analise gerada por template (sem IA): os numeros sao deterministicos e o '
                  'texto e padronizado.')
    if erro:
        e = str(erro)
        if '429' in e or 'Too Many Requests' in e:
            limitacoes += ' Limite de uso da IA atingido temporariamente; tente novamente em instantes.'
        else:
            limitacoes += f' Provedor de IA indisponivel: {e}'

    return {
        'justificativa_furto': (
            f"Score de furto {scores['score_furto']} ({scores['classificacao_furto']}), "
            f"a partir de {n_furto} evento(s) de furto em {dias} dia(s)."
        ),
        'justificativa_incendio': (
            f"Score de incendio {scores['score_incendio']} ({scores['classificacao_incendio']}), "
            f"a partir de {n_incendio} evento(s) de incendio em {dias} dia(s)."
        ),
        'recomendacoes': (
            _recomendacoes_por_classificacao(scores['classificacao_furto'], 'furto')
            + _recomendacoes_por_classificacao(scores['classificacao_incendio'], 'incendio')
        ),
        'limitacoes': limitacoes,
    }


# ---------------------------------------------------------------------------
# Relatorio de risco: scores deterministicos + camada de IA, sempre HTTP 200
# ---------------------------------------------------------------------------

def montar_relatorio_risco(dispositivo: str, dias: int, resumo_por_dia: List[Dict[str, Any]], eventos: List[Dict[str, Any]]) -> Dict[str, Any]:
    scores = calcular_scores(dispositivo, dias, eventos)
    prompt = montar_prompt(dispositivo, dias, scores, eventos)
    resultado = llm.analisar_risco(prompt)
    origem = resultado['origem']

    base = {
        'tipo': 'relatorio_risco',
        'dispositivo': dispositivo,
        'periodo_dias': dias,
        'origem_da_analise': origem,
        # scores SEMPRE vem do calculo deterministico, nunca do LLM
        'score_furto': scores['score_furto'],
        'score_incendio': scores['score_incendio'],
        'classificacao_furto': scores['classificacao_furto'],
        'classificacao_incendio': scores['classificacao_incendio'],
    }

    if origem == 'llm':
        analise = resultado.get('analise', {})
        base.update({
            'justificativa_furto': str(analise.get('justificativa_furto', '')),
            'justificativa_incendio': str(analise.get('justificativa_incendio', '')),
            'recomendacoes': analise.get('recomendacoes', []),
            'limitacoes': str(analise.get('limitacoes', '')),
        })
    elif origem == 'prompt_apenas':
        base.update(montar_fallback(scores))
        base['prompt_gerado'] = prompt
    else:  # fallback
        base.update(montar_fallback(scores, erro=resultado.get('erro')))
        base['prompt_gerado'] = prompt

    return base
