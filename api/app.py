from __future__ import annotations

import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from flask import Flask, Response, jsonify, request
from flask_cors import CORS

import documento
from config import (
    CORS_ORIGINS,
    FLASK_DEBUG,
    FLASK_HOST,
    FLASK_PORT,
    PAINEL_SENHA,
    PAINEL_USUARIO,
    SOMPO_API_KEY,
    SUPABASE_URL,
)
from relatorios import montar_relatorio_bruto, montar_relatorio_risco
from scores import calcular_scores
from supabase_client import consultar_eventos, consultar_telemetria, consultar_resumo

app = Flask(__name__)
# CORS restrito as origens de CORS_ORIGINS (vazio = nenhuma origem cross-origin).
CORS(app, origins=CORS_ORIGINS)

# Rotas liberadas sem API key mesmo com auth ligada (health check + o painel HTML).
_ROTAS_PUBLICAS = {'saude', 'painel', 'static'}


@app.before_request
def exigir_login_painel():
    # Login do painel publico (Basic Auth). Opt-in: so protege quando PAINEL_SENHA
    # esta configurada (producao). Em modo demo (senha vazia) nada e protegido.
    # Cobre TODO o site, inclusive '/' e os arquivos estaticos, para que a pagina
    # do painel nao fique exposta. O navegador guarda a credencial e as chamadas
    # fetch do painel a reenviam automaticamente.
    if not PAINEL_SENHA:
        return None
    if request.method == 'OPTIONS':
        return None
    auth = request.authorization
    if (
        auth is not None
        and auth.username is not None
        and auth.password is not None
        and hmac.compare_digest(auth.username, PAINEL_USUARIO)
        and hmac.compare_digest(auth.password, PAINEL_SENHA)
    ):
        return None
    return Response(
        'Login necessario',
        401,
        {'WWW-Authenticate': 'Basic realm="Painel SOMPO"'},
    )


@app.before_request
def exigir_api_key():
    # Auth opt-in: so protege quando SOMPO_API_KEY esta configurada (producao).
    # Em modo demo (chave vazia) nenhuma rota e protegida.
    if not SOMPO_API_KEY:
        return None
    if request.method == 'OPTIONS' or request.endpoint in _ROTAS_PUBLICAS:
        return None
    enviado = request.headers.get('X-API-Key', '')
    if not hmac.compare_digest(enviado, SOMPO_API_KEY):
        return jsonify({'erro': 'nao_autorizado', 'detalhe': 'X-API-Key ausente ou invalida'}), 401
    return None


def _parse_int(value: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        numero = int(value)
    except (TypeError, ValueError):
        return default
    if minimum is not None and numero < minimum:
        return default
    if maximum is not None and numero > maximum:
        return default
    return numero


def _erro(message: str, exc, status: int):
    # O detalhe do erro fica SO no log do servidor - nao vaza para o cliente
    # (evita expor schema/mensagens internas do Supabase). Ver docs/SEGURANCA.md.
    app.logger.warning('%s: %s', message, exc)
    return jsonify({'erro': message}), status


@app.get('/')
def painel():
    # Dashboard HTML (static/index.html) para o gestor. Os dados vem dos endpoints JSON.
    return app.send_static_file('index.html')


@app.get('/saude')
def saude():
    try:
        from supabase_client import consultar_tabela

        consultar_tabela('telemetria', limite=1)
        return jsonify({'api': 'ok', 'banco': 'ok'}), 200
    except Exception as exc:
        # Motivo da falha so no log do servidor, nao na resposta.
        app.logger.warning('saude: banco indisponivel: %s', exc)
        return jsonify({'api': 'ok', 'banco': 'falha'}), 502


@app.get('/telemetria')
def telemetria():
    dispositivo = request.args.get('dispositivo', 'SOMPO-ESP32')
    limite = _parse_int(request.args.get('limite', '50'), 50, minimum=1, maximum=500)

    try:
        dados = consultar_telemetria(dispositivo, limite=limite)
        return jsonify({'total': len(dados), 'dados': dados}), 200
    except Exception as exc:
        return _erro('falha_na_consulta', exc, 502)


@app.get('/eventos')
def eventos():
    dispositivo = request.args.get('dispositivo', 'SOMPO-ESP32')
    dias = _parse_int(request.args.get('dias', '7'), 7, minimum=1)

    try:
        dados = consultar_eventos(dispositivo, dias=dias)
        return jsonify({'total': len(dados), 'dados': dados}), 200
    except Exception as exc:
        return _erro('falha_na_consulta', exc, 502)


@app.get('/resumo')
def resumo():
    dispositivo = request.args.get('dispositivo', 'SOMPO-ESP32')
    dias = _parse_int(request.args.get('dias', '7'), 7, minimum=1)

    try:
        dados = consultar_resumo(dispositivo, dias=dias)
        return jsonify({'total': len(dados), 'dados': dados}), 200
    except Exception as exc:
        return _erro('falha_na_consulta', exc, 502)


@app.get('/scores')
def scores():
    dispositivo = request.args.get('dispositivo', 'SOMPO-ESP32')
    dias = _parse_int(request.args.get('dias', '7'), 7, minimum=1)

    try:
        eventos = consultar_eventos(dispositivo, dias=dias)
        return jsonify(calcular_scores(dispositivo, dias, eventos)), 200
    except Exception as exc:
        return _erro('falha_na_consulta', exc, 502)


@app.get('/relatorio/bruto')
def relatorio_bruto():
    dispositivo = request.args.get('dispositivo', 'SOMPO-ESP32')
    dias = _parse_int(request.args.get('dias', '7'), 7, minimum=1)

    try:
        resumo_por_dia = consultar_resumo(dispositivo, dias=dias)
        eventos = consultar_eventos(dispositivo, dias=dias)
        relatorio = montar_relatorio_bruto(dispositivo, dias, resumo_por_dia, eventos)
        return jsonify(relatorio), 200
    except Exception as exc:
        return _erro('falha_na_geracao_do_relatorio', exc, 502)


@app.get('/relatorio/risco')
def relatorio_risco():
    dispositivo = request.args.get('dispositivo', 'SOMPO-ESP32')
    dias = _parse_int(request.args.get('dias', '7'), 7, minimum=1)

    try:
        resumo_por_dia = consultar_resumo(dispositivo, dias=dias)
        eventos = consultar_eventos(dispositivo, dias=dias)
        resultado = montar_relatorio_risco(dispositivo, dias, resumo_por_dia, eventos)
        return jsonify(resultado), 200
    except Exception as exc:
        return _erro('falha_na_geracao_do_relatorio', exc, 502)


@app.get('/relatorio/risco.docx')
def relatorio_risco_docx():
    # Mesmo conteúdo do /relatorio/risco, mas como documento Word (.docx) para download.
    dispositivo = request.args.get('dispositivo', 'SOMPO-ESP32')
    dias = _parse_int(request.args.get('dias', '7'), 7, minimum=1)

    try:
        resumo_por_dia = consultar_resumo(dispositivo, dias=dias)
        eventos = consultar_eventos(dispositivo, dias=dias)
        relatorio = montar_relatorio_risco(dispositivo, dias, resumo_por_dia, eventos)
        conteudo = documento.montar_docx(relatorio, eventos)

        carimbo = datetime.now(documento.FUSO_BRASILIA).strftime('%Y%m%d_%H%M')
        nome = f'relatorio_risco_{dispositivo}_{carimbo}.docx'
        return Response(
            conteudo,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            headers={'Content-Disposition': f'attachment; filename="{nome}"'},
        )
    except Exception as exc:
        return _erro('falha_na_geracao_do_documento', exc, 502)


if __name__ == '__main__':
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
