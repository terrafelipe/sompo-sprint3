"""Calendario proprio do painel (rede isolada), exercitado pelo botao de periodo das Leituras."""
import calendar
import re
from datetime import date, timedelta

import pytest

from tests.ajuda_calendario import abrir_calendario, clicar_dia, escolher_dia, ir_para_mes
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


def test_hoje_e_o_dia_de_brasilia_mesmo_com_o_navegador_em_outro_fuso(painel):
    page, _ = painel
    cdp = page.context.new_cdp_session(page)
    cdp.send('Emulation.setTimezoneOverride', {'timezoneId': 'Asia/Tokyo'})
    page.clock.set_fixed_time('2026-10-21T01:30:00Z')       # 22:30 de 20/10 em Brasilia, 10:30 de 21/10 em Toquio
    assert page.evaluate("new Date().toLocaleDateString('sv-SE')") == '2026-10-21'   # o navegador ve o dia de Toquio
    assert page.evaluate('Calendario.hoje()') == '2026-10-20'                         # o calendario ve o de Brasilia
    page.clock.set_fixed_time('2026-10-21T03:30:00Z')       # 00:30 de 21/10 em Brasilia
    assert page.evaluate('Calendario.hoje()') == '2026-10-21'
    cdp.send('Emulation.setTimezoneOverride', {'timezoneId': ''})


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
    page.evaluate('limparMaquina()')        # o caminho da troca de maquina/fazenda, sem passar por setView
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


# ---------- calendario de dia unico (cadastro de maquina) ----------

def _nova_maquina(page):
    page.locator('#btnNovaMaquina').click()
    pw.expect(page.locator('#formMaquina')).to_be_visible()


def test_dia_unico_escolhe_com_um_clique_e_fecha(painel):
    page, _ = painel
    _nova_maquina(page)
    pw.expect(page.locator('#maqFabricacaoBtn .txt')).to_have_text('Escolher data')
    abrir_calendario(page, '#maqFabricacaoBtn')
    pw.expect(page.locator('#calendario')).to_have_class(re.compile(r'unico'))
    pw.expect(page.locator('#calAplicar')).to_be_hidden()            # dia unico: sem Aplicar
    pw.expect(page.locator('#calAtalhos')).to_be_hidden()            # e sem atalhos de periodo
    dia = (_hoje(page) - timedelta(days=3)).isoformat()
    clicar_dia(page, dia)
    pw.expect(page.locator('#calendario')).to_be_hidden()
    pw.expect(page.locator('#maqFabricacao')).to_have_value(dia)
    pw.expect(page.locator('#maqFabricacaoBtn .txt')).to_have_text(f'{dia[8:]}/{dia[5:7]}/{dia[:4]}')
    pw.expect(page.locator('#maqFabricacaoBtn')).to_be_focused()     # o foco volta ao botao


def test_dia_unico_nao_aceita_data_futura(painel):
    page, _ = painel
    _nova_maquina(page)
    amanha = (_hoje(page) + timedelta(days=1)).isoformat()
    abrir_calendario(page, '#maqManutencaoBtn')
    ir_para_mes(page, amanha)
    pw.expect(page.locator(f'#calendario [data-dia="{amanha}"]')).to_be_disabled()
    page.evaluate(f"document.querySelector('#calendario [data-dia=\"{amanha}\"]').click()")
    pw.expect(page.locator('#calendario')).to_be_visible()
    pw.expect(page.locator('#maqManutencao')).to_have_value('')


def test_editar_maquina_mostra_as_datas_gravadas_e_grava_a_nova(painel):
    page, state = painel
    from tests.test_painel import acao
    acao(page, '#listaMaquinas [data-editar-maquina="1"]').click()
    pw.expect(page.locator('#formMaquina')).to_be_visible()
    pw.expect(page.locator('#maqFabricacaoBtn .txt')).to_have_text('02/01/2020')
    pw.expect(page.locator('#maqManutencaoBtn .txt')).to_have_text('01/09/2026')
    pw.expect(page.locator('#maqFabricacao')).to_have_value('2020-01-02')
    nova = (_hoje(page) - timedelta(days=1)).isoformat()
    escolher_dia(page, '#maqManutencaoBtn', nova)
    page.locator('#formMaquina button[type=submit]').click()
    pw.expect(page.locator('#formMaquina')).not_to_be_visible()
    payload = state['posts'][-1][1]
    assert payload['fabricacao'] == '2020-01-02' and payload['ultima_manutencao'] == nova


def test_nova_maquina_depois_de_editar_limpa_as_datas(painel):
    page, _ = painel
    from tests.test_painel import acao
    acao(page, '#listaMaquinas [data-editar-maquina="1"]').click()
    pw.expect(page.locator('#maqFabricacao')).to_have_value('2020-01-02')
    page.locator('#maqCancelar').click() if page.locator('#maqCancelar').count() else page.evaluate('fecharFormMaquina()')
    page.locator('#btnNovaMaquina').click()
    pw.expect(page.locator('#maqFabricacao')).to_have_value('')       # form.reset() nao limpa campo oculto
    pw.expect(page.locator('#maqManutencao')).to_have_value('')
    pw.expect(page.locator('#maqFabricacaoBtn .txt')).to_have_text('Escolher data')
    pw.expect(page.locator('#maqManutencaoBtn .txt')).to_have_text('Escolher data')


def test_calendario_acompanha_o_botao_ao_rolar_a_pagina(painel):
    page, _ = painel
    _nova_maquina(page)
    abrir_calendario(page, '#maqFabricacaoBtn')
    antes = page.evaluate("document.getElementById('calendario').getBoundingClientRect().top")
    page.evaluate("window.scrollBy(0, 40)")
    page.wait_for_function("() => document.getElementById('calendario').getBoundingClientRect().top === document.getElementById('maqFabricacaoBtn').getBoundingClientRect().bottom + 6")
    pw.expect(page.locator('#calendario')).to_be_visible()
    depois = page.evaluate("document.getElementById('calendario').getBoundingClientRect().top")
    assert depois == page.evaluate("document.getElementById('maqFabricacaoBtn').getBoundingClientRect().bottom") + 6
    assert antes != depois or page.evaluate('window.scrollY') == 0     # so compara se a pagina de fato rolou


# ---------- achados da revisao final ----------

def test_intervalo_maior_que_1_ano_fica_desabilitado_e_o_resumo_explica(painel):
    page, _ = painel
    st = _preparar(page)
    ini = _hoje(page) - timedelta(days=10)
    longe = ini - timedelta(days=366)           # 366 dias de diferenca: o servidor recusaria (limite de 365)
    no_limite = ini - timedelta(days=365)
    abrir_calendario(page)
    clicar_dia(page, ini.isoformat())
    # o ponteiro segue sobre o dia clicado: o hover no proprio inicio nao pode virar um intervalo de 1 dia
    page.locator(f'#calendario [data-dia="{ini.isoformat()}"]:not(.fora)').hover()
    pw.expect(page.locator('#calResumo')).to_contain_text('máximo de 1 ano')
    ir_para_mes(page, longe.isoformat())
    pw.expect(page.locator(f'#calendario [data-dia="{longe.isoformat()}"]:not(.fora)')).to_be_disabled()
    page.evaluate(f"document.querySelector('#calendario [data-dia=\"{longe.isoformat()}\"]:not(.fora)').click()")
    pw.expect(page.locator('#calAplicar')).to_be_enabled()   # continua com so o inicio escolhido
    clicar_dia(page, no_limite.isoformat())                  # exatamente 365 dias: vale
    pedido = _aplicar_e_ler(page, st)
    assert (pedido['de'], pedido['ate']) == (no_limite.isoformat(), ini.isoformat())


def test_dia_unico_limpar_apaga_a_data_do_cadastro(painel):
    page, state = painel
    from tests.test_painel import acao
    acao(page, '#listaMaquinas [data-editar-maquina="1"]').click()
    pw.expect(page.locator('#maqFabricacao')).to_have_value('2020-01-02')
    abrir_calendario(page, '#maqFabricacaoBtn')
    page.locator('#calLimpar').click()
    pw.expect(page.locator('#calendario')).to_be_hidden()
    pw.expect(page.locator('#maqFabricacao')).to_have_value('')
    pw.expect(page.locator('#maqFabricacaoBtn .txt')).to_have_text('Escolher data')
    page.locator('#formMaquina button[type=submit]').click()
    pw.expect(page.locator('#formMaquina')).not_to_be_visible()
    assert state['posts'][-1][1]['fabricacao'] == ''


def test_trocar_de_tela_pelo_teclado_fecha_o_calendario(painel):
    page, _ = painel
    _preparar(page)
    abrir_calendario(page)
    page.evaluate("setView('maquinas')")        # o que a paleta (Ctrl+K) faz: sem clique fora
    pw.expect(page.locator('#calendario')).to_be_hidden()


def test_redimensionar_a_janela_nao_fecha_o_calendario(painel):
    # No celular a barra de endereco que some ao rolar dispara resize; o calendario nao pode perder a selecao.
    page, _ = painel
    _preparar(page)
    abrir_calendario(page)
    clicar_dia(page, '2026-10-01')
    tamanho = page.viewport_size
    page.set_viewport_size({'width': tamanho['width'], 'height': tamanho['height'] - 40})
    page.wait_for_timeout(200)
    pw.expect(page.locator('#calendario')).to_be_visible()
    pw.expect(page.locator('#calResumo')).to_contain_text('1 out')
