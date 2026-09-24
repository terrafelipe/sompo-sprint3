"""Linha do tempo do Painel da maquina: leituras agregadas em faixas de tempo.

Modulo puro (sem I/O): recebe as leituras de telemetria da janela e devolve uma
faixa por intervalo com quantidade de leituras, se o motor ligou e o pior nivel
de risco visto. A janela termina na ultima leitura da maquina (nao em "agora"),
para mostrar o ultimo dia com atividade mesmo quando o ESP32 parou de enviar.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

# Ordem de gravidade dos niveis de risco que o firmware envia.
ORDEM_RISCO = {'SEGURO': 0, 'BAIXO': 0, 'ATENCAO': 1, 'MEDIO': 1, 'CRITICO': 2, 'ALTO': 2}


def quando(valor: Any) -> datetime | None:
    """ISO 8601 -> datetime com fuso (sem fuso = UTC); invalido -> None."""
    try:
        t = datetime.fromisoformat(str(valor).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def agregar(linhas: List[Dict[str, Any]], fim: datetime, horas: int = 24, minutos: int = 15) -> List[Dict[str, Any]]:
    inicio = fim - timedelta(hours=horas)
    total = horas * 60 // minutos
    faixas = [{'inicio': (inicio + timedelta(minutes=i * minutos)).isoformat(),
               'leituras': 0, 'motor_ligado': False, 'risco': None} for i in range(total)]
    for linha in linhas or []:
        t = quando(linha.get('criado_em'))
        if t is None or t <= inicio or t > fim:
            continue
        # A leitura exatamente no fim da janela cai na ultima faixa.
        faixa = faixas[min(total - 1, int((t - inicio).total_seconds() // (minutos * 60)))]
        faixa['leituras'] += 1
        faixa['motor_ligado'] = faixa['motor_ligado'] or bool(linha.get('motor_ligado'))
        risco = str(linha.get('nivel_risco') or '').upper()
        if risco in ORDEM_RISCO and (faixa['risco'] is None or ORDEM_RISCO[risco] > ORDEM_RISCO[faixa['risco']]):
            faixa['risco'] = risco
    return faixas
