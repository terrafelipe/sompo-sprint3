"""Linha do tempo do Painel da maquina: leituras agregadas em faixas de tempo e os eventos do periodo.

Modulo puro (sem I/O). As faixas vem da funcao SQL linha_do_tempo_faixas (ou do `agregar`
abaixo, plano B enquanto o SQL nao foi rodado): quantidade de leituras, se o motor ligou, a
temperatura maxima do escape e o pior nivel de risco de cada intervalo. Daqui saem tambem os
eventos de rotina calculados das leituras (motor, placa sem enviar, temperatura normal), a
severidade e o eixo dos alarmes, os limites do grafico e o resumo.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

# Ordem de gravidade dos niveis de risco que o firmware envia.
ORDEM_RISCO = {'SEGURO': 0, 'BAIXO': 0, 'ATENCAO': 1, 'MEDIO': 1, 'CRITICO': 2, 'ALTO': 2}
# Tamanhos de faixa possiveis; escolhe o menor que der no maximo MAX_FAIXAS.
PASSOS_MIN = (5, 10, 15, 30, 60, 120, 180, 360, 720, 1440)
MAX_FAIXAS = 400
# Sem numero de severidade, estes sao criticos; o resto e atencao.
CRITICOS = {'chama_detectada', 'escape_critico', 'operador_nao_autorizado', 'sensor_falha'}
INCENDIO = {'chama_detectada', 'escape_atencao', 'escape_critico'}
LIMITES_PADRAO = {'atencao': 450, 'critico': 550}   # TEMP_ESCAPE_ATENCAO/CRITICO do firmware fora da demo
LACUNA_MIN = 15   # placa sem enviar: pelo menos 15 min e 2 faixas seguidas sem leitura


def quando(valor: Any) -> datetime | None:
    """ISO 8601 -> datetime com fuso (sem fuso = UTC); invalido -> None."""
    try:
        t = datetime.fromisoformat(str(valor).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def minutos_para(inicio: datetime, fim: datetime) -> int:
    total = (fim - inicio).total_seconds() / 60
    return next((m for m in PASSOS_MIN if total / m <= MAX_FAIXAS), PASSOS_MIN[-1])


def agregar(linhas: List[Dict[str, Any]], fim: datetime, horas: int = 24, minutos: int = 15,
            inicio: datetime | None = None) -> List[Dict[str, Any]]:
    inicio = inicio or fim - timedelta(hours=horas)
    total = math.ceil((fim - inicio).total_seconds() / (minutos * 60))
    faixas = [{'inicio': (inicio + timedelta(minutes=i * minutos)).isoformat(),
               'leituras': 0, 'motor_ligado': False, 'temp_max': None, 'risco': None} for i in range(total)]
    for linha in linhas or []:
        t = quando(linha.get('criado_em'))
        if t is None or t <= inicio or t > fim:
            continue
        # A leitura exatamente no fim da janela cai na ultima faixa.
        faixa = faixas[min(total - 1, int((t - inicio).total_seconds() // (minutos * 60)))]
        faixa['leituras'] += 1
        faixa['motor_ligado'] = faixa['motor_ligado'] or bool(linha.get('motor_ligado'))
        temp = linha.get('temp_escape')
        if temp is not None and (faixa['temp_max'] is None or temp > faixa['temp_max']):
            faixa['temp_max'] = temp
        risco = str(linha.get('nivel_risco') or '').upper()
        if risco in ORDEM_RISCO and (faixa['risco'] is None or ORDEM_RISCO[risco] > ORDEM_RISCO[faixa['risco']]):
            faixa['risco'] = risco
    return faixas


def eixo(tipo: str) -> str:
    return 'incendio' if tipo in INCENDIO else 'furto'


def severidade(evento: Dict[str, Any]) -> str:
    n = evento.get('severidade')
    if isinstance(n, (int, float)):
        return 'critico' if n >= 3 else 'atencao'
    return 'critico' if evento.get('tipo') in CRITICOS else 'atencao'


def normalizar_alarme(ev: Dict[str, Any]) -> Dict[str, Any]:
    """Linha da tabela eventos -> evento da linha do tempo."""
    detalhes = ev.get('detalhes') if isinstance(ev.get('detalhes'), dict) else {}
    return {'id': f"a{ev.get('id')}", 'tipo': ev.get('tipo'), 'eixo': eixo(ev.get('tipo')), 'sev': severidade(ev),
            'em': ev.get('criado_em'), 'temp': ev.get('temp_escape'), 'limiar_c': detalhes.get('limiar_c')}


def limites(alarmes: List[Dict[str, Any]]) -> Dict[str, float]:
    """Cada alarme de escape traz so o limite que cruzou: o ultimo de cada tipo vale."""
    out = dict(LIMITES_PADRAO)
    for a in sorted(alarmes, key=lambda a: quando(a.get('em')) or datetime.min.replace(tzinfo=timezone.utc)):
        if a.get('limiar_c') is None:
            continue
        if a['tipo'] == 'escape_atencao':
            out['atencao'] = a['limiar_c']
        elif a['tipo'] == 'escape_critico':
            out['critico'] = a['limiar_c']
    return out


def _lacunas(faixas: List[Dict[str, Any]], minutos: int) -> List[Tuple[int, int]]:
    """(primeira, depois da ultima) de cada trecho de faixas vazias entre leituras, grande o bastante."""
    cheias = [i for i, f in enumerate(faixas) if f['leituras']]
    out = []
    for a, b in zip(cheias, cheias[1:]):
        n = b - a - 1
        if n >= 2 and n * minutos >= LACUNA_MIN:
            out.append((a + 1, b))
    return out


def _trechos_motor(faixas: List[Dict[str, Any]]) -> List[Tuple[int, int]]:
    """(primeira, ultima) faixa de cada trecho de motor ligado; faixas sem leitura nao quebram o trecho."""
    out, aberto = [], None
    for i, f in enumerate(faixas):
        if not f['leituras']:
            continue
        if f['motor_ligado'] and aberto is None:
            aberto = [i, i]
        elif f['motor_ligado']:
            aberto[1] = i
        elif aberto is not None:
            out.append(tuple(aberto))
            aberto = None
    if aberto is not None:
        out.append(tuple(aberto))
    return out


def _cobre(sessao: Dict[str, Any], t: datetime) -> bool:
    a, b = quando(sessao.get('inicio')), quando(sessao.get('fim'))
    return a is not None and a <= t and (b is None or t <= b)


def eventos_rotina(faixas: List[Dict[str, Any]], minutos: int, sessoes: Optional[List[Dict[str, Any]]],
                   alarmes: List[Dict[str, Any]], lim: Dict[str, float]) -> List[Dict[str, Any]]:
    if not faixas:
        return []
    passo = timedelta(minutes=minutos)
    inicio = lambda i: quando(faixas[i]['inicio'])
    cheias = [i for i, f in enumerate(faixas) if f['leituras']]
    primeira, ultima_cheia = (cheias[0], cheias[-1]) if cheias else (None, None)
    out = []
    for a, b in _trechos_motor(faixas):
        if a != primeira:   # ligado desde o inicio da janela: a partida foi antes
            t = inicio(a)
            out.append({'tipo': 'motor_ligou', 'em': t.isoformat(),
                        'com_cracha': None if sessoes is None else any(_cobre(s, t) for s in sessoes)})
        if b != ultima_cheia:   # ainda ligado na ultima leitura: nao parou
            out.append({'tipo': 'motor_parou', 'em': (inicio(b) + passo).isoformat(),
                        'duracao_min': (b - a + 1) * minutos})
    for a, b in _lacunas(faixas, minutos):
        out.append({'tipo': 'envio_parou', 'em': inicio(a).isoformat(), 'duracao_min': (b - a) * minutos})
        out.append({'tipo': 'envio_voltou', 'em': inicio(b).isoformat()})
    coberto_ate = None
    for al in sorted((x for x in alarmes if x.get('tipo') in INCENDIO), key=lambda x: quando(x['em'])):
        t = quando(al['em'])
        if t is None or (coberto_ate is not None and t <= coberto_ate):
            continue
        for i, f in enumerate(faixas):
            if inicio(i) + passo <= t or not f['leituras'] or f['temp_max'] is None:
                continue
            if f['temp_max'] < lim['atencao']:
                coberto_ate = inicio(i)
                out.append({'tipo': 'temp_normal', 'em': coberto_ate.isoformat(), 'temp': f['temp_max']})
                break
        else:
            break   # nao voltou ate o fim da janela: os alarmes seguintes tambem nao
    for e in out:
        e.update(eixo='rotina', sev='rotina')
    return sorted(out, key=lambda e: quando(e['em']))


def cortar(eventos: List[Dict[str, Any]], maximo: int = 1000) -> Tuple[List[Dict[str, Any]], int]:
    """Todos os alarmes ficam; a rotina mais antiga sai primeiro. Devolve (eventos, quantos sairam)."""
    chave = lambda e: quando(e['em'])
    alarmes = [e for e in eventos if e['eixo'] != 'rotina']
    rotina = sorted((e for e in eventos if e['eixo'] == 'rotina'), key=chave, reverse=True)
    fica = rotina[:max(0, maximo - len(alarmes))]
    return sorted(alarmes + fica, key=chave), len(rotina) - len(fica)


def resumo(alarmes: List[Dict[str, Any]], faixas: List[Dict[str, Any]], minutos: int) -> Dict[str, int]:
    return {'incendio': sum(a['eixo'] == 'incendio' for a in alarmes),
            'furto': sum(a['eixo'] == 'furto' for a in alarmes),
            'motor_min': sum(1 for f in faixas if f['leituras'] and f['motor_ligado']) * minutos,
            'sem_envio_min': sum(b - a for a, b in _lacunas(faixas, minutos)) * minutos}
