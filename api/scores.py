"""Cálculo determinístico de risco (furto e incêndio) a partir dos eventos.

Regra do projeto (ver plano_final_sprint3.md): os scores são calculados aqui,
ANTES de qualquer prompt, e entram na camada de IA como fato dado. O LLM nunca
recalcula nem contesta esses números.

Módulo puro: sem I/O, sem rede, sem `import requests`. A mesma entrada produz
sempre a mesma saída (determinístico).
"""
from __future__ import annotations

from typing import Any, Dict, List

# Eixo de cada tipo de evento (contrato em CLAUDE-SOMPO.md).
EIXO_POR_TIPO = {
    'furto_movimento': 'furto',
    'furto_cerca': 'furto',
    'furto_capo': 'furto',
    'furto_tanque': 'furto',
    'operador_nao_autorizado': 'furto',
    'sensor_falha': 'furto',          # perder o sensor de adulteracao e evento de furto
    'chama_detectada': 'incendio',
    'escape_critico': 'incendio',
    'escape_atencao': 'incendio',
    'fumaca_detectada': 'incendio',
}

# Severidade padrão por tipo, usada quando o evento não trouxe o campo.
SEVERIDADE_PADRAO = {
    'furto_movimento': 4,
    'furto_cerca': 4,
    'furto_capo': 2,
    'furto_tanque': 3,
    'operador_nao_autorizado': 3,
    'sensor_falha': 3,
    'chama_detectada': 5,
    'escape_critico': 4,
    'escape_atencao': 2,
    'fumaca_detectada': 3,
}

# Pontos que cada nível de severidade adiciona ao score do eixo.
PONTOS_POR_SEVERIDADE = {0: 0, 1: 5, 2: 10, 3: 20, 4: 40, 5: 70}


def _eixo_do_tipo(tipo: str) -> str | None:
    if tipo in EIXO_POR_TIPO:
        return EIXO_POR_TIPO[tipo]
    # Heurística de segurança para tipos novos não mapeados.
    if tipo.startswith('furto') or tipo.startswith('operador'):
        return 'furto'
    if tipo.startswith('escape') or tipo.startswith('chama') or tipo.startswith('fumaca'):
        return 'incendio'
    return None


def _severidade(evento: Dict[str, Any]) -> int:
    sev = evento.get('severidade')
    if sev is None:
        sev = SEVERIDADE_PADRAO.get(evento.get('tipo', ''), 0)
    try:
        sev = int(sev)
    except (TypeError, ValueError):
        sev = 0
    return max(0, min(5, sev))


def _pontos(severidade: int) -> int:
    return PONTOS_POR_SEVERIDADE.get(severidade, 0)


def _classificar(score: int) -> str:
    if score >= 67:
        return 'ALTO'
    if score >= 34:
        return 'MEDIO'
    return 'BAIXO'


def calcular_scores(dispositivo: str, dias: int, eventos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Score 0..100 por eixo, a partir dos eventos do período.

    Determinístico: a saída depende apenas dos argumentos, e o `detalhamento` é
    ordenado por tipo para não variar entre execuções.
    """
    soma = {'furto': 0, 'incendio': 0}
    contagem = {'furto': 0, 'incendio': 0}
    # detalhamento[tipo] = {"eixo", "quantidade", "pontos"}
    detalhamento: Dict[str, Dict[str, Any]] = {}

    for evento in eventos or []:
        tipo = str(evento.get('tipo', ''))
        eixo = _eixo_do_tipo(tipo)
        if eixo is None:
            continue
        pontos = _pontos(_severidade(evento))
        soma[eixo] += pontos
        contagem[eixo] += 1
        linha = detalhamento.setdefault(tipo, {'eixo': eixo, 'quantidade': 0, 'pontos': 0})
        linha['quantidade'] += 1
        linha['pontos'] += pontos

    score_furto = min(100, soma['furto'])
    score_incendio = min(100, soma['incendio'])

    return {
        'dispositivo': dispositivo,
        'periodo_dias': dias,
        'score_furto': score_furto,
        'score_incendio': score_incendio,
        'classificacao_furto': _classificar(score_furto),
        'classificacao_incendio': _classificar(score_incendio),
        'eventos_considerados': {
            'furto': contagem['furto'],
            'incendio': contagem['incendio'],
            'total': contagem['furto'] + contagem['incendio'],
        },
        # dict ordenado por tipo -> saida estavel/deterministica
        'detalhamento': {k: detalhamento[k] for k in sorted(detalhamento)},
    }
