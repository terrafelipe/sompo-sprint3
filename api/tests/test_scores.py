from unittest.mock import patch

from app import app
from scores import calcular_scores


EVENTOS = [
    {'tipo': 'furto_movimento', 'severidade': 4},   # furto +40
    {'tipo': 'furto_capo', 'severidade': 2},         # furto +10
    {'tipo': 'chama_detectada', 'severidade': 5},    # incendio +70
]


def test_scores_deterministico():
    # Rodar duas vezes com a mesma entrada devolve exatamente o mesmo resultado.
    a = calcular_scores('SOMPO-ESP32', 7, EVENTOS)
    b = calcular_scores('SOMPO-ESP32', 7, EVENTOS)
    assert a == b


def test_scores_valores_conhecidos():
    r = calcular_scores('SOMPO-ESP32', 7, EVENTOS)
    assert r['score_furto'] == 50            # 40 + 10
    assert r['score_incendio'] == 70
    assert r['classificacao_furto'] == 'MEDIO'
    assert r['classificacao_incendio'] == 'ALTO'
    assert r['eventos_considerados']['total'] == 3


def test_scores_severidade_ausente_usa_padrao():
    # Sem o campo severidade, usa a severidade padrao do tipo (furto_tanque = 3 -> 20).
    r = calcular_scores('SOMPO-ESP32', 7, [{'tipo': 'furto_tanque'}])
    assert r['score_furto'] == 20


def test_scores_sem_eventos():
    r = calcular_scores('SOMPO-ESP32', 7, [])
    assert r['score_furto'] == 0
    assert r['score_incendio'] == 0
    assert r['classificacao_furto'] == 'BAIXO'


def test_scores_sem_import_de_rede():
    # Garante que o modulo e puro: nao importa requests.
    import scores
    assert not hasattr(scores, 'requests')


def test_rota_scores():
    client = app.test_client()
    with patch('app.consultar_eventos', return_value=EVENTOS):
        response = client.get('/scores?dispositivo=SOMPO-ESP32&dias=7')
    assert response.status_code == 200
    data = response.get_json()
    assert data['score_furto'] == 50
    assert data['score_incendio'] == 70
