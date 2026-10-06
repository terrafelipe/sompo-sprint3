"""Modo ao vivo: liga a telemetria rapida da placa e entrega o que chegou desde um instante."""
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, g, jsonify, request

import frota
import supabase_client as db

bp = Blueprint('ao_vivo', __name__)

DURACAO = timedelta(hours=2)   # desliga sozinho: o banco compara ao_vivo_ate com now()


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
