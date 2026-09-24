"""Cadastros e autorização da frota. Identidade do operador não é login."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import re
import secrets

from flask import Blueprint, current_app, g, jsonify, request, session
import supabase_client as db
from scores import calcular_scores

bp = Blueprint('frota', __name__)


class FrotaErro(Exception):
    def __init__(self, codigo, status=400):
        self.codigo, self.status = codigo, status


@bp.app_errorhandler(FrotaErro)
def erro_frota(exc):
    return jsonify(erro=exc.codigo), exc.status


@bp.errorhandler(Exception)
def erro_banco(exc):
    if isinstance(exc, FrotaErro):
        return erro_frota(exc)
    if isinstance(exc, db.SupabaseError):
        if exc.codigo == '23505':
            return jsonify(erro='cadastro_duplicado'), 409
        if exc.codigo in {'23514', '23503', '22P02', '22023'}:
            return jsonify(erro='dados_invalidos'), 400
        if exc.status == 409 or exc.codigo == 'P0001':
            return jsonify(erro='operacao_em_conflito'), 409
    current_app.logger.warning('Frota indisponível: %s', exc)
    return jsonify(erro='frota_indisponivel'), 502


def inteiro(value, nome='id', minimo=1, maximo=None):
    if isinstance(value, bool) or not re.fullmatch(r'\d+', str(value)):
        raise FrotaErro(f'{nome}_invalido')
    n = int(value)
    if n < minimo or (maximo is not None and n > maximo):
        raise FrotaErro(f'{nome}_invalido')
    return n


def papel():
    role = session.get('role', 'sompo')
    if role not in {'sompo', 'gestor_fazenda'}:
        raise FrotaErro('proibido', 403)
    if role == 'gestor_fazenda' and not session.get('fazenda_id'):
        raise FrotaErro('fazenda_nao_vinculada', 403)
    return role


def autorizar_fazenda(fazenda_id):
    if papel() == 'gestor_fazenda' and str(fazenda_id) != str(session['fazenda_id']):
        raise FrotaErro('proibido', 403)


def obter(tabela, pk, value):
    rows = db.consultar_tabela(tabela, filtros={pk: f'eq.{inteiro(value)}'}, limite=1)
    if not rows:
        raise FrotaErro('nao_encontrado', 404)
    return rows[0]


def equipamento(value, historico=False):
    papel()
    row = obter('equipamentos', 'id_equipamento', value)
    autorizar_fazenda(row.get('fk_fazenda_id_fazenda'))
    if row.get('excluido_em') and not historico:
        raise FrotaErro('nao_encontrado', 404)
    return row


def operador(value, historico=False):
    papel()
    row = obter('operadores', 'id_operador', value)
    autorizar_fazenda(row.get('fk_fazenda_id_fazenda'))
    if row.get('excluido_em') and not historico:
        raise FrotaErro('nao_encontrado', 404)
    return row


def filtros_fazenda():
    role = papel()
    value = session['fazenda_id'] if role == 'gestor_fazenda' else request.args.get('fazenda')
    return {'excluido_em': 'is.null', **({'fk_fazenda_id_fazenda': f'eq.{inteiro(value)}'} if value else {})}


def corpo_json():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise FrotaErro('json_invalido')
    return value


def texto(value, nome, tamanho=255, obrigatorio=False):
    if value is None:
        value = ''
    if not isinstance(value, str):
        raise FrotaErro(f'{nome}_invalido')
    value = value.strip()
    if len(value) > tamanho or (obrigatorio and not value):
        raise FrotaErro(f'{nome}_invalido')
    return value or None


def fazenda_cadastro(corpo, atual=None):
    value = corpo.get('fk_fazenda_id_fazenda',
                      atual.get('fk_fazenda_id_fazenda') if atual else session.get('fazenda_id'))
    fazenda_id = inteiro(value, 'fazenda')
    if atual and atual.get('fk_fazenda_id_fazenda') is not None and fazenda_id != atual['fk_fazenda_id_fazenda']:
        raise FrotaErro('transferencia_nao_permitida', 409)
    autorizar_fazenda(fazenda_id)
    faz = obter('fazenda', 'id_fazenda', fazenda_id)
    if faz.get('excluido_em'):
        raise FrotaErro('fazenda_excluida', 409)
    if not faz.get('fk_cliente_id_cliente'):
        raise FrotaErro('fazenda_sem_cliente', 409)
    return faz


def ativo(corpo):
    value = corpo.get('ativo', True)
    if not isinstance(value, bool):
        raise FrotaErro('ativo_invalido')
    return value


def dados_equipamento(corpo, atual=None):
    atual = atual or {}
    faz = fazenda_cadastro(corpo, atual)
    merged = {**atual, **corpo}
    dev = texto(merged.get('dispositivo_id'), 'dispositivo', 64)
    if dev and not re.fullmatch(r'[A-Za-z0-9_-]+', dev):
        raise FrotaErro('dispositivo_invalido')
    dados = {
        'nome': texto(merged.get('nome'), 'nome', obrigatorio=True),
        'fk_fazenda_id_fazenda': faz['id_fazenda'],
        'fk_cliente_id_cliente': faz['fk_cliente_id_cliente'],
        'dispositivo_id': dev, 'ativo': ativo(merged),
    }
    for campo in ('tipo', 'modelo'):
        if campo in merged:
            dados[campo] = texto(merged[campo], campo, 100)
    for campo in ('fabricacao', 'ultima_manutencao'):
        if campo in merged:
            value = merged[campo]
            try:
                dados[campo] = date.fromisoformat(str(value)[:10]).isoformat() if value else None
            except ValueError:
                raise FrotaErro(f'{campo}_invalida')
    if 'valor_segurado' in merged:
        try:
            valor = Decimal(str(merged['valor_segurado'])) if merged['valor_segurado'] not in (None, '') else None
            if valor is not None and (not valor.is_finite() or valor < 0):
                raise InvalidOperation
            dados['valor_segurado'] = str(valor) if valor is not None else None
        except (InvalidOperation, ValueError):
            raise FrotaErro('valor_segurado_invalido')
    if dev:
        # O ESP32 de uma maquina excluida fica livre (o historico dela continua com ela).
        encontrados = db.consultar_tabela('equipamentos', filtros={'dispositivo_id': f'eq.{dev}', 'excluido_em': 'is.null'}, limite=1)
        if encontrados and encontrados[0]['id_equipamento'] != atual.get('id_equipamento'):
            raise FrotaErro('dispositivo_ja_vinculado', 409)
    return dados


def dados_operador(corpo, atual=None):
    atual = atual or {}
    faz = fazenda_cadastro(corpo, atual)
    merged = {**atual, **corpo}
    uid = texto(merged.get('uid'), 'uid', 40, True)
    uid = re.sub(r'[\s:-]', '', uid).upper()
    if len(uid) not in (8, 14, 20) or not re.fullmatch(r'[0-9A-F]+', uid):
        raise FrotaErro('uid_invalido')
    # Só operadores ativos seguram o crachá: o de um excluído pode ir para outra pessoa.
    rows = db.consultar_tabela('operadores', filtros={'uid': f'eq.{uid}', 'excluido_em': 'is.null'}, limite=1)
    if rows and rows[0]['id_operador'] != atual.get('id_operador'):
        raise FrotaErro('cracha_ja_cadastrado', 409)
    return {'nome': texto(merged.get('nome'), 'nome', obrigatorio=True),
            'matricula': texto(merged.get('matricula'), 'matricula', 100),
            'uid': uid, 'ativo': ativo(merged), 'fk_fazenda_id_fazenda': faz['id_fazenda']}


@bp.get('/equipamentos')
def listar_equipamentos():
    rows = db.consultar_todos('equipamentos', filtros=filtros_fazenda(), order='nome.asc,id_equipamento.asc')
    return jsonify(dados=rows, total=len(rows))


@bp.post('/equipamentos')
def criar_equipamento():
    papel()
    row = db.inserir_tabela('equipamentos', dados_equipamento(corpo_json()))
    return jsonify(ok=True, equipamento=row), 201


@bp.get('/equipamentos/<int:value>')
def ler_equipamento(value):
    return jsonify(equipamento=equipamento(value))


@bp.patch('/equipamentos/<int:value>')
def editar_equipamento(value):
    anterior = equipamento(value)
    dados = dados_equipamento(corpo_json(), anterior)
    row = db.atualizar_tabela('equipamentos', {'id_equipamento': f'eq.{value}'}, dados)
    return jsonify(ok=True, equipamento=row)


@bp.get('/operadores')
def listar_operadores():
    rows = db.consultar_todos('operadores', filtros=filtros_fazenda(), order='nome.asc,id_operador.asc')
    return jsonify(dados=rows, total=len(rows))


@bp.post('/operadores')
def criar_operador():
    papel()
    row = db.inserir_tabela('operadores', dados_operador(corpo_json()))
    return jsonify(ok=True, operador=row), 201


@bp.get('/operadores/<int:value>')
def ler_operador(value):
    return jsonify(operador=operador(value))


@bp.patch('/operadores/<int:value>')
def editar_operador(value):
    dados = dados_operador(corpo_json(), operador(value))
    row = db.atualizar_tabela('operadores', {'id_operador': f'eq.{value}'}, dados)
    return jsonify(ok=True, operador=row)


@bp.get('/equipamentos/<int:value>/operadores')
def listar_autorizacoes(value):
    equipamento(value)
    rows = db.consultar_todos('operador_equipamento', filtros={
        'equipamento_id': f'eq.{value}', 'ativo': 'eq.true'}, order='operador_id.asc')
    return jsonify(dados=rows, total=len(rows))


@bp.put('/equipamentos/<int:value>/operadores')
def definir_autorizacoes(value):
    eq = equipamento(value)
    ids = corpo_json().get('operador_ids')
    if not isinstance(ids, list):
        raise FrotaErro('operador_ids_invalidos')
    ids = sorted({inteiro(i, 'operador') for i in ids})
    for i in ids:
        op = operador(i)
        if op['fk_fazenda_id_fazenda'] != eq['fk_fazenda_id_fazenda']:
            raise FrotaErro('operador_de_outra_fazenda', 403)
        if not op['ativo']:
            raise FrotaErro('operador_inativo', 409)
    db.chamar_rpc('definir_operadores_equipamento', {'p_equipamento_id': value, 'p_operador_ids': ids})
    return listar_autorizacoes(value)


@bp.post('/equipamentos/<int:value>/credencial')
def criar_credencial(value):
    eq = equipamento(value)
    if not eq.get('dispositivo_id'):
        raise FrotaErro('equipamento_sem_dispositivo', 409)
    token = secrets.token_urlsafe(32)
    db.chamar_rpc('provisionar_dispositivo', {
        'p_equipamento_id': value, 'p_token_hash': hashlib.sha256(token.encode()).hexdigest()})
    response = jsonify(dispositivo_id=eq['dispositivo_id'], token=token)
    response.headers['Cache-Control'] = 'no-store'
    return response, 201


def resolver_equipamento():
    """Autoriza antes de qualquer consulta de telemetria ou relatório."""
    papel()
    eid, dev = request.args.get('equipamento'), request.args.get('dispositivo')
    if not eid and not dev:
        raise FrotaErro('equipamento_obrigatorio')
    if eid:
        eq = equipamento(eid, historico=True)
        if dev and dev != eq.get('dispositivo_id'):
            raise FrotaErro('seletores_incompativeis')
    else:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', dev):
            raise FrotaErro('dispositivo_invalido')
        rows = db.consultar_tabela('equipamentos', filtros={'dispositivo_id': f'eq.{dev}', 'excluido_em': 'is.null'}, limite=1)
        if not rows:
            if papel() != 'sompo':
                raise FrotaErro('proibido', 403)
            g.equipamento = None
            return dev  # consulta explícita de dados legados pela Sompo
        eq = rows[0]
        autorizar_fazenda(eq.get('fk_fazenda_id_fazenda'))
    g.equipamento = eq
    return eq.get('dispositivo_id')


def id_selecionado():
    # Maquina resolvida por resolver_equipamento(): as leituras sao filtradas por ela.
    eq = getattr(g, 'equipamento', None)
    return eq['id_equipamento'] if eq else None


def contexto():
    eq = getattr(g, 'equipamento', None)
    if not eq:
        return {}
    faz = obter('fazenda', 'id_fazenda', eq['fk_fazenda_id_fazenda']) if eq.get('fk_fazenda_id_fazenda') else None
    return {'equipamento': eq, 'fazenda': faz}


def identificar_registros(rows):
    eq = getattr(g, 'equipamento', None)
    if not eq:
        return rows
    ids = sorted({r['operador_id'] for r in rows if r.get('operador_id')})
    ops = db.consultar_todos('operadores', filtros={
        'id_operador': 'in.(' + ','.join(map(str, ids)) + ')',
        'fk_fazenda_id_fazenda': f'eq.{eq["fk_fazenda_id_fazenda"]}',
    }, order='id_operador.asc') if ids else []
    nomes = {o['id_operador']: o['nome'] for o in ops}
    return [{**r, 'equipamento_nome': eq['nome'],
             'operador_nome': nomes.get(r.get('operador_id'), 'Operador não identificado'),
             'horario_ocorrencia': r.get('ocorrido_em') if r.get('registro_id') else r.get('criado_em')}
            for r in rows]


def periodo():
    return inteiro(request.args.get('dias', 7), 'dias', maximo=365)


@bp.get('/operacoes')
def listar_operacoes():
    papel()
    filtros = {}
    if papel() == 'gestor_fazenda':
        filtros['fazenda_id'] = f'eq.{session["fazenda_id"]}'
    elif request.args.get('fazenda'):
        filtros['fazenda_id'] = f'eq.{inteiro(request.args["fazenda"], "fazenda")}'
    if request.args.get('equipamento'):
        eq = equipamento(request.args['equipamento'], historico=True)
        filtros['equipamento_id'] = f'eq.{eq["id_equipamento"]}'
    if request.args.get('operador'):
        op = operador(request.args['operador'], historico=True)
        filtros['operador_id'] = f'eq.{op["id_operador"]}'
    rows = db.consultar_periodo('sessoes_operacao', filtros, periodo(),
                               campo='recebido_em', order='recebido_em.desc,sessao_id.asc')
    pagina = inteiro(request.args.get('pagina', 1), 'pagina')
    limite = inteiro(request.args.get('limite', 50), 'limite', maximo=200)
    start = (pagina-1)*limite
    return jsonify(dados=rows[start:start+limite], total=len(rows), pagina=pagina, limite=limite)


def _resumos(fazendas, dias):
    # Resumo de varias fazendas com poucas consultas: maquinas de todas numa consulta e, em
    # paralelo, leituras, eventos e operadores (cada consulta cruza EUA -> Supabase em SP).
    ids = [f['id_fazenda'] for f in fazendas]
    if not ids:
        return []
    em_ids = 'in.(' + ','.join(map(str, ids)) + ')'
    maquinas = db.consultar_todos('equipamentos', filtros={'fk_fazenda_id_fazenda': em_ids, 'excluido_em': 'is.null'},
                                  order='nome.asc,id_equipamento.asc')
    # O historico acompanha a maquina: o ESP32 pode ter mudado de maquina.
    ids_maquinas = [m['id_equipamento'] for m in maquinas]
    filtros = {'equipamento_id': 'in.(' + ','.join(map(str, ids_maquinas)) + ')'}
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_leituras = pool.submit(db.consultar_todos, 'ultima_telemetria_maquina', filtros=filtros, order='equipamento_id.asc') if ids_maquinas else None
        f_eventos = pool.submit(db.consultar_periodo, 'eventos', filtros, dias) if ids_maquinas else None
        f_operadores = pool.submit(db.consultar_todos, 'operadores', filtros={'fk_fazenda_id_fazenda': em_ids}, order='id_operador.asc')
        leituras = f_leituras.result() if f_leituras else []
        eventos = f_eventos.result() if f_eventos else []
        operadores = f_operadores.result()
    return [_resumo_de(f, [m for m in maquinas if m.get('fk_fazenda_id_fazenda') == f['id_fazenda']],
                       leituras, eventos, [o for o in operadores if o.get('fk_fazenda_id_fazenda') == f['id_fazenda']], dias)
            for f in fazendas]


@bp.get('/carteira')
def carteira():
    # Inicio da Sompo: fazendas e o resumo de cada uma numa chamada so.
    if papel() != 'sompo':
        raise FrotaErro('proibido', 403)
    fazendas = db.consultar_fazendas()
    return jsonify(dados=_resumos(fazendas, periodo()))


@bp.get('/fazendas/<int:value>/resumo')
def resumo_fazenda(value):
    autorizar_fazenda(value)
    faz = obter('fazenda', 'id_fazenda', value)
    if faz.get('excluido_em'):
        raise FrotaErro('nao_encontrado', 404)
    return jsonify(**_resumos([faz], periodo())[0])


def _resumo_de(faz, maquinas, leituras, eventos, operadores, dias):
    maquina_por_id = {m['id_equipamento']: m for m in maquinas}
    eventos = [ev for ev in eventos if ev.get('equipamento_id') in maquina_por_id]
    nomes = {o['id_operador']: o['nome'] for o in operadores}
    por_maquina = {r['equipamento_id']: r for r in leituras if r.get('equipamento_id') in maquina_por_id}
    eventos_maquina = {}
    for ev in eventos:
        eventos_maquina.setdefault(ev['equipamento_id'], []).append(ev)
    agora = datetime.now(timezone.utc)
    for m in maquinas:
        dev = m.get('dispositivo_id')
        t = por_maquina.get(m['id_equipamento'])
        estado = 'sem_dispositivo' if not dev else 'sem_dados'
        if t and dev:
            estado = 'atrasada'
            try:
                # O instante de captura evita exibir backlog recém recebido como presença atual.
                captura = t.get('ocorrido_em') if t.get('registro_id') else t.get('criado_em')
                stamp = datetime.fromisoformat(captura.replace('Z', '+00:00'))
                if 0 <= (agora-stamp).total_seconds() <= 30:
                    estado = 'recente'
            except (TypeError, ValueError, AttributeError):
                pass
        m.update(ultima_telemetria=t, comunicacao=estado,
                 operador_nome=nomes.get(t.get('operador_id') if t else None, 'Operador não identificado'),
                 scores=calcular_scores(dev or '', dias, eventos_maquina.get(m['id_equipamento'], [])),
                 config_pendente=m.get('config_versao_aplicada') != m.get('config_versao', 1))
    # Os 10 alertas mais recentes da fazenda (Inicio do gestor), pelo instante de captura.
    # A maquina gravada no evento manda: um ESP32 que trocou de maquina nao leva os alertas junto.
    alertas = []
    for ev in eventos:
        m = maquina_por_id[ev['equipamento_id']]
        alertas.append({**ev, 'equipamento_nome': m['nome'],
                        'horario_ocorrencia': ev.get('ocorrido_em') if ev.get('registro_id') else ev.get('criado_em')})
    alertas.sort(key=lambda a: a['horario_ocorrencia'] or '', reverse=True)
    return {'fazenda': faz, 'equipamentos': maquinas, 'alertas_recentes': alertas[:10]}
