from __future__ import annotations

import functools
import hmac
import math
import os
import re
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
from werkzeug.security import check_password_hash, generate_password_hash

import ocorrencias
import frota
import linha_do_tempo
from config import (
    COOKIE_SEGURO,
    CORS_ORIGINS,
    FLASK_DEBUG,
    FLASK_HOST,
    FLASK_PORT,
    PAINEL_SENHA,
    SECRET_KEY,
    SESSAO_HORAS,
    SOMPO_API_KEY,
    SUPABASE_URL,
)
from relatorios import montar_relatorio_bruto, montar_relatorio_risco
from scores import calcular_scores
from supabase_client import (
    SupabaseError,
    atualizar_tabela,
    buscar_usuario,
    consultar_clientes,
    consultar_eventos,
    consultar_fazendas,
    consultar_gestores,
    consultar_resumo,
    consultar_telemetria,
    consultar_telemetria_intervalo,
    consultar_usuarios,
    inserir_tabela,
)

app = Flask(__name__)
app.register_blueprint(frota.bp)
app.register_blueprint(ocorrencias.bp)
# Chave para assinar o cookie de sessao do login.
app.secret_key = SECRET_KEY
_SESSAO_SEGUNDOS = SESSAO_HORAS * 3600
app.permanent_session_lifetime = timedelta(hours=SESSAO_HORAS)
# Cookie de sessao mais seguro (HttpOnly, SameSite; Secure via COOKIE_SEGURO). Sem refresh a cada request: o
# prazo conta a partir do login, forcando novo login depois de SESSAO_HORAS.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=COOKIE_SEGURO,
    SESSION_REFRESH_EACH_REQUEST=False,
)
# CORS restrito as origens de CORS_ORIGINS (vazio = nenhuma origem cross-origin).
CORS(app, origins=CORS_ORIGINS)

# Rotas liberadas sem API key mesmo com auth ligada (health + painel + login).
_ROTAS_PUBLICAS = {'saude', 'painel', 'static', 'login', 'aquecer'}
# Rotas acessiveis sem estar logado (a propria pagina de login e o logout).
_LOGIN_LIVRE = {'login', 'logout', 'aquecer'}
# Revalidacao da sessao: a consulta ao usuario (EUA -> Supabase em SP) ia em TODA requisicao.
# Guardada por 20 s por usuario; qualquer exclusao de cadastro limpa na hora.
_REVALIDACAO_SEGUNDOS = 20
_revalidados: Dict[str, tuple] = {}


def _usuario_atual(nome):
    agora = time.time()
    guardado = _revalidados.get(nome)
    if guardado and guardado[0] > agora:
        return guardado[1]
    atual = buscar_usuario(nome)
    _revalidados[nome] = (agora + _REVALIDACAO_SEGUNDOS, atual)
    return atual


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
            atual = _usuario_atual(session.get('usuario', ''))
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


# Senhas do painel: o banco guarda hash (werkzeug). Senha legada em texto puro ainda entra,
# uma vez, e e regravada como hash no mesmo login. '!' marca conta sem senha definida
# (seeds do usuarios.sql; definir com tools/definir_senha.py).
_PREFIXOS_HASH = ('scrypt:', 'pbkdf2:')
SENHA_BLOQUEADA = '!'


def _senha_confere(guardada: str, digitada: str) -> Tuple[bool, bool]:
    """Devolve (confere, regravar_como_hash)."""
    if not guardada or guardada == SENHA_BLOQUEADA or not digitada:
        return False, False
    if guardada.startswith(_PREFIXOS_HASH):
        return check_password_hash(guardada, digitada), False
    confere = hmac.compare_digest(guardada.encode('utf-8'), digitada.encode('utf-8'))
    return confere, confere


def _autenticar(usuario: str, senha: str) -> Dict[str, Any] | None:
    # Perfis vem so da tabela `usuario` (role + fazenda vinculada), com senha em hash
    # (ver _senha_confere). PAINEL_SENHA apenas liga o login: nao e senha de ninguem
    # (o antigo login reserva do env era uma 2a senha de admin e foi removido).
    try:
        u = buscar_usuario(usuario)
    except Exception as exc:
        app.logger.warning('login: busca de usuario indisponivel: %s', exc)
        return None  # Fail closed: an excluded login must not use the env fallback.
    if u and u.get('excluido_em'):
        return None
    confere, regravar = _senha_confere(str((u or {}).get('senha') or ''), senha)
    if u and confere:
        if regravar:
            try:
                atualizar_tabela('usuario', {'id_usuario': f"eq.{u.get('id_usuario')}"},
                                 {'senha': generate_password_hash(senha)})
            except Exception as exc:   # o login segue; a migracao pega depois
                app.logger.warning('login: nao regravou a senha como hash: %s', exc)
        faz = u.get('fazenda') or {}
        return {
            'usuario_id': u.get('id_usuario'),
            'usuario': usuario,
            'role': u.get('role', 'sompo'),
            'fazenda_id': u.get('fk_fazenda_id_fazenda'),
            'fazenda_nome': faz.get('nome'),
            'dispositivo_forcado': faz.get('dispositivo_id'),
        }
    return None


# Limite de tentativas: 5 falhas em 15 min travam o usuario naquela conexao (vale ate para a
# senha certa, senao a forca bruta so continuaria). A chave usa o IP da conexao, nunca um
# cabecalho (X-Forwarded-For e falsificavel); atras da Cloudflare isso vira um limite por
# usuario. Fica em memoria: vale por instancia da Lambda.
_TENTATIVAS_MAX = 5
_JANELA_LOGIN_SEGUNDOS = 15 * 60
_falhas_login: Dict[Tuple[str, str], List[float]] = {}


def _chave_login(usuario: str) -> Tuple[str, str]:
    return usuario.strip().lower(), request.remote_addr or ''


def _espera_login(chave: Tuple[str, str], agora: float) -> int:
    recentes = [t for t in _falhas_login.get(chave, []) if agora - t < _JANELA_LOGIN_SEGUNDOS]
    if recentes:
        _falhas_login[chave] = recentes
    else:
        _falhas_login.pop(chave, None)
    if len(recentes) < _TENTATIVAS_MAX:
        return 0
    return int(recentes[0] + _JANELA_LOGIN_SEGUNDOS - agora) + 1


@app.route('/login', methods=['GET', 'POST'])
def login():
    # Login desligado (demo) -> nao ha tela de login; segue para o painel.
    if not PAINEL_SENHA:
        return redirect(url_for('painel'))
    if session.get('logado'):
        return redirect(_destino_seguro(request.args.get('proximo', '')))

    erro = False
    if request.method == 'POST':
        chave, agora = _chave_login(request.form.get('usuario', '')), time.time()
        espera = _espera_login(chave, agora)
        if espera:
            pagina = render_template('login.html', erro=False, bloqueado_minutos=math.ceil(espera / 60),
                                     proximo=request.values.get('proximo', ''))
            return pagina, 429, {'Retry-After': str(espera)}
        perfil = _autenticar(request.form.get('usuario', ''), request.form.get('senha', ''))
        if perfil:
            _falhas_login.pop(chave, None)
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
        _falhas_login.setdefault(chave, []).append(agora)

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


@app.post('/events')
def aquecer():
    # Ping do EventBridge a cada 5 min (o Lambda Web Adapter entrega eventos nao-HTTP aqui):
    # mantem instancias quentes. Nao toca no banco; a espera curta faz os alvos simultaneos
    # ocuparem instancias diferentes.
    time.sleep(0.3)
    return '', 204


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
    eq = frota.id_selecionado()
    limite = _parse_int(request.args.get('limite', '50'), 50, minimum=1, maximum=500)

    try:
        dados = frota.identificar_registros(consultar_telemetria(dispositivo, limite=limite, equipamento=eq) if dispositivo or eq else [])
        return jsonify({'total': len(dados), 'dados': dados, **frota.contexto()}), 200
    except Exception as exc:
        return _erro('falha_na_consulta', exc, 502)


@app.get('/telemetria/linha-do-tempo')
def telemetria_linha_do_tempo():
    # Janela de N horas ate a ULTIMA leitura da maquina (mostra o ultimo dia com
    # atividade mesmo se o ESP32 parou), agregada em faixas de 15 min.
    dispositivo = _dispositivo_para(request.args.get('dispositivo', 'SOMPO-ESP32'))
    eq = frota.id_selecionado()
    horas = _parse_int(request.args.get('horas', '24'), 24, minimum=1, maximum=72)
    try:
        ultima = consultar_telemetria(dispositivo, limite=1, equipamento=eq) if dispositivo or eq else []
        fim = linha_do_tempo.quando(ultima[0].get('criado_em')) if ultima else None
        if fim is None:
            return jsonify({'faixas': [], 'janela': None, **frota.contexto()}), 200
        inicio = fim - timedelta(hours=horas)
        linhas = consultar_telemetria_intervalo(dispositivo, inicio, fim, equipamento=eq)
        return jsonify({'janela': {'inicio': inicio.isoformat(), 'fim': fim.isoformat(), 'minutos': 15},
                        'faixas': linha_do_tempo.agregar(linhas, fim, horas, 15), **frota.contexto()}), 200
    except Exception as exc:
        return _erro('falha_na_consulta', exc, 502)


@app.get('/eventos')
def eventos():
    dispositivo = _dispositivo_para(request.args.get('dispositivo', 'SOMPO-ESP32'))
    eq = frota.id_selecionado()
    dias = frota.periodo()   # 1..365, senao 400 dias_invalido (como no /operacoes)

    try:
        dados = frota.identificar_registros(consultar_eventos(dispositivo, dias=dias, equipamento=eq) if dispositivo or eq else [])
        return jsonify({'total': len(dados), 'dados': dados, **frota.contexto()}), 200
    except Exception as exc:
        return _erro('falha_na_consulta', exc, 502)


@app.get('/resumo')
def resumo():
    dispositivo = _dispositivo_para(request.args.get('dispositivo', 'SOMPO-ESP32'))
    eq = frota.id_selecionado()
    dias = frota.periodo()   # 1..365, senao 400 dias_invalido (como no /operacoes)

    try:
        dados = consultar_resumo(dispositivo, dias=dias, equipamento=eq) if dispositivo or eq else []
        return jsonify({'total': len(dados), 'dados': dados, **frota.contexto()}), 200
    except Exception as exc:
        return _erro('falha_na_consulta', exc, 502)


@app.get('/scores')
def scores():
    dispositivo = _dispositivo_para(request.args.get('dispositivo', 'SOMPO-ESP32'))
    eq = frota.id_selecionado()
    dias = frota.periodo()   # 1..365, senao 400 dias_invalido (como no /operacoes)

    try:
        eventos = consultar_eventos(dispositivo, dias=dias, equipamento=eq) if dispositivo or eq else []
        return jsonify({**calcular_scores(dispositivo, dias, eventos), **frota.contexto()}), 200
    except Exception as exc:
        return _erro('falha_na_consulta', exc, 502)


@app.get('/relatorio/bruto')
def relatorio_bruto():
    dispositivo = _dispositivo_para(request.args.get('dispositivo', 'SOMPO-ESP32'))
    eq = frota.id_selecionado()
    dias = frota.periodo()   # 1..365, senao 400 dias_invalido (como no /operacoes)

    try:
        resumo_por_dia = consultar_resumo(dispositivo, dias=dias, equipamento=eq) if dispositivo or eq else []
        eventos = frota.identificar_registros(consultar_eventos(dispositivo, dias=dias, equipamento=eq) if dispositivo or eq else [])
        relatorio = montar_relatorio_bruto(dispositivo, dias, resumo_por_dia, eventos)
        relatorio.update(frota.contexto())
        return jsonify(relatorio), 200
    except Exception as exc:
        return _erro('falha_na_geracao_do_relatorio', exc, 502)


def _separar_periodo(eventos, dias):
    """(ultimos `dias` dias, os `dias` dias anteriores). Sem data -> conta como atual."""
    corte = datetime.now(timezone.utc) - timedelta(days=dias)
    atuais, anteriores = [], []
    for evento in eventos:
        try:
            quando = datetime.fromisoformat(str(evento.get('criado_em')).replace('Z', '+00:00'))
            if quando.tzinfo is None:
                quando = quando.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            quando = None
        (anteriores if quando is not None and quando < corte else atuais).append(evento)
    return atuais, anteriores


@app.get('/relatorio/risco')
def relatorio_risco():
    dispositivo = _dispositivo_para(request.args.get('dispositivo', 'SOMPO-ESP32'))
    eq = frota.id_selecionado()
    dias = frota.periodo()   # 1..365, senao 400 dias_invalido (como no /operacoes)

    try:
        resumo_por_dia = consultar_resumo(dispositivo, dias=dias, equipamento=eq) if dispositivo or eq else []
        # Busca 2x a janela: os ultimos N dias viram o relatorio; os N dias antes deles
        # so geram os scores de comparacao ("anterior", variacao nos cards da tela).
        todos = frota.identificar_registros(consultar_eventos(dispositivo, dias=dias * 2, equipamento=eq) if dispositivo or eq else [])
        eventos, anteriores = _separar_periodo(todos, dias)
        # novo=1: botao "Gerar de novo" da tela -> ignora o cache da IA.
        novo = request.args.get('novo', '').lower() in {'1', 'true'}
        # ia=0: refresh de 5 s do painel -> medidores sem esperar o LLM (texto de template).
        usar_ia = request.args.get('ia', '').lower() not in {'0', 'false'}
        resultado = montar_relatorio_risco(dispositivo, dias, resumo_por_dia, eventos,
                                           contexto=frota.contexto(), forcar=novo, usar_ia=usar_ia)
        ant = calcular_scores(dispositivo, dias, anteriores)
        resultado['anterior'] = {'score_furto': ant['score_furto'], 'score_incendio': ant['score_incendio'],
                                 'eventos': ant['eventos_considerados']}
        return jsonify(resultado), 200
    except Exception as exc:
        return _erro('falha_na_geracao_do_relatorio', exc, 502)


@app.get('/relatorio/risco.pdf')
def relatorio_risco_pdf():
    # Mesmo conteúdo do /relatorio/risco, mas como PDF para download (abre em qualquer celular).
    dispositivo = _dispositivo_para(request.args.get('dispositivo', 'SOMPO-ESP32'))
    eq = frota.id_selecionado()
    dias = frota.periodo()   # 1..365, senao 400 dias_invalido (como no /operacoes)

    try:
        resumo_por_dia = consultar_resumo(dispositivo, dias=dias, equipamento=eq) if dispositivo or eq else []
        eventos = frota.identificar_registros(consultar_eventos(dispositivo, dias=dias, equipamento=eq) if dispositivo or eq else [])
        relatorio = montar_relatorio_risco(dispositivo, dias, resumo_por_dia, eventos, contexto=frota.contexto())
        import documento   # tardio: fpdf2 (Pillow, fontTools) pesava ~1 s em todo cold start
        conteudo = documento.montar_pdf(relatorio, eventos)

        carimbo = datetime.now(documento.FUSO_BRASILIA).strftime('%Y%m%d_%H%M')
        nome = f'relatorio_risco_{dispositivo or f"maquina_{eq}"}_{carimbo}.pdf'
        return Response(
            conteudo,
            mimetype='application/pdf',
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
        logo = _logo_url(corpo.get('logo_url'))
    except ValueError:
        return jsonify({'erro': 'logo_invalido'}), 400
    if logo:
        payload['logo_url'] = logo

    try:
        criado = inserir_tabela('cliente', payload)
        return jsonify({'ok': True, 'cliente': criado}), 201
    except Exception as exc:
        return _erro('falha_ao_criar_cliente', exc, 502)


def _logo_url(valor):
    # Link do logo vira <img src> no painel: so https, ate 500 caracteres (o mesmo check
    # de firmware/sql/clientes_logo.sql) e sem espaco, aspas ou < >. Vazio -> None.
    if valor is None:
        return None
    if not isinstance(valor, str):
        raise ValueError
    valor = valor.strip()
    if not valor:
        return None
    if not valor.startswith('https://') or len(valor) > 500 or re.search(r'''[\s"'<>]''', valor):
        raise ValueError
    return valor


@app.patch('/clientes/<int:value>')
@somente_sompo
def clientes_trocar_logo(value):
    # Nao ha edicao de cliente: esta rota altera SO o logo (os outros campos sao ignorados).
    corpo = request.get_json(silent=True) or {}
    if 'logo_url' not in corpo:
        return jsonify({'erro': 'nada_para_atualizar'}), 400
    try:
        logo = _logo_url(corpo['logo_url'])
    except ValueError:
        return jsonify({'erro': 'logo_invalido'}), 400

    try:
        atualizado = atualizar_tabela('cliente', {'id_cliente': f'eq.{value}', 'excluido_em': 'is.null'},
                                      {'logo_url': logo})
    except SupabaseError as exc:
        if exc.codigo == 'PGRST204':
            # Coluna desconhecida: firmware/sql/clientes_logo.sql ainda nao rodou no Supabase.
            return _erro('migracao_pendente', exc, 409)
        return _erro('falha_ao_editar_cliente', exc, 502)
    except Exception as exc:
        return _erro('falha_ao_editar_cliente', exc, 502)
    if not atualizado:
        return jsonify({'erro': 'nao_encontrado'}), 404
    return jsonify({'ok': True, 'cliente': atualizado}), 200


@app.get('/fazendas')
@somente_sompo
def fazendas_listar():
    try:
        dados = consultar_fazendas()
        gestores = consultar_gestores([f['id_fazenda'] for f in dados])
        for f in dados:
            f['gestores'] = [{'id_usuario': g['id_usuario'], 'usuario': g['usuario']}
                             for g in gestores if g['fk_fazenda_id_fazenda'] == f['id_fazenda']]
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


def _coordenada(valor, limite):
    # None limpa a coordenada; qualquer outro valor precisa ser numero dentro do limite.
    if valor is None:
        return None
    if isinstance(valor, bool):
        raise ValueError(valor)
    numero = float(valor)
    if not -limite <= numero <= limite:
        raise ValueError(valor)
    return numero


@app.patch('/fazendas/<int:value>')
@somente_sompo
def fazendas_editar(value):
    corpo = request.get_json(silent=True)
    corpo = corpo if isinstance(corpo, dict) else {}
    dados: Dict[str, Any] = {}
    if 'latitude' in corpo or 'longitude' in corpo:
        # O mapa precisa do par: latitude sem longitude (ou o contrario) nao posiciona nada.
        if 'latitude' not in corpo or 'longitude' not in corpo or (corpo['latitude'] is None) != (corpo['longitude'] is None):
            return jsonify({'erro': 'coordenadas_incompletas'}), 400
        for campo, limite in (('latitude', 90), ('longitude', 180)):
            try:
                dados[campo] = _coordenada(corpo[campo], limite)
            except (TypeError, ValueError):
                return jsonify({'erro': f'{campo}_invalida'}), 400
    for campo, erro in (('nome', 'nome_obrigatorio'), ('localizacao', 'localizacao_obrigatoria')):
        if campo in corpo:
            texto = str(corpo[campo] or '').strip()
            if not texto:
                return jsonify({'erro': erro}), 400
            dados[campo] = texto
    if 'area_ha' in corpo:
        try:
            if isinstance(corpo['area_ha'], bool):
                raise ValueError
            area = float(corpo['area_ha'])
        except (TypeError, ValueError):
            return jsonify({'erro': 'area_invalida'}), 400
        if not math.isfinite(area) or area < 0:
            return jsonify({'erro': 'area_invalida'}), 400
        dados['area_ha'] = area
    if not dados:
        return jsonify({'erro': 'nada_para_atualizar'}), 400

    try:
        atualizada = atualizar_tabela('fazenda', {'id_fazenda': f'eq.{value}', 'excluido_em': 'is.null'}, dados)
    except SupabaseError as exc:
        if exc.codigo == 'PGRST204':
            # Coluna desconhecida: firmware/sql/mapa_ocorrencias.sql ainda nao rodou no Supabase.
            return _erro('migracao_pendente', exc, 409)
        return _erro('falha_ao_editar_fazenda', exc, 502)
    except Exception as exc:
        return _erro('falha_ao_editar_fazenda', exc, 502)
    if not atualizada:
        return jsonify({'erro': 'nao_encontrado'}), 404
    return jsonify({'ok': True, 'fazenda': atualizada}), 200


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

    payload: Dict[str, Any] = {'usuario': usuario, 'senha': generate_password_hash(senha), 'role': role}
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
        if status == 200:
            _revalidados.clear()   # uma exclusao pode revogar logins: sem esperar os 20 s do cache
        return jsonify(resultado), status
    except frota.FrotaErro:
        raise
    except Exception as exc:
        return _erro('falha_ao_excluir', exc, 502)


if __name__ == '__main__':
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
