from __future__ import annotations

import functools
import hmac
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_cors import CORS

import documento
import frota
from config import (
    CORS_ORIGINS,
    FLASK_DEBUG,
    FLASK_HOST,
    FLASK_PORT,
    PAINEL_SENHA,
    PAINEL_USUARIO,
    SECRET_KEY,
    SESSAO_HORAS,
    SOMPO_API_KEY,
    SUPABASE_URL,
)
from relatorios import montar_relatorio_bruto, montar_relatorio_risco
from scores import calcular_scores
from supabase_client import (
    buscar_usuario,
    consultar_clientes,
    consultar_eventos,
    consultar_fazendas,
    consultar_resumo,
    consultar_telemetria,
    consultar_usuarios,
    inserir_tabela,
)

app = Flask(__name__)
app.register_blueprint(frota.bp)
# Chave para assinar o cookie de sessao do login.
app.secret_key = SECRET_KEY
_SESSAO_SEGUNDOS = SESSAO_HORAS * 3600
app.permanent_session_lifetime = timedelta(hours=SESSAO_HORAS)
# Cookie de sessao mais seguro (HttpOnly, SameSite). Sem refresh a cada request: o
# prazo conta a partir do login, forcando novo login depois de SESSAO_HORAS.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_REFRESH_EACH_REQUEST=False,
)
# CORS restrito as origens de CORS_ORIGINS (vazio = nenhuma origem cross-origin).
CORS(app, origins=CORS_ORIGINS)

# Rotas liberadas sem API key mesmo com auth ligada (health + painel + login).
_ROTAS_PUBLICAS = {'saude', 'painel', 'static', 'login'}
# Rotas acessiveis sem estar logado (a propria pagina de login e o logout).
_LOGIN_LIVRE = {'login', 'logout'}


@app.before_request
def exigir_login_painel():
    # Login do painel via pagina /login + sessao. Opt-in: so protege quando
    # PAINEL_SENHA esta configurada (producao). Em modo demo (senha vazia) nada
    # e protegido. Cobre TODO o site (inclusive '/' e os estaticos); a pagina de
    # login e self-contained, entao 'static' NAO precisa ficar liberado.
    if not PAINEL_SENHA:
        return None
    if request.method == 'OPTIONS':
        return None
    if request.endpoint in _LOGIN_LIVRE:
        return None
    # Cliente de API (script, aparelho no campo, outro front) entra pela chave, sem
    # sessao de navegador: se o X-API-Key confere, libera aqui e deixa a trava de
    # API key (exigir_api_key) cuidar da validacao por rota.
    if SOMPO_API_KEY and hmac.compare_digest(request.headers.get('X-API-Key', ''), SOMPO_API_KEY):
        return None
    if session.get('logado'):
        # Cookies remain signed after a deletion; revalidate database identities.
        try:
            atual = buscar_usuario(session.get('usuario', ''))
        except Exception as exc:
            return _erro('autenticacao_indisponivel', exc, 502)
        if (atual and atual.get('excluido_em')) or (session.get('usuario_id') and not atual):
            session.clear()
        # Timeout absoluto: expira SESSAO_HORAS apos o login, independente de atividade.
        if time.time() - session.get('login_em', 0) < _SESSAO_SEGUNDOS:
            return None
        session.clear()  # sessao expirou -> exige novo login
    # Nao logado (ou expirado): navegador (HTML) vai para a tela de login; chamada de dados (fetch/JSON)
    # recebe 401 para o JS tratar sem seguir o redirect.
    if 'text/html' in request.headers.get('Accept', ''):
        return redirect(url_for('login', proximo=request.full_path.rstrip('?')))
    return jsonify({'erro': 'nao_autorizado', 'detalhe': 'login necessario'}), 401


def _destino_seguro(proximo: str) -> str:
    # Evita open redirect: so aceita caminho interno (comeca com '/' e nao '//').
    if proximo and proximo.startswith('/') and not proximo.startswith('//'):
        return proximo
    return url_for('painel')


def _autenticar(usuario: str, senha: str) -> Dict[str, Any] | None:
    # Perfis: 1) tabela `usuario` (role + fazenda vinculada); 2) fallback para a
    # credencial do env (PAINEL_USUARIO/SENHA) como perfil 'sompo', para nao quebrar
    # o login ja configurado. Senha em texto plano - demo academica (ver usuarios.sql).
    try:
        u = buscar_usuario(usuario)
    except Exception as exc:
        app.logger.warning('login: busca de usuario indisponivel: %s', exc)
        return None  # Fail closed: an excluded login must not use the env fallback.
    if u and u.get('excluido_em'):
        return None
    if u and hmac.compare_digest(str(u.get('senha', '')), senha):
        faz = u.get('fazenda') or {}
        return {
            'usuario_id': u.get('id_usuario'),
            'usuario': usuario,
            'role': u.get('role', 'sompo'),
            'fazenda_id': u.get('fk_fazenda_id_fazenda'),
            'fazenda_nome': faz.get('nome'),
            'dispositivo_forcado': faz.get('dispositivo_id'),
        }
    if PAINEL_USUARIO and hmac.compare_digest(usuario, PAINEL_USUARIO) and hmac.compare_digest(senha, PAINEL_SENHA):
        return {'usuario': usuario, 'role': 'sompo', 'fazenda_id': None,
                'fazenda_nome': None, 'dispositivo_forcado': None}
    return None


@app.route('/login', methods=['GET', 'POST'])
def login():
    # Login desligado (demo) -> nao ha tela de login; segue para o painel.
    if not PAINEL_SENHA:
        return redirect(url_for('painel'))
    if session.get('logado'):
        return redirect(_destino_seguro(request.args.get('proximo', '')))

    erro = False
    if request.method == 'POST':
        perfil = _autenticar(request.form.get('usuario', ''), request.form.get('senha', ''))
        if perfil:
            session['logado'] = True
            session['login_em'] = time.time()  # inicio da sessao, para o timeout absoluto
            session['usuario'] = perfil['usuario']
            session['usuario_id'] = perfil.get('usuario_id')
            session['role'] = perfil['role']
            session['fazenda_id'] = perfil['fazenda_id']
            session['fazenda_nome'] = perfil['fazenda_nome']
            session['dispositivo_forcado'] = perfil['dispositivo_forcado']
            # "Manter conectado": marcado = cookie persiste (ate SESSAO_HORAS); desmarcado =
            # cai ao fechar o navegador. O timeout de SESSAO_HORAS vale nos dois casos.
            session.permanent = bool(request.form.get('lembrar'))
            return redirect(_destino_seguro(request.form.get('proximo', '')))
        erro = True

    proximo = request.values.get('proximo', '')
    pagina = render_template('login.html', erro=erro, proximo=proximo)
    return pagina, (401 if erro else 200)


@app.get('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


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


# ---------------------------------------------------------------------------
# Perfis de acesso (role-based). Sem sessao (modo demo) o padrao e 'sompo', o que
# preserva o comportamento aberto atual do painel.
# ---------------------------------------------------------------------------
def _perfil() -> Dict[str, Any]:
    return {
        'usuario': session.get('usuario'),
        'role': session.get('role', 'sompo'),
        'fazenda_id': session.get('fazenda_id'),
        'fazenda_nome': session.get('fazenda_nome'),
        'dispositivo_forcado': session.get('dispositivo_forcado'),
    }


def _dispositivo_para(req_dispositivo: str) -> str:
    # A seleção é explícita e autorizada pela fazenda da máquina, não pelo
    # dispositivo antigo armazenado na sessão de login.
    try:
        return frota.resolver_equipamento()
    except frota.FrotaErro:
        raise
    except Exception as exc:
        app.logger.warning('falha ao resolver equipamento: %s', exc)
        raise frota.FrotaErro('frota_indisponivel', 502) from exc


def somente_sompo(view):
    # Cadastro/portfolio: so o perfil 'sompo'. Qualquer outro -> 403.
    @functools.wraps(view)
    def _wrap(*args, **kwargs):
        if _perfil()['role'] != 'sompo':
            return jsonify({'erro': 'proibido', 'detalhe': 'acesso restrito ao perfil Sompo'}), 403
        return view(*args, **kwargs)
    return _wrap


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


@app.get('/me')
def me():
    # Perfil do usuario logado, para o front esconder/mostrar abas e escopar a visao.
    p = _perfil()
    return jsonify({
        'usuario': p['usuario'],
        'role': p['role'],
        'fazenda_id': p['fazenda_id'],
        'fazenda_nome': p['fazenda_nome'],
        'dispositivo': p['dispositivo_forcado'],
    }), 200


@app.get('/telemetria')
def telemetria():
    dispositivo = _dispositivo_para(request.args.get('dispositivo', 'SOMPO-ESP32'))
    limite = _parse_int(request.args.get('limite', '50'), 50, minimum=1, maximum=500)

    try:
        dados = frota.identificar_registros(consultar_telemetria(dispositivo, limite=limite) if dispositivo else [])
        return jsonify({'total': len(dados), 'dados': dados, **frota.contexto()}), 200
    except Exception as exc:
        return _erro('falha_na_consulta', exc, 502)


@app.get('/eventos')
def eventos():
    dispositivo = _dispositivo_para(request.args.get('dispositivo', 'SOMPO-ESP32'))
    dias = _parse_int(request.args.get('dias', '7'), 7, minimum=1)

    try:
        dados = frota.identificar_registros(consultar_eventos(dispositivo, dias=dias) if dispositivo else [])
        return jsonify({'total': len(dados), 'dados': dados, **frota.contexto()}), 200
    except Exception as exc:
        return _erro('falha_na_consulta', exc, 502)


@app.get('/resumo')
def resumo():
    dispositivo = _dispositivo_para(request.args.get('dispositivo', 'SOMPO-ESP32'))
    dias = _parse_int(request.args.get('dias', '7'), 7, minimum=1)

    try:
        dados = consultar_resumo(dispositivo, dias=dias) if dispositivo else []
        return jsonify({'total': len(dados), 'dados': dados, **frota.contexto()}), 200
    except Exception as exc:
        return _erro('falha_na_consulta', exc, 502)


@app.get('/scores')
def scores():
    dispositivo = _dispositivo_para(request.args.get('dispositivo', 'SOMPO-ESP32'))
    dias = _parse_int(request.args.get('dias', '7'), 7, minimum=1)

    try:
        eventos = consultar_eventos(dispositivo, dias=dias) if dispositivo else []
        return jsonify({**calcular_scores(dispositivo, dias, eventos), **frota.contexto()}), 200
    except Exception as exc:
        return _erro('falha_na_consulta', exc, 502)


@app.get('/relatorio/bruto')
def relatorio_bruto():
    dispositivo = _dispositivo_para(request.args.get('dispositivo', 'SOMPO-ESP32'))
    dias = _parse_int(request.args.get('dias', '7'), 7, minimum=1)

    try:
        resumo_por_dia = consultar_resumo(dispositivo, dias=dias) if dispositivo else []
        eventos = frota.identificar_registros(consultar_eventos(dispositivo, dias=dias) if dispositivo else [])
        relatorio = montar_relatorio_bruto(dispositivo, dias, resumo_por_dia, eventos)
        relatorio.update(frota.contexto())
        return jsonify(relatorio), 200
    except Exception as exc:
        return _erro('falha_na_geracao_do_relatorio', exc, 502)


@app.get('/relatorio/risco')
def relatorio_risco():
    dispositivo = _dispositivo_para(request.args.get('dispositivo', 'SOMPO-ESP32'))
    dias = _parse_int(request.args.get('dias', '7'), 7, minimum=1)

    try:
        resumo_por_dia = consultar_resumo(dispositivo, dias=dias) if dispositivo else []
        eventos = frota.identificar_registros(consultar_eventos(dispositivo, dias=dias) if dispositivo else [])
        resultado = montar_relatorio_risco(dispositivo, dias, resumo_por_dia, eventos, contexto=frota.contexto())
        return jsonify(resultado), 200
    except Exception as exc:
        return _erro('falha_na_geracao_do_relatorio', exc, 502)


@app.get('/relatorio/risco.docx')
def relatorio_risco_docx():
    # Mesmo conteúdo do /relatorio/risco, mas como documento Word (.docx) para download.
    dispositivo = _dispositivo_para(request.args.get('dispositivo', 'SOMPO-ESP32'))
    dias = _parse_int(request.args.get('dias', '7'), 7, minimum=1)

    try:
        resumo_por_dia = consultar_resumo(dispositivo, dias=dias) if dispositivo else []
        eventos = frota.identificar_registros(consultar_eventos(dispositivo, dias=dias) if dispositivo else [])
        relatorio = montar_relatorio_risco(dispositivo, dias, resumo_por_dia, eventos, contexto=frota.contexto())
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


# ---------------------------------------------------------------------------
# Cadastro de fazendas (tela do dashboard). Protegido pelo login do painel.
# ---------------------------------------------------------------------------
@app.get('/clientes')
@somente_sompo
def clientes():
    try:
        dados = consultar_clientes()
        return jsonify({'total': len(dados), 'dados': dados}), 200
    except Exception as exc:
        return _erro('falha_na_consulta', exc, 502)


@app.post('/clientes')
@somente_sompo
def clientes_criar():
    corpo = request.get_json(silent=True) or {}
    payload: Dict[str, Any] = {}
    # Obrigatorios (para poder entrar em contato); o e-mail fica opcional.
    for campo in ('nome', 'cnpj', 'telefone', 'endereco'):
        valor = str(corpo.get(campo, '')).strip()
        if not valor:
            return jsonify({'erro': f'{campo}_obrigatorio'}), 400
        payload[campo] = valor
    email = str(corpo.get('email', '')).strip()
    if email:
        payload['email'] = email

    try:
        criado = inserir_tabela('cliente', payload)
        return jsonify({'ok': True, 'cliente': criado}), 201
    except Exception as exc:
        return _erro('falha_ao_criar_cliente', exc, 502)


@app.get('/fazendas')
@somente_sompo
def fazendas_listar():
    try:
        dados = consultar_fazendas()
        return jsonify({'total': len(dados), 'dados': dados}), 200
    except Exception as exc:
        return _erro('falha_na_consulta', exc, 502)


@app.post('/fazendas')
@somente_sompo
def fazendas_criar():
    corpo = request.get_json(silent=True) or {}
    nome = str(corpo.get('nome', '')).strip()
    if not nome:
        return jsonify({'erro': 'nome_obrigatorio'}), 400

    localizacao = str(corpo.get('localizacao', '')).strip()
    if not localizacao:
        return jsonify({'erro': 'localizacao_obrigatoria'}), 400

    area = corpo.get('area_ha')
    if area in (None, ''):
        return jsonify({'erro': 'area_obrigatoria'}), 400
    try:
        area = float(area)
    except (TypeError, ValueError):
        return jsonify({'erro': 'area_invalida'}), 400

    cliente_id = corpo.get('fk_cliente_id_cliente')
    if cliente_id in (None, ''):
        return jsonify({'erro': 'cliente_obrigatorio'}), 400
    try:
        cliente_id = int(cliente_id)
    except (TypeError, ValueError):
        return jsonify({'erro': 'cliente_invalido'}), 400

    payload: Dict[str, Any] = {
        'nome': nome, 'localizacao': localizacao,
        'area_ha': area, 'fk_cliente_id_cliente': cliente_id,
    }
    # Dispositivo (ESP32) que monitora esta fazenda. Opcional: uma fazenda pode ser
    # cadastrada antes de ter um aparelho vinculado. So aparece com dado ao vivo a
    # fazenda cujo dispositivo_id bate com o que o ESP32 envia (hoje "SOMPO-ESP32").
    dispositivo_id = str(corpo.get('dispositivo_id', '')).strip()
    if dispositivo_id:
        payload['dispositivo_id'] = dispositivo_id

    try:
        criado = inserir_tabela('fazenda', payload)
        return jsonify({'ok': True, 'fazenda': criado}), 201
    except Exception as exc:
        return _erro('falha_ao_criar_fazenda', exc, 502)


# ---------------------------------------------------------------------------
# Cadastro de usuarios/logins do painel (aba "Usuarios"). So o perfil Sompo.
# Senha em texto plano - demo academica, mesmo padrao de usuarios.sql.
# ---------------------------------------------------------------------------
_ROLES_VALIDAS = {'sompo', 'gestor_fazenda'}


@app.get('/usuarios')
@somente_sompo
def usuarios_listar():
    try:
        dados = consultar_usuarios()
        return jsonify({'total': len(dados), 'dados': dados}), 200
    except Exception as exc:
        return _erro('falha_na_consulta', exc, 502)


@app.post('/usuarios')
@somente_sompo
def usuarios_criar():
    corpo = request.get_json(silent=True) or {}
    usuario = str(corpo.get('usuario', '')).strip()
    if not usuario:
        return jsonify({'erro': 'usuario_obrigatorio'}), 400
    senha = str(corpo.get('senha', '')).strip()
    if not senha:
        return jsonify({'erro': 'senha_obrigatoria'}), 400
    role = str(corpo.get('role', '')).strip()
    if role not in _ROLES_VALIDAS:
        return jsonify({'erro': 'role_invalida'}), 400

    payload: Dict[str, Any] = {'usuario': usuario, 'senha': senha, 'role': role}
    # gestor_fazenda tem de estar vinculado a uma fazenda (e o que escopa a visao dele).
    if role == 'gestor_fazenda':
        fazenda_id = corpo.get('fk_fazenda_id_fazenda')
        if fazenda_id in (None, ''):
            return jsonify({'erro': 'fazenda_obrigatoria'}), 400
        try:
            payload['fk_fazenda_id_fazenda'] = int(fazenda_id)
        except (TypeError, ValueError):
            return jsonify({'erro': 'fazenda_invalida'}), 400

    try:
        criado = inserir_tabela('usuario', payload)
        if isinstance(criado, dict):
            criado.pop('senha', None)   # nunca ecoa a senha de volta
        return jsonify({'ok': True, 'usuario': criado}), 201
    except Exception as exc:
        # Usuario ja existe (unique violation 23505 do Postgres) -> mensagem amigavel.
        texto = str(exc).lower()
        if '23505' in texto or 'duplicate' in texto:
            return jsonify({'erro': 'usuario_ja_existe'}), 409
        return _erro('falha_ao_criar_usuario', exc, 502)


@app.get('/usuarios/<int:value>')
@somente_sompo
def usuario_detalhe(value):
    try:
        from supabase_client import consultar_usuario
        usuario = consultar_usuario(value)
        if not usuario:
            return jsonify(erro='nao_encontrado'), 404
        return jsonify(usuario=usuario)
    except Exception as exc:
        return _erro('falha_na_consulta', exc, 502)


@app.delete('/clientes/<int:value>', defaults={'tipo': 'clientes'})
@app.delete('/fazendas/<int:value>', defaults={'tipo': 'fazendas'})
@app.delete('/usuarios/<int:value>', defaults={'tipo': 'usuarios'})
@app.delete('/operadores/<int:value>', defaults={'tipo': 'operadores'})
@app.delete('/equipamentos/<int:value>', defaults={'tipo': 'equipamentos'})
def cadastro_excluir(tipo, value):
    # Scope is checked even for repeated deletions. Only the trusted server may
    # invoke the transactional RPC; caller identity never comes from JSON.
    papel = frota.papel()
    if tipo not in {'operadores', 'equipamentos'} and papel != 'sompo':
        return jsonify(erro='proibido'), 403
    try:
        if tipo == 'operadores':
            frota.operador(value, historico=True)
        elif tipo == 'equipamentos':
            frota.equipamento(value, historico=True)
        from supabase_client import chamar_rpc
        resultado = chamar_rpc('excluir_cadastro', {
            'p_tipo': tipo, 'p_id': value, 'p_usuario': session.get('usuario')})
        codigo = resultado.get('erro')
        status = 404 if codigo == 'nao_encontrado' else (409 if codigo else 200)
        return jsonify(resultado), status
    except frota.FrotaErro:
        raise
    except Exception as exc:
        return _erro('falha_ao_excluir', exc, 502)


if __name__ == '__main__':
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
