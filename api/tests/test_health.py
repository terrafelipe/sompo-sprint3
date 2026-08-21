from unittest.mock import patch

from app import app


def test_saude():
    client = app.test_client()
    with patch('supabase_client.consultar_tabela', return_value=[{'id': 1}]):
        response = client.get('/saude')
    assert response.status_code == 200
    data = response.get_json()
    assert data['api'] == 'ok'
    assert data['banco'] == 'ok'
