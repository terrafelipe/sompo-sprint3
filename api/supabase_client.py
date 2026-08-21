from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from config import SUPABASE_URL, SUPABASE_SECRET_KEY, get_supabase_headers, validate_supabase_config


BASE_URL = f'{SUPABASE_URL.rstrip("/")}/rest/v1' if SUPABASE_URL else ''


def _request_json(method: str, table: str, params: Optional[Dict[str, str]] = None, payload: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    validate_supabase_config()
    url = f'{BASE_URL}/{table}'
    headers = get_supabase_headers()
    response = requests.request(
        method=method,
        url=url,
        headers=headers,
        params=params or {},
        json=payload,
        timeout=10,
    )
    if response.status_code >= 400:
        detail = response.text[:500]
        raise RuntimeError(f'Erro ao consultar Supabase: {response.status_code} - {detail}')
    if not response.text:
        return []
    try:
        data = response.json()
        return data if isinstance(data, list) else [data]
    except ValueError as exc:
        raise RuntimeError('Resposta inválida do Supabase') from exc


def consultar_tabela(tabela: str, *, filtros: Optional[Dict[str, str]] = None, limite: int = 50, select: str = '*', order: Optional[str] = None) -> List[Dict[str, Any]]:
    params: Dict[str, str] = {'select': select}
    if filtros:
        for key, value in filtros.items():
            params[f'{key}'] = value
    if order:
        params['order'] = order
    params['limit'] = str(limite)
    return _request_json('GET', tabela, params=params)


def consultar_telemetria(dispositivo: str, limite: int = 50) -> List[Dict[str, Any]]:
    filtros = {'dispositivo_id': f'eq.{dispositivo}'}
    return consultar_tabela('telemetria', filtros=filtros, limite=limite, order='criado_em.desc')


def consultar_eventos(dispositivo: str, dias: int = 7) -> List[Dict[str, Any]]:
    # Some Supabase REST setups may not accept the relative time filter syntax
    # uniformly; to avoid 400/502 errors, only filter by dispositivo here and
    # let callers perform date-based trimming if needed.
    filtros = {
        'dispositivo_id': f'eq.{dispositivo}',
    }
    return consultar_tabela('eventos', filtros=filtros, limite=500, order='criado_em.desc')


def consultar_resumo(dispositivo: str, dias: int = 7) -> List[Dict[str, Any]]:
    filtros = {
        'dispositivo_id': f'eq.{dispositivo}',
    }
    return consultar_tabela('resumo_diario', filtros=filtros, limite=500, order='dia.desc')
