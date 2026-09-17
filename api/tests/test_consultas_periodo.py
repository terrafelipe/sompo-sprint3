from unittest.mock import patch
from datetime import datetime
import supabase_client as db


def test_periodo_filtrado_no_servidor_e_paginas_completas():
    chamadas = []
    def query(method, table, params=None, payload=None):
        chamadas.append(params.copy())
        offset = int(params.get('offset', 0))
        return [{'id': i} for i in range(offset, min(offset+500, 1100))]
    with patch.object(db, '_request_json', side_effect=query):
        rows = db.consultar_eventos('ESP-A', 3)
    assert len(rows) == 1100
    assert [r['id'] for r in rows] == list(range(1100))
    assert chamadas[0]['criado_em'].startswith('gte.')
    datetime.fromisoformat(chamadas[0]['criado_em'][4:])
    assert chamadas[-1]['offset'] == '1000'
