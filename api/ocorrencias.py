"""Ocorrencias: fila de tratamento dos alertas (aberta -> em verificacao -> resolvida).

Mesmo escopo da frota: a Sompo ve todas as fazendas; o gestor so a propria.
A tabela vem de firmware/sql/mapa_ocorrencias.sql; sem ela, as rotas respondem 409.
"""
from flask import Blueprint, current_app, jsonify, request, session

import frota
import supabase_client as db

bp = Blueprint('ocorrencias', __name__)

STATUS = ('aberta', 'em_verificacao', 'resolvida')
# Tabela ou coluna desconhecida no PostgREST = migracao ainda nao aplicada no Supabase.
_SEM_MIGRACAO = ('PGRST205', 'PGRST204', '42P01')


@bp.errorhandler(Exception)
def erro(exc):
    if isinstance(exc, frota.FrotaErro):
        return frota.erro_frota(exc)
    codigo = getattr(exc, 'codigo', '') or ''
    if codigo in _SEM_MIGRACAO or any(c in str(exc) for c in _SEM_MIGRACAO):
        return jsonify(erro='migracao_pendente'), 409
    if codigo in {'23514', '23503', '22P02'}:
        return jsonify(erro='dados_invalidos'), 400
    current_app.logger.warning('Ocorrencias indisponiveis: %s', exc)
    return jsonify(erro='ocorrencias_indisponiveis'), 502


def _texto(valor, limite):
    texto = str(valor or '').strip()
    return texto[:limite] or None


def _nomes(tabela, pk, ids, campo='nome'):
    ids = sorted({i for i in ids if i is not None})
    if not ids:
        return {}
    rows = db.consultar_todos(tabela, filtros={pk: 'in.(' + ','.join(map(str, ids)) + ')'},
                              select=f'{pk},{campo}', order=f'{pk}.asc')
    return {r[pk]: r[campo] for r in rows}


def _responsaveis(fazenda_id):
    # Quem pode assumir: usuarios Sompo e os gestores desta fazenda (nao excluidos).
    rows = db.consultar_todos('usuario', filtros={'excluido_em': 'is.null'},
                              select='id_usuario,usuario,role,fk_fazenda_id_fazenda', order='usuario.asc')
    return [r for r in rows if r.get('role') == 'sompo'
            or (r.get('role') == 'gestor_fazenda' and str(r.get('fk_fazenda_id_fazenda')) == str(fazenda_id))]


@bp.get('/ocorrencias')
def listar():
    role = frota.papel()
    fazenda = request.args.get('fazenda')
    if role == 'gestor_fazenda':
        if fazenda and str(fazenda) != str(session['fazenda_id']):
            raise frota.FrotaErro('proibido', 403)
        fazenda = session['fazenda_id']
    filtros = {}
    if fazenda:
        filtros['fazenda_id'] = f'eq.{frota.inteiro(fazenda, "fazenda")}'
    status = request.args.get('status')
    if status:
        if status not in STATUS:
            raise frota.FrotaErro('status_invalido')
        filtros['status'] = f'eq.{status}'
    rows = db.consultar_todos('ocorrencias', filtros=filtros, order='criado_em.desc')
    fazendas = _nomes('fazenda', 'id_fazenda', [r.get('fazenda_id') for r in rows])
    maquinas = _nomes('equipamentos', 'id_equipamento', [r.get('equipamento_id') for r in rows])
    pessoas = _nomes('usuario', 'id_usuario', [r.get('responsavel_id') for r in rows], 'usuario')
    dados = [{**r, 'fazenda_nome': fazendas.get(r.get('fazenda_id')), 'equipamento_nome': maquinas.get(r.get('equipamento_id')),
              'responsavel_nome': pessoas.get(r.get('responsavel_id'))} for r in rows]
    return jsonify(total=len(dados), dados=dados)


@bp.get('/ocorrencias/responsaveis')
def responsaveis():
    fazenda = frota.inteiro(request.args.get('fazenda'), 'fazenda')
    frota.papel()
    frota.autorizar_fazenda(fazenda)
    return jsonify(dados=[{k: r.get(k) for k in ('id_usuario', 'usuario', 'role')} for r in _responsaveis(fazenda)])


@bp.post('/ocorrencias')
def criar():
    frota.papel()
    corpo = request.get_json(silent=True) or {}
    maquina = None
    if corpo.get('equipamento_id') not in (None, ''):
        maquina = frota.equipamento(corpo['equipamento_id'])   # autoriza pela fazenda da maquina
        fazenda_id = maquina['fk_fazenda_id_fazenda']
    else:
        fazenda_id = frota.inteiro(corpo.get('fazenda_id'), 'fazenda')
        frota.autorizar_fazenda(fazenda_id)
        if frota.obter('fazenda', 'id_fazenda', fazenda_id).get('excluido_em'):
            raise frota.FrotaErro('nao_encontrado', 404)
    titulo = _texto(corpo.get('titulo'), 200)
    if not titulo:
        raise frota.FrotaErro('titulo_obrigatorio')

    payload = {'fazenda_id': fazenda_id, 'equipamento_id': maquina['id_equipamento'] if maquina else None,
               'evento_id': None, 'tipo': _texto(corpo.get('tipo'), 60), 'titulo': titulo,
               'descricao': _texto(corpo.get('descricao'), 2000), 'criado_por': session.get('usuario') or 'sompo'}
    if corpo.get('evento_id') not in (None, ''):
        if not maquina:
            raise frota.FrotaErro('evento_sem_maquina')
        evento = frota.obter('eventos', 'id', corpo['evento_id'])
        if evento.get('equipamento_id') not in (None, maquina['id_equipamento']) \
                or (evento.get('equipamento_id') is None and evento.get('dispositivo_id') != maquina.get('dispositivo_id')):
            raise frota.FrotaErro('evento_de_outra_maquina')
        existente = db.consultar_tabela('ocorrencias', filtros={'evento_id': f'eq.{evento["id"]}'}, limite=1)
        if existente:
            return jsonify(erro='ocorrencia_ja_existe', id_ocorrencia=existente[0]['id_ocorrencia']), 409
        payload.update(evento_id=evento['id'], tipo=evento.get('tipo'))
    criada = db.inserir_tabela('ocorrencias', payload)
    return jsonify(ok=True, ocorrencia=criada), 201


@bp.patch('/ocorrencias/<value>')
def editar(value):
    frota.papel()
    ocorrencia = frota.obter('ocorrencias', 'id_ocorrencia', value)
    frota.autorizar_fazenda(ocorrencia['fazenda_id'])
    corpo = request.get_json(silent=True) or {}
    dados = {}
    if 'status' in corpo:
        if corpo['status'] not in STATUS:
            raise frota.FrotaErro('status_invalido')
        dados['status'] = corpo['status']
    if 'responsavel_id' in corpo:
        responsavel = corpo['responsavel_id']
        if responsavel not in (None, ''):
            responsavel = frota.inteiro(responsavel, 'responsavel')
            if responsavel not in {r['id_usuario'] for r in _responsaveis(ocorrencia['fazenda_id'])}:
                raise frota.FrotaErro('responsavel_invalido')
        dados['responsavel_id'] = responsavel or None
    if 'nota' in corpo:
        dados['nota'] = _texto(corpo['nota'], 2000)
    if not dados:
        raise frota.FrotaErro('nada_para_atualizar')
    atualizada = db.atualizar_tabela('ocorrencias', {'id_ocorrencia': f'eq.{ocorrencia["id_ocorrencia"]}'}, dados)
    return jsonify(ok=True, ocorrencia=atualizada)
