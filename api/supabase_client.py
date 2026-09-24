from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone

import requests

from config import SUPABASE_URL, SUPABASE_SECRET_KEY, get_supabase_headers, validate_supabase_config


BASE_URL = f'{SUPABASE_URL.rstrip("/")}/rest/v1' if SUPABASE_URL else ''

# Uma sessao so para o processo: reaproveita a conexao TCP+TLS entre consultas. A Lambda
# roda nos EUA e o Supabase em Sao Paulo; conexao nova a cada consulta custava ~3 idas e
# voltas em vez de 1, e cada rota faz de 2 a 5 consultas.
_sessao = requests.Session()


class SupabaseError(RuntimeError):
    def __init__(self, status, codigo=''):
        super().__init__(f'Supabase HTTP {status}: {codigo}')
        self.status = status
        self.codigo = codigo


def _request_json(method: str, table: str, params: Optional[Dict[str, str]] = None, payload: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    validate_supabase_config()
    url = f'{BASE_URL}/{table}'
    headers = get_supabase_headers()
    if method in {'POST', 'PATCH'}:
        headers = {**headers, 'Prefer': 'return=representation'}
    response = _sessao.request(
        method=method,
        url=url,
        headers=headers,
        params=params or {},
        json=payload,
        timeout=10,
    )
    if response.status_code >= 400:
        try:
            codigo = response.json().get('code', '')
        except (ValueError, AttributeError):
            codigo = ''
        raise SupabaseError(response.status_code, codigo)
    if not response.text:
        return []
    try:
        data = response.json()
        return data if isinstance(data, list) else [data]
    except ValueError as exc:
        raise RuntimeError('Resposta inválida do Supabase') from exc


def consultar_tabela(tabela: str, *, filtros: Optional[Dict[str, str]] = None, limite: int = 50, select: str = '*', order: Optional[str] = None, offset: int = 0) -> List[Dict[str, Any]]:
    params: Dict[str, str] = {'select': select}
    if filtros:
        for key, value in filtros.items():
            params[f'{key}'] = value
    if order:
        params['order'] = order
    params['limit'] = str(limite)
    params['offset'] = str(offset)
    return _request_json('GET', tabela, params=params)


def consultar_todos(tabela, *, filtros=None, select='*', order='id.asc'):
    dados = []
    while True:
        pagina = consultar_tabela(tabela, filtros=filtros, select=select,
                                  order=order, limite=500, offset=len(dados))
        dados.extend(pagina)
        if len(pagina) < 500:
            return dados


def consultar_periodo(tabela, filtros, dias, campo='criado_em', order='criado_em.desc,id.desc'):
    agora = datetime.now(timezone.utc)
    return consultar_todos(tabela, filtros={
        **filtros, campo: f'gte.{(agora-timedelta(days=dias)).isoformat()}',
        'and': f'({campo}.lte.{agora.isoformat()})',
    }, order=order)


def atualizar_tabela(tabela, filtros, dados):
    linhas = _request_json('PATCH', tabela, params=filtros, payload=dados)
    return linhas[0] if linhas else {}


def chamar_rpc(nome, payload):
    linhas = _request_json('POST', f'rpc/{nome}', payload=payload)
    return linhas[0] if len(linhas) == 1 else linhas


def consultar_telemetria(dispositivo: str, limite: int = 50) -> List[Dict[str, Any]]:
    filtros = {'dispositivo_id': f'eq.{dispositivo}'}
    return consultar_tabela('telemetria', filtros=filtros, limite=limite, order='criado_em.desc')


def consultar_telemetria_intervalo(dispositivo: str, inicio: datetime, fim: datetime) -> List[Dict[str, Any]]:
    # So as colunas que a linha do tempo usa: 24h de leituras podem ser milhares de linhas.
    return consultar_todos('telemetria', filtros={
        'dispositivo_id': f'eq.{dispositivo}',
        'criado_em': f'gte.{inicio.isoformat()}',
        'and': f'(criado_em.lte.{fim.isoformat()})',
    }, select='criado_em,motor_ligado,nivel_risco', order='criado_em.asc')


def consultar_eventos(dispositivo: str, dias: int = 7) -> List[Dict[str, Any]]:
    return consultar_periodo('eventos', {'dispositivo_id': f'eq.{dispositivo}'}, dias)


def consultar_resumo(dispositivo: str, dias: int = 7) -> List[Dict[str, Any]]:
    hoje = datetime.now(timezone(timedelta(hours=-3))).date()
    filtros = {
        'dispositivo_id': f'eq.{dispositivo}',
        'dia': f'gte.{(hoje-timedelta(days=dias-1)).isoformat()}',
        'and': f'(dia.lte.{hoje.isoformat()})',
    }
    return consultar_todos('resumo_diario', filtros=filtros, order='dia.desc')


# --- Cadastro de negocio (dashboard): clientes e fazendas ---------------------

def consultar_clientes() -> List[Dict[str, Any]]:
    # Traz tambem os dados de contato, para o modal de detalhe do cliente no painel.
    # O dropdown de "dono da fazenda" usa so id+nome; os campos extras nao atrapalham.
    return consultar_tabela('cliente', filtros={'excluido_em': 'is.null'}, select='id_cliente,nome,cnpj,telefone,endereco,email', order='nome.asc', limite=200)


def consultar_fazendas() -> List[Dict[str, Any]]:
    # Embed do PostgREST traz os dados do cliente dono junto (cliente(...)), usados no
    # modal de detalhe da fazenda.
    return consultar_tabela(
        'fazenda',
        filtros={'excluido_em': 'is.null'},
        select='*,cliente(nome,cnpj,telefone,email)',
        order='criado_em.desc',
        limite=200,
    )


def consultar_usuarios() -> List[Dict[str, Any]]:
    # Lista de logins do painel SEM a senha, com o nome da fazenda vinculada embutido.
    return consultar_tabela(
        'usuario',
        filtros={'excluido_em': 'is.null'},
        select='id_usuario,usuario,role,fk_fazenda_id_fazenda,fazenda(nome)',
        order='usuario.asc',
        limite=200,
    )


def consultar_usuario(value):
    linhas = consultar_tabela('usuario', filtros={
        'id_usuario': f'eq.{value}', 'excluido_em': 'is.null'}, limite=1,
        select='id_usuario,usuario,role,criado_em,fk_fazenda_id_fazenda,'
               'fazenda(nome,localizacao,cliente(nome,cnpj,telefone,email))')
    return linhas[0] if linhas else None


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
    response = _sessao.post(url, headers=headers, json=dados, timeout=10)
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
