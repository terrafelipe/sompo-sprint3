"""Cores das gravidades 1..5: cada uma diferente (cinza, verde, amarela, laranja, vermelha) nos dois temas."""
import os
from pathlib import Path

from tests.test_painel import painel, pw, nav  # noqa: F401

CORES = {
    'claro': ['#a1a1aa', '#16a34a', '#eab308', '#ea580c', '#dc2626'],
    'escuro': ['#71717a', '#22c55e', '#facc15', '#f97316', '#ef4444'],
}
NOMES = ['Baixa', 'Moderada', 'Média', 'Alta', 'Crítica']
# Um tipo por gravidade (pontos/quantidade cai na faixa de cada uma) para as barras sairem coloridas.
DETALHAMENTO = {
    'furto_adulteracao': dict(eixo='furto', pontos=5, quantidade=1),
    'furto_capo': dict(eixo='furto', pontos=20, quantidade=2),
    'furto_tanque': dict(eixo='furto', pontos=40, quantidade=2),
    'furto_movimento': dict(eixo='furto', pontos=80, quantidade=2),
    'operador_nao_autorizado': dict(eixo='furto', pontos=70, quantidade=1),
}


def _cores(page):
    return page.evaluate("""() => [1,2,3,4,5].map(n =>
        getComputedStyle(document.documentElement).getPropertyValue('--g' + n).trim().toLowerCase())""")


def _print(page, tema):
    """Print do cartao "De onde vem o score" quando SOMPO_TEST_ARTIFACTS aponta uma pasta."""
    if os.getenv('SOMPO_TEST_ARTIFACTS'):
        destino = Path(os.environ['SOMPO_TEST_ARTIFACTS'])
        destino.mkdir(parents=True, exist_ok=True)
        cartao = page.locator('#detFurto').locator('xpath=..')
        cartao.scroll_into_view_if_needed()
        cartao.screenshot(path=str(destino / f'gravidade-{tema}-{page.viewport_size["width"]}.png'), animations='disabled')


def test_gravidades_tem_cores_distintas_nos_dois_temas(painel):
    page, state = painel
    page.route('**/relatorio/risco*', lambda r: r.fulfill(json=dict(
        score_furto=100, score_incendio=0, classificacao_furto='ALTO', classificacao_incendio='BAIXO',
        detalhamento=DETALHAMENTO)))
    page.evaluate("document.documentElement.dataset.tema = 'claro'")
    nav(page, 'visao')
    page.select_option('#equipamentoSel', '1')
    pw.expect(page.locator('#detFurto [data-evidencia]')).to_have_count(5)

    legenda = page.locator('#secRisco [aria-label="Legenda da gravidade"]').first
    pw.expect(legenda.locator('span').first).to_have_text('Gravidade:')
    pw.expect(legenda.locator('span.inline-flex')).to_have_text(NOMES)

    assert _cores(page) == CORES['claro']
    assert len(set(CORES['claro'])) == 5
    _print(page, 'claro')

    page.evaluate("document.documentElement.dataset.tema = 'escuro'")
    assert _cores(page) == CORES['escuro']
    assert len(set(CORES['escuro'])) == 5
    _print(page, 'escuro')
    assert not state['errors']
