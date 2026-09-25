"""Cabecalhos de seguranca em toda resposta (clickjacking, sniffing, referrer, CSP, HSTS)."""
from unittest.mock import patch

import pytest

import app


@pytest.mark.parametrize('rota', ['/login', '/saude', '/', '/rota-que-nao-existe'])
def test_cabecalhos_em_toda_resposta(rota):
    with patch('app.PAINEL_SENHA', 'liga-o-login'):
        h = app.app.test_client().get(rota).headers
    assert h['X-Frame-Options'] == 'DENY'
    assert h['X-Content-Type-Options'] == 'nosniff'
    assert h['Referrer-Policy'] == 'same-origin'
    assert 'geolocation=()' in h['Permissions-Policy']
    csp = h['Content-Security-Policy']
    for diretiva in ["default-src 'self'", "frame-ancestors 'none'", "object-src 'none'", "base-uri 'self'",
                     "form-action 'self'", 'https://cdnjs.cloudflare.com', 'https://nominatim.openstreetmap.org']:
        assert diretiva in csp, diretiva
    assert 'cdn.tailwindcss.com' not in csp


def test_hsts_so_com_cookie_seguro():
    with patch('app.COOKIE_SEGURO', True):
        assert 'max-age=' in app.app.test_client().get('/saude').headers['Strict-Transport-Security']
    with patch('app.COOKIE_SEGURO', False):
        assert 'Strict-Transport-Security' not in app.app.test_client().get('/saude').headers
