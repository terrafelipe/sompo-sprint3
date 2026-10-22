"""Dados da linha do tempo para os testes do navegador: o dia 22/10 do mockup aprovado.

As linhas "do banco" (faixas, alarmes, sessoes, crachas recusados) passam pela mesma funcao da
rota (app._linha_do_tempo_corpo), entao o formato e sempre o que o backend devolve."""
import json
import math
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from app import _linha_do_tempo_corpo
from linha_do_tempo import minutos_para

BRT = timezone(timedelta(hours=-3))
FIM = datetime(2026, 10, 22, 22, 20, tzinfo=BRT)


def _t(dia, h, m):
    return datetime(2026, 10, dia, h, m, tzinfo=BRT)


# (dia, inicio, fim) em (h, m)
MOTOR = [(22, (7, 1), (11, 40)), (22, (13, 5), (13, 9)), (22, (14, 12), (16, 30)), (21, (7, 20), (12, 0)), (21, (13, 30), (17, 10))]
SEM_ENVIO = [(22, (17, 29), (22, 15))]
PICOS = [(22, (9, 33), 63, 16), (21, (15, 44), 52, 10)]   # (dia, centro, pico em C, largura em min)
SESSOES = [('João Silva', 22, (6, 58), (11, 42)), ('Maria Souza', 22, (14, 10), (16, 31)), ('João Silva', 21, (7, 15), (17, 12))]
ALARMES = [('furto_capo', 22, (2, 14), 2, None, None), ('escape_atencao', 22, (9, 12), 2, 44, 40), ('escape_atencao', 22, (9, 18), 2, 47, 40),
           ('escape_atencao', 22, (9, 25), 2, 53, 40), ('escape_critico', 22, (9, 31), 4, 61, 60), ('escape_critico', 22, (9, 38), 4, 63, 60),
           ('operador_nao_autorizado', 22, (13, 5), 3, None, None), ('furto_movimento', 22, (13, 6), 2, None, None),
           ('escape_atencao', 21, (15, 40), 2, 45, 40), ('escape_atencao', 21, (15, 47), 2, 52, 40)]
NEGADAS = [(22, (13, 4), '4A1F9C02')]


def _dentro(t, trechos):
    return any(_t(d, *a) <= t < _t(d, *b) for d, a, b in trechos)


def _temp(t):
    v = 26.0
    for d, a, b in MOTOR:
        ia, ib = _t(d, *a), _t(d, *b)
        if t < ia:
            continue
        sub = 13 * (1 - math.exp(-(min(t, ib) - ia).total_seconds() / 2100))
        v += sub if t <= ib else sub * math.exp(-(t - ib).total_seconds() / 1500)
    for d, c, pico, larg in PICOS:
        dt = (t - _t(d, *c)).total_seconds() / 60
        v += (pico - 39) * math.exp(-dt * dt / (2 * larg * larg))
    return round(v, 1)


def _faixas(inicio, fim, minutos, vazio=False):
    out, t = [], inicio
    while t < fim:
        mins = [t + timedelta(minutes=k) for k in range(minutos) if not _dentro(t + timedelta(minutes=k), SEM_ENVIO)]
        if vazio:   # maquina ligada a placa, parada e sem nada acontecendo
            mins = [t]
        out.append({'inicio': t.isoformat(), 'leituras': len(mins),
                    'motor_ligado': (not vazio) and any(_dentro(m, MOTOR) for m in mins),
                    'temp_max': (26.0 if vazio else max(_temp(m) for m in mins)) if mins else None, 'risco': None})
        t += timedelta(minutes=minutos)
    return out


def resposta_exemplo(fim=FIM, horas=24, vazio=False, omitidos=None):
    inicio = fim - timedelta(hours=horas)
    minutos = minutos_para(inicio, fim)
    iso = lambda d, hm: _t(d, *hm).isoformat()
    alarmes = [] if vazio else [{'id': i, 'tipo': tipo, 'criado_em': iso(d, hm), 'severidade': sev, 'temp_escape': temp,
                                 'detalhes': {'limiar_c': lim} if lim else None}
                                for i, (tipo, d, hm, sev, temp, lim) in enumerate(ALARMES)]
    sessoes = [] if vazio else [{'sessao_id': str(i), 'inicio_em': iso(d, a), 'fim_em': iso(d, b), 'operador_nome': nome,
                                 'status': 'encerrada'} for i, (nome, d, a, b) in enumerate(SESSOES)]
    negadas = [] if vazio else [{'registro_id': f'n{i}', 'ocorrido_em': iso(d, hm), 'recebido_em': iso(d, hm), 'uid': uid}
                                for i, (d, hm, uid) in enumerate(NEGADAS)]
    corpo = _linha_do_tempo_corpo(_faixas(inicio, fim, minutos, vazio), minutos, alarmes, sessoes, negadas, inicio, fim)
    if omitidos is not None:
        corpo['omitidos'] = omitidos
    return {'janela': {'inicio': inicio.isoformat(), 'fim': fim.isoformat(), 'minutos': minutos, 'tipo': 'horas'}, **corpo}


def vazia(fim=FIM, horas=24):
    return resposta_exemplo(fim, horas, vazio=True)


def servir(page, resposta=None):
    """Responde a rota da linha do tempo. `resposta`: dict, ou funcao(params) -> dict | (status, dict).
    Sem resposta, 24 h ou 7 dias do exemplo conforme ?horas=. Guarda as URLs em st['urls']."""
    st = {'urls': []}

    def rota(r):
        st['urls'].append(r.request.url)
        params = {k: v[0] for k, v in parse_qs(urlparse(r.request.url).query).items()}
        if resposta is None:
            corpo, status = resposta_exemplo(horas=int(params.get('horas', 24))), 200
        else:
            corpo = resposta(params) if callable(resposta) else resposta
            status, corpo = corpo if isinstance(corpo, tuple) else (200, corpo)
        r.fulfill(status=status, content_type='application/json', body=json.dumps(corpo))
    page.route('**/telemetria/linha-do-tempo*', rota)
    return st
