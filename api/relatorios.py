from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

import llm
from scores import FAIXA_ALTO, FAIXA_MEDIO, calcular_scores


# Nomes tecnicos (tipos de evento e sensores) -> nomes legiveis para a seguradora.
# Vale para o texto da IA e entra no prompt como vocabulario obrigatorio.
TIPOS_LEGIVEIS = {
    'furto_adulteracao': 'adulteração/vibração',
    'furto_cerca': 'cerca virtual',
    'furto_capo': 'capô aberto',
    'furto_tanque': 'tanque aberto',
    'furto_movimento': 'movimento suspeito',
    'operador_nao_autorizado': 'partida sem crachá',
    'sensor_falha': 'sensor de adulteração removido',
    'chama_detectada': 'chama detectada',
    'escape_critico': 'escape crítico',
    'escape_atencao': 'escape em atenção',
    'fumaca_detectada': 'fumaça detectada',
}
SENSORES_LEGIVEIS = {
    'reed_capo': 'sensor do capô',
    'reed_tanque': 'sensor do tanque',
    'rc522': 'leitor de crachá (RC522)',
    'ky026': 'sensor de chama (KY-026)',
    'mpu6050': 'acelerômetro (MPU-6050)',
    'max6675': 'sensor de temperatura do escape (MAX6675)',
    'aht10': 'sensor de temperatura e umidade (AHT10)',
}
_LEGIVEIS = {**TIPOS_LEGIVEIS, **SENSORES_LEGIVEIS}
# Uma passada so (a troca nunca e trocada de novo). Engole aspas em volta e um
# "sensor " antes do nome do sensor, para nao virar "sensor sensor do capo".
_RE_TECNICO = re.compile(
    r"(?:\bsensor\s+)?['\"`]?\b(" + '|'.join(sorted(_LEGIVEIS, key=len, reverse=True)) + r")\b['\"`]?",
    re.IGNORECASE,
)


# Se a IA ja escreveu "leitor de cracha (RC522)", a troca do "RC522" geraria
# "leitor de cracha (leitor de cracha (RC522))": este padrao junta de volta.
_RE_DUPLICADO = [
    (re.compile(r'(' + re.escape(r.split(' (')[0]) + r')\s*\(\s*' + re.escape(r) + r'\s*\)', re.IGNORECASE),
     r[len(r.split(' (')[0]):])
    for r in SENSORES_LEGIVEIS.values() if ' (' in r
]


def legivel(texto: str) -> str:
    """Troca nomes tecnicos por nomes legiveis num texto livre."""
    t = _RE_TECNICO.sub(lambda m: _LEGIVEIS[m.group(1).lower()], texto or '')
    for padrao, resto in _RE_DUPLICADO:
        t = padrao.sub(lambda m: m.group(1) + resto, t)
    return t


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

# Janelas longas (30/90 dias) tem centenas de eventos: o prompt leva os totais exatos
# (detalhamento) e so uma amostra dos mais recentes, para nao ficar enorme e lento.
LIMITE_EVENTOS_PROMPT = 60


def montar_prompt(dispositivo: str, dias: int, scores: Dict[str, Any], eventos: List[Dict[str, Any]], contexto=None) -> str:
    eventos = eventos or []
    amostra = eventos[:LIMITE_EVENTOS_PROMPT]   # consultas vem do mais recente para o mais antigo
    dados = json.dumps(
        {
            'dispositivo': dispositivo,
            'dias': dias,
            'identificacao': contexto or {},
            'scores_ja_calculados': {
                'score_furto': scores['score_furto'],
                'classificacao_furto': scores['classificacao_furto'],
                'score_incendio': scores['score_incendio'],
                'classificacao_incendio': scores['classificacao_incendio'],
                'detalhamento': scores['detalhamento'],
            },
            'eventos_na_amostra': f'{len(amostra)} de {len(eventos)} (os mais recentes; os totais estao no detalhamento)',
            'eventos': amostra,
        },
        ensure_ascii=False,
        indent=2,
    )

    header = (
        "Voce e um analista de risco de seguros. Escreva a analise para o dispositivo "
        + str(dispositivo or 'sem dispositivo') + " com base nos dados abaixo.\n\n"
        "Regras obrigatorias:\n"
        "1. Os scores JA foram calculados de forma deterministica e sao FATO DADO. "
        "NAO recalcule, NAO altere e NAO conteste esses numeros - apenas os justifique.\n"
        "2. Toda afirmacao deve citar o numero (score ou contagem de eventos) que a sustenta.\n"
        "3. Se os dados nao permitirem uma conclusao, informe explicitamente.\n"
        "4. Nao invente causas.\n"
        "5. Escreva em portugues, com linguagem adequada para seguros.\n"
        "6. Operador identificado por cracha nao comprova conducao continua nem culpa. "
        "Nao atribua responsabilidade pelo acidente somente pela presenca. "
        "Horarios de ocorrencia ausentes sao desconhecidos; recebimento nao e ocorrencia.\n"
        "7. Nunca escreva nomes tecnicos de eventos ou sensores; use os nomes legiveis: "
        + '; '.join(f'{k} = {v}' for k, v in _LEGIVEIS.items()) + ".\n"
        "8. Preencha TODOS os campos, inclusive o eixo com poucos eventos. "
        "\"resumo\" tem no maximo 2 frases.\n\n"
        "Dados:\n"
    )

    exemplo = (
        "Retorne APENAS um JSON valido com este formato (use os scores dados, nao os recalcule):\n"
        "{\n"
        '  "resumo": "",\n'
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


# Rotulos legiveis por tipo de evento (para a quebra na narrativa do fallback).
_ROTULO_TIPO = {
    'furto_adulteracao': 'adulteracao/vibracao',
    'furto_cerca': 'cerca virtual',
    'furto_capo': 'capo aberto',
    'furto_tanque': 'tanque aberto',
    'operador_nao_autorizado': 'partida sem cracha',
    'sensor_falha': 'sensor de adulteracao removido',
    'chama_detectada': 'chama detectada',
    'escape_critico': 'escape critico',
    'escape_atencao': 'escape em atencao',
    'fumaca_detectada': 'fumaca',
}


def _quebra_por_tipo(detalhamento: Dict[str, Any], eixo: str) -> str:
    itens = [(t, v.get('quantidade', 0)) for t, v in detalhamento.items() if v.get('eixo') == eixo]
    if not itens:
        return ''
    partes = [f"{q}x {_ROTULO_TIPO.get(t, t)}" for t, q in itens]
    return ' Ocorrencias: ' + ', '.join(partes) + '.'


def _frase_eixo(nome: str, score: int, classif: str, n: int, dias: int,
                detalhamento: Dict[str, Any], eixo: str) -> str:
    if n == 0:
        return (f"Risco de {nome} {classif} (score {score}/100): nenhum evento de {nome} "
                f"registrado nos ultimos {dias} dia(s).")
    return (f"Risco de {nome} {classif} (score {score}/100), a partir de {n} evento(s) de {nome} "
            f"nos ultimos {dias} dia(s).{_quebra_por_tipo(detalhamento, eixo)}")


def _resumo_padrao(scores: Dict[str, Any]) -> str:
    n = scores['eventos_considerados']
    return (f"Risco de furto {scores['classificacao_furto']} ({scores['score_furto']}/100) e de incendio "
            f"{scores['classificacao_incendio']} ({scores['score_incendio']}/100) nos ultimos "
            f"{scores['periodo_dias']} dia(s), com {n['furto']} evento(s) de furto e "
            f"{n['incendio']} de incendio.")


def montar_fallback(scores: Dict[str, Any], erro: str | None = None) -> Dict[str, Any]:
    n_furto = scores['eventos_considerados']['furto']
    n_incendio = scores['eventos_considerados']['incendio']
    dias = scores['periodo_dias']
    detalhamento = scores.get('detalhamento', {})

    limitacoes = ('Analise gerada por template (sem IA): os numeros sao deterministicos e o '
                  'texto e padronizado.')
    if erro:
        e = str(erro)
        if '429' in e or 'Too Many Requests' in e:
            limitacoes += ' Limite de uso da IA atingido temporariamente; tente novamente em instantes.'
        else:
            limitacoes += f' Provedor de IA indisponivel: {e}'

    return {
        'resumo': _resumo_padrao(scores),
        'justificativa_furto': _frase_eixo(
            'furto', scores['score_furto'], scores['classificacao_furto'],
            n_furto, dias, detalhamento, 'furto',
        ),
        'justificativa_incendio': _frase_eixo(
            'incendio', scores['score_incendio'], scores['classificacao_incendio'],
            n_incendio, dias, detalhamento, 'incendio',
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

def _pontos_acumulados(detalhamento: Dict[str, Any]) -> Dict[str, int]:
    # Soma sem o teto de 100: mostra o quanto o eixo passou do limite.
    total = {'furto': 0, 'incendio': 0}
    for linha in detalhamento.values():
        total[linha['eixo']] += linha['pontos']
    return total


def montar_relatorio_risco(dispositivo: str, dias: int, resumo_por_dia: List[Dict[str, Any]], eventos: List[Dict[str, Any]], contexto=None, forcar: bool = False) -> Dict[str, Any]:
    scores = calcular_scores(dispositivo, dias, eventos)
    prompt = montar_prompt(dispositivo, dias, scores, eventos, contexto)
    resultado = llm.analisar_risco(prompt, forcar=forcar)
    origem = resultado['origem']

    base = {
        **(contexto or {}),
        'tipo': 'relatorio_risco',
        'dispositivo': dispositivo,
        'periodo_dias': dias,
        'origem_da_analise': origem,
        # scores SEMPRE vem do calculo deterministico, nunca do LLM
        'score_furto': scores['score_furto'],
        'score_incendio': scores['score_incendio'],
        'classificacao_furto': scores['classificacao_furto'],
        'classificacao_incendio': scores['classificacao_incendio'],
        # "De onde vem o score": quantidade e pontos por tipo, sem teto; faixas do medidor.
        'detalhamento': scores['detalhamento'],
        'eventos_considerados': scores['eventos_considerados'],
        'pontos_acumulados': _pontos_acumulados(scores['detalhamento']),
        'faixas': {'medio': FAIXA_MEDIO, 'alto': FAIXA_ALTO},
        'gerado_em': resultado.get('gerado_em') or datetime.now(timezone.utc).isoformat(),
        'complementado_pelo_sistema': [],
    }

    if origem == 'llm':
        analise = resultado.get('analise', {})
        if not isinstance(analise, dict):
            analise = {}
        recs = analise.get('recomendacoes', [])
        recs = [legivel(str(r)) for r in (recs if isinstance(recs, list) else [recs]) if str(r).strip()]
        base.update({
            'resumo': legivel(str(analise.get('resumo', '') or '')),
            'justificativa_furto': legivel(str(analise.get('justificativa_furto', '') or '')),
            'justificativa_incendio': legivel(str(analise.get('justificativa_incendio', '') or '')),
            'recomendacoes': recs,
            'limitacoes': legivel(str(analise.get('limitacoes', '') or '')),
        })
        # A IA as vezes deixa campos vazios: o texto deterministico completa (a tela
        # e o PDF nunca ficam em branco) e a tela avisa o que veio do sistema.
        padrao = montar_fallback(scores)
        for campo in ('resumo', 'justificativa_furto', 'justificativa_incendio', 'recomendacoes'):
            if not base[campo] or (isinstance(base[campo], str) and not base[campo].strip()):
                base[campo] = padrao[campo]
                base['complementado_pelo_sistema'].append(campo)
    elif origem == 'prompt_apenas':
        base.update(montar_fallback(scores))
        base['prompt_gerado'] = prompt
    else:  # fallback
        base.update(montar_fallback(scores, erro=resultado.get('erro')))
        base['prompt_gerado'] = prompt

    base['eventos'] = eventos
    base['limitacoes'] += ' Identificação por crachá não comprova condução contínua nem responsabilidade pelo acidente.'
    return base
