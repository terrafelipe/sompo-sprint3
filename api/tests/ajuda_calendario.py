"""Ajudantes dos testes de navegador para escolher datas no calendario proprio do painel."""
import pytest

pw = pytest.importorskip('playwright.sync_api')


def abrir_calendario(page, botao='#leiturasPeriodoBtn'):
    page.locator(botao).click()
    pw.expect(page.locator('#calendario')).to_be_visible()


def ir_para_mes(page, iso):
    """Navega pelas setas (de ano em ano enquanto falta um ano ou mais) ate o mes de `iso` (AAAA-MM-DD)."""
    alvo = iso[:7]
    for _ in range(300):
        atual = page.locator('#calGrade').get_attribute('data-mes')
        if atual == alvo:
            return
        dif = (int(alvo[:4]) * 12 + int(alvo[5:])) - (int(atual[:4]) * 12 + int(atual[5:]))
        passo = 12 if dif >= 12 else -12 if dif <= -12 else 1 if dif > 0 else -1
        page.locator(f'#calendario [data-nav="{passo}"]').click()
    raise AssertionError(f'nao cheguei ao mes {alvo}')


def clicar_dia(page, iso):
    ir_para_mes(page, iso)
    page.locator(f'#calendario [data-dia="{iso}"]:not(.fora)').click()


def escolher_periodo(page, de, ate, botao='#leiturasPeriodoBtn'):
    abrir_calendario(page, botao)
    clicar_dia(page, de)
    clicar_dia(page, ate)
    page.locator('#calAplicar').click()


def escolher_dia(page, botao, iso):
    """Calendario de dia unico: abre pelo botao e escolhe o dia (o clique no dia ja aplica e fecha)."""
    abrir_calendario(page, botao)
    clicar_dia(page, iso)
    pw.expect(page.locator('#calendario')).to_be_hidden()
