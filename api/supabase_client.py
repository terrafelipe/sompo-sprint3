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


# --- Cadastro de negocio (dashboard): clientes e fazendas ---------------------

def consultar_clientes() -> List[Dict[str, Any]]:
    # Traz tambem os dados de contato, para o modal de detalhe do cliente no painel.
    # O dropdown de "dono da fazenda" usa so id+nome; os campos extras nao atrapalham.
    return consultar_tabela('cliente', select='id_cliente,nome,cnpj,telefone,endereco,email', order='nome.asc', limite=200)


def consultar_fazendas() -> List[Dict[str, Any]]:
    # Embed do PostgREST traz os dados do cliente dono junto (cliente(...)), usados no
    # modal de detalhe da fazenda.
    return consultar_tabela(
        'fazenda',
        select='*,cliente(nome,cnpj,telefone,email)',
        order='criado_em.desc',
        limite=200,
    )


def consultar_usuarios() -> List[Dict[str, Any]]:
    # Lista de logins do painel SEM a senha, com o nome da fazenda vinculada embutido.
    return consultar_tabela(
        'usuario',
        select='id_usuario,usuario,role,fk_fazenda_id_fazenda,fazenda(nome)',
        order='usuario.asc',
        limite=200,
    )


def buscar_usuario(usuario: str) -> Optional[Dict[str, Any]]:
    # Login por perfil: busca 1 usuario pelo nome, com a fazenda vinculada embutida
    # (nome + dispositivo_id) para escopar a telemetria do gestor_fazenda.
    linhas = consultar_tabela(
        'usuario',
        filtros={'usuario': f'eq.{usuario}'},
        select='*,fazenda(nome,dispositivo_id)',
        limite=1,
    )
    return linhas[0] if linhas else None


def inserir_tabela(tabela: str, dados: Dict[str, Any]) -> Dict[str, Any]:
    # POST no PostgREST. 'Prefer: return=representation' devolve a linha criada (com o id gerado).
    validate_supabase_config()
    url = f'{BASE_URL}/{tabela}'
    headers = {**get_supabase_headers(), 'Prefer': 'return=representation'}
    response = requests.post(url, headers=headers, json=dados, timeout=10)
    if response.status_code >= 400:
        detail = response.text[:500]
        raise RuntimeError(f'Erro ao inserir no Supabase: {response.status_code} - {detail}')
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError('Resposta inválida do Supabase') from exc
    if isinstance(data, list):
        return data[0] if data else {}
    return data
