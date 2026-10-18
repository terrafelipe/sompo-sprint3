"""Modo ao vivo: liga a telemetria rapida da placa e entrega o que chegou desde um instante."""
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, g, jsonify, request

import frota
import supabase_client as db

bp = Blueprint('ao_vivo', __name__)

DURACAO = timedelta(hours=2)   # desliga sozinho: o banco compara ao_vivo_ate com now()
JANELA_PADRAO = timedelta(seconds=30)
JANELA_MAX = timedelta(minutes=10)
FOLGA_FUTURO = timedelta(seconds=5)
RECUO_CURSOR = timedelta(seconds=5)   # linha confirmada (commit) um pouco depois do instante do cursor
LIMITE = 30
COLUNAS = {
    'telemetria': 'registro_id,equipamento_id,criado_em,ocorrido_em,recebido_em,temp_escape,temp_ambiente,umidade_ar,'
                  'chama_detectada,vibracao,motor_ligado,capo_aberto,tanque_aberto,operador_autorizado,nivel_risco,'
                  'operador_id,uid',
    'eventos': 'registro_id,equipamento_id,criado_em,ocorrido_em,recebido_em,tipo,severidade,temp_escape,operador_id',
    'registros_operacao': 'registro_id,equipamento_id,ocorrido_em,recebido_em,tipo,motivo,uid,operador_id,sessao_id',
}


@bp.errorhandler(db.SupabaseError)
def erro_banco(exc):
    # Detalhe so no log do servidor (ver docs/SEGURANCA.md).
    current_app.logger.warning('Ao vivo indisponivel: %s', exc)
    return jsonify(erro='falha_na_consulta'), 502


@bp.post('/equipamentos/<int:value>/ao-vivo')
def ligar_ao_vivo(value):
    eq = frota.equipamento(value)
    ligar = frota.corpo_json().get('ligar')
    if not isinstance(ligar, bool):
        raise frota.FrotaErro('ligar_invalido')
    if not eq.get('dispositivo_id'):
        raise frota.FrotaErro('equipamento_sem_dispositivo', 409)
    ate = (datetime.now(timezone.utc) + DURACAO).isoformat() if ligar else None
    db.atualizar_tabela('equipamentos', {'id_equipamento': f'eq.{value}'}, {'ao_vivo_ate': ate})
    return jsonify(ok=True, ao_vivo_ate=ate)


def _instante(texto):
    return datetime.fromisoformat(texto.strip().replace(' ', '+').replace('Z', '+00:00'))


def _desde(texto, agora):
    if not texto:
        return agora - JANELA_PADRAO
    try:
        # '+' do fuso chega como espaco quando o cliente nao codifica a URL.
        t = _instante(texto)
    except ValueError:
        raise frota.FrotaErro('desde_invalido')
    if t.tzinfo is None or t > agora + FOLGA_FUTURO or t < agora - JANELA_MAX:
        raise frota.FrotaErro('desde_invalido')
    return t


def _depois(tabela, equipamento_id, desde):
    # As 30 mais novas (desc), devolvidas em ordem crescente para o terminal.
    rows = db.consultar_tabela(tabela, filtros={'equipamento_id': f'eq.{equipamento_id}',
                                                'recebido_em': f'gt.{desde.isoformat()}'},
                               select=COLUNAS[tabela], order='recebido_em.desc', limite=LIMITE)
    return list(reversed(rows))


@bp.get('/ao-vivo')
def ao_vivo():
    frota.resolver_equipamento()
    eq = getattr(g, 'equipamento', None)
    if not eq:   # Sompo consultando ID legado sem maquina: o ao vivo e por maquina
        raise frota.FrotaErro('equipamento_obrigatorio')
    agora = datetime.now(timezone.utc)
    desde = _desde(request.args.get('desde'), agora)
    telemetria = frota.identificar_registros(_depois('telemetria', eq['id_equipamento'], desde))
    eventos = _depois('eventos', eq['id_equipamento'], desde)
    operacoes = frota.identificar_registros(_depois('registros_operacao', eq['id_equipamento'], desde))
    # O cursor recua sempre: as 3 consultas nao sao atomicas, e saltar ate a linha mais nova perderia
    # uma linha de recebido_em anterior confirmada depois. O painel deduplica pelo registro_id.
    cursor = agora - RECUO_CURSOR
    resposta = jsonify(telemetria=telemetria, eventos=eventos, operacoes=operacoes,
                       ao_vivo_ate=eq.get('ao_vivo_ate'), cursor=cursor.isoformat(), agora=agora.isoformat())
    resposta.headers['Cache-Control'] = 'no-store'
    return resposta
