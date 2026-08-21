from unittest.mock import patch

from app import app


def test_telemetria():
    client = app.test_client()
    with patch('app.consultar_telemetria', return_value=[{'id': 1, 'dispositivo_id': 'SOMPO-ESP32'}]):
        response = client.get('/telemetria?dispositivo=SOMPO-ESP32&limite=10')
    assert response.status_code == 200
    data = response.get_json()
    assert data['total'] == 1
    assert len(data['dados']) == 1
