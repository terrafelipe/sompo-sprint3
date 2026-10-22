"""Calendario proprio do painel (rede isolada), exercitado pelo botao de periodo das Leituras."""
import calendar
from datetime import date, timedelta

import pytest

from tests.ajuda_calendario import abrir_calendario, clicar_dia, ir_para_mes
from tests.test_painel import painel, pw  # noqa: F401
from tests.test_painel_leituras_periodo import _abrir, _servidor, leitura

BTN = '#leiturasPeriodoBtn'


def _preparar(page):
    st = _servidor(page, [([leitura(i) for i in range(5)], False)])
    _abrir(page)
    return st


def _hoje(page):
    return date.fromisoformat(page.evaluate('Calendario.hoje()'))


def _br(d):
    return d.strftime('%d/%m/%Y')


def _mes_mais(d, n, limite=None):
    """Mesmo dia do mes n meses depois (limitado ao ultimo dia do mes e, se vier, a `limite`)."""
    m = d.year * 12 + d.month - 1 + n
    ano, mes = divmod(m, 12)
    mes += 1
    r = date(ano, mes, min(d.day, calendar.monthrange(ano, mes)[1]))
    return min(r, limite) if limite else r


def _aplicar_e_ler(page, st):
    page.locator('#calAplicar').click()
    pw.expect(page.locator('#calendario')).to_be_hidden()
    return st['pedidos'][-1]


def test_hoje_e_o_dia_de_brasilia(painel):
    page, _ = painel
    page.clock.set_fixed_time('2026-10-21T01:30:00Z')       # 22:30 de 20/10 em Brasilia
    assert page.evaluate('Calendario.hoje()') == '2026-10-20'
    page.clock.set_fixed_time('2026-10-21T03:30:00Z')       # 00:30 de 21/10 em Brasilia
    assert page.evaluate('Calendario.hoje()') == '2026-10-21'
    assert 'America/Sao_Paulo' in page.evaluate("fetch('/static/calendario.js').then(r => r.text())")


def test_formatar_e_dd_mm_aaaa(painel):
    page, _ = painel
    assert page.evaluate("Calendario.formatar('2026-09-05')") == '05/09/2026'


def test_dois_cliques_escolhem_o_intervalo_e_aplicar_envia_as_datas(painel):
    page, _ = painel
    st = _preparar(page)
    abrir_calendario(page)
    clicar_dia(page, '2026-09-21')
    clicar_dia(page, '2026-10-05')
    pw.expect(page.locator('#calResumo')).to_contain_text('15 dias')
    pedido = _aplicar_e_ler(page, st)
    pw.expect(page.locator('#leiturasPeriodoTxt')).to_have_text('21/09/2026 até 05/10/2026')
    pw.expect(page.locator('#tabelaTelemetria tr')).to_have_count(5)
    assert (pedido['de'], pedido['ate']) == ('2026-09-21', '2026-10-05')


def test_clique_antes_do_inicio_troca_a_ordem(painel):
    page, _ = painel
    st = _preparar(page)
    abrir_calendario(page)
    clicar_dia(page, '2026-10-10')
    clicar_dia(page, '2026-10-05')
    pedido = _aplicar_e_ler(page, st)
    assert (pedido['de'], pedido['ate']) == ('2026-10-05', '2026-10-10')


@pytest.mark.parametrize('chave', ['hoje', 'ontem', '7', '30', 'mes', 'mespassado', '90'])
def test_atalhos_preenchem_o_intervalo_esperado(painel, chave):
    page, _ = painel
    st = _preparar(page)
    hoje = _hoje(page)
    um = timedelta(days=1)
    primeiro_do_mes = hoje.replace(day=1)
    esperado = {
        'hoje': (hoje, hoje), 'ontem': (hoje - um, hoje - um),
        '7': (hoje - 6 * um, hoje), '30': (hoje - 29 * um, hoje), '90': (hoje - 89 * um, hoje),
        'mes': (primeiro_do_mes, hoje),
        'mespassado': ((primeiro_do_mes - um).replace(day=1), primeiro_do_mes - um),
    }[chave]
    abrir_calendario(page)
    page.locator(f'#calAtalhos [data-atalho="{chave}"]').click()
    pedido = _aplicar_e_ler(page, st)
    assert (pedido['de'], pedido['ate']) == (esperado[0].isoformat(), esperado[1].isoformat())
    pw.expect(page.locator('#leiturasPeriodoTxt')).to_have_text(f'{_br(esperado[0])} até {_br(esperado[1])}')


def test_dias_futuros_ficam_desabilitados(painel):
    page, _ = painel
    _preparar(page)
    amanha = (_hoje(page) + timedelta(days=1)).isoformat()
    abrir_calendario(page)
    ir_para_mes(page, amanha)
    futuro = page.locator(f'#calendario [data-dia="{amanha}"]')
    pw.expect(futuro).to_be_disabled()
    page.evaluate(f"document.querySelector('#calendario [data-dia=\"{amanha}\"]').click()")
    pw.expect(page.locator('#calAplicar')).to_be_disabled()


def test_aplicar_desabilitado_sem_inicio_e_com_so_o_inicio_vale_um_dia(painel):
    page, _ = painel
    st = _preparar(page)
    abrir_calendario(page)
    pw.expect(page.locator('#calAplicar')).to_be_disabled()
    dia = (_hoje(page) - timedelta(days=3)).isoformat()
    clicar_dia(page, dia)
    pw.expect(page.locator('#calAplicar')).to_be_enabled()
    pedido = _aplicar_e_ler(page, st)
    assert pedido['de'] == pedido['ate'] == dia


def test_limpar_apaga_a_selecao_sem_fechar(painel):
    page, _ = painel
    _preparar(page)
    abrir_calendario(page)
    clicar_dia(page, '2026-10-01')
    clicar_dia(page, '2026-10-05')
    page.locator('#calLimpar').click()
    pw.expect(page.locator('#calendario')).to_be_visible()
    pw.expect(page.locator('#calAplicar')).to_be_disabled()
    pw.expect(page.locator('#calResumo')).to_have_text('Escolha a data inicial')


def test_setas_de_mes_e_ano_e_fevereiro_bissexto(painel):
    page, _ = painel
    _preparar(page)
    abrir_calendario(page)
    ir_para_mes(page, '2024-02-01')
    pw.expect(page.locator('#calTitulo')).to_have_text('fevereiro de 2024')
    assert page.locator('#calGrade [data-dia]:not(.fora)').count() == 29      # 2024 e bissexto
    page.locator('#calendario [data-nav="12"]').click()
    pw.expect(page.locator('#calTitulo')).to_have_text('fevereiro de 2025')
    assert page.locator('#calGrade [data-dia]:not(.fora)').count() == 28
    page.locator('#calendario [data-nav="-12"]').click()
    page.locator('#calendario [data-nav="-1"]').click()
    pw.expect(page.locator('#calTitulo')).to_have_text('janeiro de 2024')


def test_esc_fecha_e_devolve_o_foco_ao_botao(painel):
    page, _ = painel
    _preparar(page)
    abrir_calendario(page)
    pw.expect(page.locator(BTN)).to_have_attribute('aria-expanded', 'true')
    page.keyboard.press('Escape')
    pw.expect(page.locator('#calendario')).to_be_hidden()
    pw.expect(page.locator(BTN)).to_be_focused()
    pw.expect(page.locator(BTN)).to_have_attribute('aria-expanded', 'false')


def test_clique_fora_fecha_e_clicar_no_botao_de_novo_tambem(painel):
    page, _ = painel
    _preparar(page)
    abrir_calendario(page)
    page.locator('#tituloView').click()
    pw.expect(page.locator('#calendario')).to_be_hidden()
    abrir_calendario(page)
    page.locator(BTN).click()
    pw.expect(page.locator('#calendario')).to_be_hidden()


def test_teclado_setas_pageup_pagedown_enter(painel):
    page, _ = painel
    _preparar(page)
    abrir_calendario(page)
    hoje, um = _hoje(page), timedelta(days=1)
    foco = lambda: page.evaluate('document.activeElement.dataset.dia')  # noqa: E731
    assert foco() == hoje.isoformat()                       # sem selecao, abre com o foco em hoje
    page.keyboard.press('ArrowLeft')
    assert foco() == (hoje - um).isoformat()
    page.keyboard.press('ArrowUp')
    assert foco() == (hoje - 8 * um).isoformat()
    page.keyboard.press('ArrowRight')
    assert foco() == (hoje - 7 * um).isoformat()
    page.keyboard.press('ArrowDown')
    assert foco() == hoje.isoformat()
    page.keyboard.press('ArrowDown')                         # nao anda para o futuro
    assert foco() == hoje.isoformat()
    page.keyboard.press('PageUp')
    mes_antes = _mes_mais(hoje, -1)
    assert foco() == mes_antes.isoformat()
    page.keyboard.press('PageDown')
    assert foco() == _mes_mais(mes_antes, 1, limite=hoje).isoformat()
    page.keyboard.press('ArrowLeft')
    page.keyboard.press('Enter')                             # escolhe o inicio; o foco continua no calendario
    page.keyboard.press('ArrowRight')
    page.keyboard.press('Enter')
    pw.expect(page.locator('#calResumo')).to_contain_text('2 dias')


def test_trocar_de_maquina_fecha_o_calendario(painel):
    page, _ = painel
    _preparar(page)
    abrir_calendario(page)
    page.select_option('#equipamentoSel', '')
    pw.expect(page.locator('#calendario')).to_be_hidden()


def test_tema_escuro_usa_as_variaveis_do_painel(painel):
    page, _ = painel
    _preparar(page)
    page.evaluate("document.documentElement.dataset.tema = 'escuro'")
    abrir_calendario(page)
    esperado, atual = page.evaluate("""() => {
        const t = document.createElement('div'); t.style.background = 'var(--v-card)'; document.body.appendChild(t);
        const c = getComputedStyle(t).backgroundColor; t.remove();
        return [c, getComputedStyle(document.getElementById('calendario')).backgroundColor];
    }""")
    assert atual == esperado


def test_atalhos_viram_fileira_no_celular_e_coluna_no_desktop(painel):
    page, _ = painel
    _preparar(page)
    abrir_calendario(page)
    direcao = page.evaluate("getComputedStyle(document.getElementById('calAtalhos')).flexDirection")
    assert direcao == ('row' if page.viewport_size['width'] <= 560 else 'column')
