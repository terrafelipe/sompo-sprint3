"""Conexao com o Supabase reaproveitada entre consultas (a Lambda fica nos EUA e o banco em SP:
abrir TCP+TLS a cada consulta custava ~3 idas e voltas em vez de 1)."""
from unittest.mock import MagicMock, patch

import supabase_client as db

# O conftest troca _request_json em todo teste; aqui queremos o original, que usa a sessao.
_REQUEST_JSON = db._request_json


def _resposta(corpo='[{"id": 1}]'):
    r = MagicMock(status_code=200, text=corpo)
    r.json.return_value = [{'id': 1}]
    return r


def test_consultas_usam_a_mesma_sessao_persistente():
    with patch.object(db, 'validate_supabase_config'), patch.object(db, '_request_json', _REQUEST_JSON), \
         patch.object(db._sessao, 'request', return_value=_resposta()) as req, \
         patch('requests.request', side_effect=AssertionError('conexao nova por consulta')):
        db.consultar_tabela('fazenda', limite=1)
        db.consultar_tabela('equipamentos', limite=1)
    assert req.call_count == 2


def test_insercao_usa_a_mesma_sessao():
    r = MagicMock(status_code=201, text='[{"id": 5}]')
    r.json.return_value = [{'id': 5}]
    with patch.object(db, 'validate_supabase_config'), \
         patch.object(db._sessao, 'post', return_value=r) as post, \
         patch('requests.post', side_effect=AssertionError('conexao nova por insercao')):
        assert db.inserir_tabela('ocorrencias', {'titulo': 'x'}) == {'id': 5}
    post.assert_called_once()
