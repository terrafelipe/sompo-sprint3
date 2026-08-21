from unittest.mock import patch

from app import app


def test_eventos():
    client = app.test_client()
    with patch('app.consultar_eventos', return_value=[{'id': 1, 'tipo': 'furto_movimento'}]):
        response = client.get('/eventos?dispositivo=SOMPO-ESP32&dias=7')
    assert response.status_code == 200
    data = response.get_json()
    assert data['total'] == 1
    assert data['dados'][0]['tipo'] == 'furto_movimento'
