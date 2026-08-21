"""Camada de acesso ao LLM: encapsula a chamada ao provedor e decide a ORIGEM
da análise, sempre de forma segura (nunca lança para a rota).

Provedor: Google Gemini (Generative Language API) - tier gratuito.
Chave gratuita em https://aistudio.google.com/apikey

Três origens possíveis (ver plano_final_sprint3.md, passo 4):
  - 'prompt_apenas' : sem LLM_API_KEY -> não chama ninguém, devolve só o sinal.
  - 'llm'           : chave presente e provedor respondeu com JSON válido.
  - 'fallback'      : chave presente mas o provedor falhou (timeout/erro/JSON inválido).

Em todos os casos `analisar_risco` retorna um dict; quem monta o relatório (relatorios.py)
transforma isso em resposta HTTP 200. Trocar de provedor mexe só em `_chamar_provedor`.
"""
from __future__ import annotations

import json
from typing import Any, Dict

import requests

from config import LLM_API_KEY, LLM_MODEL

# Endpoint da Google Generative Language API (Gemini).
URL_BASE = 'https://generativelanguage.googleapis.com/v1beta/models'
TIMEOUT = 20


def _chamar_provedor(prompt: str) -> Dict[str, Any]:
    """Chama o Gemini e devolve o JSON parseado da resposta. Lança em qualquer falha."""
    url = f'{URL_BASE}/{LLM_MODEL}:generateContent'
    response = requests.post(
        url,
        headers={
            'Content-Type': 'application/json',
            'x-goog-api-key': LLM_API_KEY,
        },
        json={
            'contents': [{'parts': [{'text': prompt}]}],
            'generationConfig': {
                'temperature': 0.2,
                # Forca a saida a ser JSON puro (Gemini 1.5+/2.x).
                'responseMimeType': 'application/json',
            },
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    # Estrutura da resposta do Gemini: candidates[0].content.parts[0].text
    texto = data['candidates'][0]['content']['parts'][0]['text']
    return json.loads(texto)   # ValueError se nao vier JSON valido


def analisar_risco(prompt: str) -> Dict[str, Any]:
    """Decide a origem e retorna um dict. Nunca lança."""
    if not LLM_API_KEY:
        return {'origem': 'prompt_apenas'}
    try:
        analise = _chamar_provedor(prompt)
        return {'origem': 'llm', 'analise': analise}
    except Exception as exc:   # rede, timeout, HTTP >=400, JSON invalido, resposta bloqueada
        return {'origem': 'fallback', 'erro': str(exc)}
