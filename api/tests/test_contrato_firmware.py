"""Trava o contrato de dados entre firmware, banco e API.

O firmware (C++), o schema (SQL) e o scores.py (Python) compartilham um contrato
que nenhum deles consegue verificar sozinho. Ja aconteceu de divergirem em
silencio: o hardware trocou de sensores e o painel ficou mostrando colunas que
nunca mais teriam valor.

Estes testes leem o .ino como texto e comparam com o .sql e o scores.py. Nao
compilam nada - so garantem que uma chave nova no firmware tenha coluna, e que
um evento novo pontue no score em vez de cair no vazio.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from scores import EIXO_POR_TIPO, SEVERIDADE_PADRAO

RAIZ = Path(__file__).resolve().parents[2]
INO = RAIZ / 'firmware' / 'sompo_hardware_final' / 'sompo_hardware_final.ino'
SQL = RAIZ / 'firmware' / 'sql' / 'preparar_supabase.sql'

pytestmark = pytest.mark.skipif(
    not INO.exists() or not SQL.exists(),
    reason='firmware/ ausente (ex.: imagem Docker, que so copia api/)',
)


def _ino() -> str:
    return INO.read_text(encoding='utf-8', errors='replace')


def _colunas(tabela: str) -> set[str]:
    """Colunas declaradas no create table + as adicionadas por alter table."""
    sql = SQL.read_text(encoding='utf-8', errors='replace')
    corpo = re.search(
        rf'create table if not exists public\.{tabela} \((.*?)\n\);', sql, re.S
    ).group(1)
    cols = {
        m.group(1)
        for linha in corpo.splitlines()
        if (m := re.match(r'\s+(\w+)\s+\S', linha))
    }
    cols |= set(re.findall(
        rf'alter table public\.{tabela} add column if not exists (\w+)', sql
    ))
    cols -= set(re.findall(
        rf'alter table public\.{tabela} drop column if exists (\w+)', sql
    ))
    return cols


def _corpo_funcao(nome: str) -> str:
    """Corpo da funcao, por chaves balanceadas (a assinatura pode ter 2 linhas)."""
    texto = _ino()
    m = re.search(rf'^[ \t]*(?:void|bool)[ \t]+{nome}[ \t]*\([^;{{}}]*\)[ \t]*\{{',
                  texto, re.M | re.S)
    assert m, f'nao achei a definicao de {nome}() no .ino'
    i = m.end() - 1
    nivel = 0
    for j in range(i, len(texto)):
        if texto[j] == '{':
            nivel += 1
        elif texto[j] == '}':
            nivel -= 1
            if nivel == 0:
                return texto[i:j + 1]
    pytest.fail(f'chaves desbalanceadas em {nome}()')


def _chaves_json(trecho: str) -> set[str]:
    r"""Chaves JSON escritas em string C: \"nome\": ..."""
    return set(re.findall(r'\\"(\w+)\\":', trecho))


def _corpos_telemetria() -> str:
    """montar() monta o envelope; cada sensor contribui pela sua telemetria()."""
    texto = _ino()
    trechos = [_corpo_funcao('montar')]
    for m in re.finditer(r'void telemetria\(Json ?&j\)[ \t]*\{', texto):
        i = m.end() - 1
        nivel = 0
        for j in range(i, len(texto)):
            if texto[j] == '{':
                nivel += 1
            elif texto[j] == '}':
                nivel -= 1
                if nivel == 0:
                    trechos.append(texto[i:j + 1])
                    break
    return '\n'.join(trechos)


def test_telemetria_so_manda_coluna_que_existe():
    enviadas = _chaves_json(_corpos_telemetria())
    assert 'dispositivo_id' in enviadas, 'regex nao achou as chaves - desatualizada?'
    sobrando = enviadas - _colunas('telemetria')
    assert not sobrando, (
        f'firmware manda chave sem coluna na tabela telemetria: {sorted(sobrando)}. '
        f'Acrescente a coluna em firmware/sql/preparar_supabase.sql.'
    )


def test_evento_so_manda_coluna_que_existe():
    enviadas = _chaves_json(_corpo_funcao('disparar'))
    # 'detalhes' e jsonb livre: o que esta dentro dele nao vira coluna.
    enviadas -= {'sensor', 'origem', 'vibracao_g', 'limiar_ms2', 'limiar_c'}
    sobrando = enviadas - _colunas('eventos')
    assert not sobrando, (
        f'firmware manda chave sem coluna na tabela eventos: {sorted(sobrando)}'
    )


def test_todo_evento_do_firmware_pontua_no_score():
    tipos = set(re.findall(r'disparar\([^;]*?"(\w+)",\s*\d+,', _ino(), re.S))
    assert tipos, 'nenhum tipo de evento encontrado no .ino - regex desatualizada?'

    sem_eixo = sorted(t for t in tipos if t not in EIXO_POR_TIPO)
    assert not sem_eixo, (
        f'tipo sem eixo em api/scores.py (chega ao banco mas nao pontua): {sem_eixo}'
    )

    sem_padrao = sorted(t for t in tipos if t not in SEVERIDADE_PADRAO)
    assert not sem_padrao, (
        f'tipo sem SEVERIDADE_PADRAO em api/scores.py (vira 0 se o firmware '
        f'omitir o campo): {sem_padrao}'
    )


def test_dispositivo_id_bate_com_o_default_da_api():
    # api/app.py usa 'SOMPO-ESP32' como default de todas as rotas; outro id
    # grava no banco e a API nao acha.
    m = re.search(r'#define DISPOSITIVO_ID "([^"]+)"', _ino())
    assert m and m.group(1) == 'SOMPO-ESP32'


def test_colunas_do_hc_sr04_sumiram_do_painel():
    # O HC-SR04 saiu do hardware: se voltarem ao painel, viram "–" para sempre.
    painel = (RAIZ / 'api' / 'static' / 'index.html').read_text(encoding='utf-8')
    for morta in ('distancia_cm', 'em_movimento'):
        assert morta not in painel, f'{morta} voltou ao dashboard mas nao tem sensor'
