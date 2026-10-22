"""Ajudantes dos testes de navegador para escolher datas no calendario proprio do painel."""
from tests.test_painel import pw


def abrir_calendario(page, botao='#leiturasPeriodoBtn'):
    page.locator(botao).click()
    pw.expect(page.locator('#calendario')).to_be_visible()


def ir_para_mes(page, iso):
    """Navega pelas setas ate o mes de `iso` (AAAA-MM-DD) aparecer."""
    alvo = iso[:7]
    for _ in range(300):
        atual = page.locator('#calGrade').get_attribute('data-mes')
        if atual == alvo:
            return
        page.locator('#calendario [data-nav="-1"]' if atual > alvo else '#calendario [data-nav="1"]').click()
    raise AssertionError(f'nao cheguei ao mes {alvo}')


def clicar_dia(page, iso):
    ir_para_mes(page, iso)
    page.locator(f'#calendario [data-dia="{iso}"]:not(.fora)').click()


def escolher_periodo(page, de, ate, botao='#leiturasPeriodoBtn'):
    abrir_calendario(page, botao)
    clicar_dia(page, de)
    clicar_dia(page, ate)
    page.locator('#calAplicar').click()
