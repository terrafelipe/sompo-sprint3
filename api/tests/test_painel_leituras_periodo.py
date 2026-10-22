"""Últimas leituras por período: De/Até, páginas de 50 e volta às 10 mais recentes (rede isolada)."""
import re
from urllib.parse import parse_qs, urlparse

from tests.test_painel import painel, nav, pw  # noqa: F401


CORTE = '2026-10-05T18:00:00+00:00'   # o que o servidor devolve na 1a pagina


def leitura(i):
    return dict(criado_em=f'2026-10-05T15:{i % 60:02d}:00Z', nivel_risco='BAIXO', temp_escape=40 + i, umidade_ar=50,
                vibracao=0.1, motor_ligado=True, capo_aberto=False, tanque_aberto=False, chama_detectada=False)


def _servidor(page, paginas):
    """Finge o /telemetria com período: paginas = [(linhas, tem_mais), ...]."""
    st = dict(pedidos=[], status=200, falhar_pagina=None, segurar=False, presas=[])

    def corpo(q):
        n = int(q.get('pagina', 1))
        linhas, tem_mais = paginas[n - 1]
        return dict(total=len(linhas), dados=linhas, pagina=n, tem_mais=tem_mais, corte=CORTE)

    def responder(r):
        q = {k: v[0] for k, v in parse_qs(urlparse(r.request.url).query).items()}
        st['pedidos'].append(q)
        if st['segurar']:                    # o teste libera a resposta quando quiser
            st['presas'].append((r, q))
            return
        if st['falhar_pagina'] == int(q.get('pagina', 1)):
            r.fulfill(status=502, json={'erro': 'falha_na_consulta'})
            return
        if st['status'] != 200:
            r.fulfill(status=st['status'], json={'erro': 'periodo_invalido'})
            return
        r.fulfill(json=corpo(q))
    st['corpo'] = corpo
    page.route(re.compile(r'.*/telemetria\?.*\bde=.*'), responder)
    return st


def _abrir(page):
    page.select_option('#equipamentoSel', '1')
    pw.expect(page.locator('#tituloView')).to_have_text('Painel da máquina')
    pw.expect(page.locator('#tabelaTelemetria tr').first).to_be_visible()


def _escolher(page, de, ate):
    page.fill('#leiturasDe', de)
    page.fill('#leiturasAte', ate)
    page.get_by_role('button', name='Ver leituras').click()


def test_periodo_lista_leituras_com_data_e_pagina(painel):
    page, state = painel
    st = _servidor(page, [([leitura(i) for i in range(50)], True), ([leitura(1), leitura(2)], False)])
    _abrir(page)
    assert page.locator('#tabelaTelemetria tr').count() <= 10      # sem período: as 10 mais recentes

    _escolher(page, '2026-09-21', '2026-10-21')
    pw.expect(page.locator('#tabelaTelemetria tr')).to_have_count(50)
    assert (st['pedidos'][-1]['de'], st['pedidos'][-1]['ate'], st['pedidos'][-1]['pagina']) == ('2026-09-21', '2026-10-21', '1')
    pw.expect(page.locator('#tabelaTelemetria tr').first).to_contain_text('05/10/2026')
    pw.expect(page.locator('#tabelaSub')).to_contain_text('21/09/2026 a 21/10/2026')
    pw.expect(page.locator('#leiturasPagina')).to_contain_text('Página 1')
    pw.expect(page.locator('#leiturasAnterior')).to_be_disabled()

    page.locator('#leiturasProxima').click()
    pw.expect(page.locator('#tabelaTelemetria tr')).to_have_count(2)
    assert st['pedidos'][-1]['pagina'] == '2'
    assert 'corte' not in st['pedidos'][0]         # a 1a pagina deixa o servidor escolher o instante (relogio do servidor)
    assert st['pedidos'][-1]['corte'] == CORTE      # as seguintes reenviam o que ele devolveu
    pw.expect(page.locator('#leiturasPagina')).to_contain_text('Página 2')
    pw.expect(page.locator('#leiturasProxima')).to_be_disabled()

    page.locator('#leiturasAnterior').click()
    pw.expect(page.locator('#tabelaTelemetria tr')).to_have_count(50)


def test_a_atualizacao_automatica_nao_apaga_o_periodo(painel):
    page, state = painel
    _servidor(page, [([leitura(i) for i in range(50)], False)])
    _abrir(page)
    _escolher(page, '2026-09-21', '2026-10-21')
    pw.expect(page.locator('#tabelaTelemetria tr')).to_have_count(50)
    page.evaluate('carregarTelemetria()')            # o refresh de 5 s do painel
    page.wait_for_load_state('networkidle')
    pw.expect(page.locator('#tabelaTelemetria tr')).to_have_count(50)


def test_limpar_volta_as_10_mais_recentes(painel):
    page, state = painel
    _servidor(page, [([leitura(i) for i in range(50)], False)])
    # Sem periodo o painel pede 30 e mostra 10: o stub padrao devolve lista vazia, que nao provaria o corte em 10.
    page.route(re.compile(r'.*/telemetria\?.*limite=30.*'),
               lambda r: r.fulfill(json=dict(total=12, dados=[leitura(i) for i in range(12)])))
    _abrir(page)
    antes = page.locator('#tabelaTelemetria tr').count()
    assert antes == 10
    _escolher(page, '2026-09-21', '2026-10-21')
    pw.expect(page.locator('#tabelaTelemetria tr')).to_have_count(50)
    page.get_by_role('button', name='Limpar').click()
    pw.expect(page.locator('#tabelaSub')).to_have_text('As 10 leituras mais recentes da máquina')
    pw.expect(page.locator('#tabelaTelemetria tr')).to_have_count(antes)   # as mesmas 10 de antes, nao uma tabela vazia
    assert page.locator('#tabelaTelemetria').inner_text().count('Carregando') == 0
    pw.expect(page.locator('#leiturasPagina')).to_be_hidden()
    pw.expect(page.locator('#leiturasDe')).to_have_value('')


def test_clique_duplo_em_proxima_avanca_so_uma_pagina(painel):
    page, state = painel
    st = _servidor(page, [([leitura(i) for i in range(50)], True), ([leitura(i) for i in range(50)], True),
                          ([leitura(1)], False)])
    _abrir(page)
    _escolher(page, '2026-09-21', '2026-10-21')
    pw.expect(page.locator('#leiturasPagina')).to_contain_text('Página 1')
    page.locator('#leiturasProxima').dblclick()
    pw.expect(page.locator('#leiturasPagina')).to_contain_text('Página 2')
    page.wait_for_load_state('networkidle')
    pw.expect(page.locator('#tabelaTelemetria tr')).to_have_count(50)
    assert [p['pagina'] for p in st['pedidos']] == ['1', '2']


def test_falha_em_uma_pagina_mostra_aviso_e_deixa_voltar(painel):
    page, state = painel
    st = _servidor(page, [([leitura(i) for i in range(50)], True), ([], False)])
    _abrir(page)
    _escolher(page, '2026-09-21', '2026-10-21')
    pw.expect(page.locator('#tabelaTelemetria tr')).to_have_count(50)
    st['falhar_pagina'] = 2
    page.locator('#leiturasProxima').click()
    pw.expect(page.locator('#leiturasAviso')).to_contain_text('período')
    pw.expect(page.locator('#leiturasPagina')).to_contain_text('Página 2')
    pw.expect(page.locator('#leiturasAnterior')).to_be_enabled()
    st['falhar_pagina'] = None
    page.locator('#leiturasAnterior').click()
    pw.expect(page.locator('#tabelaTelemetria tr')).to_have_count(50)
    pw.expect(page.locator('#leiturasAviso')).to_be_hidden()


def test_trocar_de_maquina_descarta_o_periodo(painel):
    page, state = painel
    _servidor(page, [([leitura(i) for i in range(50)], False)])
    _abrir(page)
    _escolher(page, '2026-09-21', '2026-10-21')
    pw.expect(page.locator('#tabelaTelemetria tr')).to_have_count(50)
    page.select_option('#equipamentoSel', '')
    pw.expect(page.locator('#tabelaSub')).to_have_text('As 10 leituras mais recentes da máquina')
    pw.expect(page.locator('#leiturasNav')).to_be_hidden()
    pw.expect(page.locator('#leiturasDe')).to_have_value('')
    assert page.evaluate('leiturasPeriodo') is None


def test_datas_invertidas_avisam_sem_consultar(painel):
    page, state = painel
    st = _servidor(page, [([], False)])
    _abrir(page)
    _escolher(page, '2026-10-21', '2026-09-21')
    pw.expect(page.locator('#leiturasAviso')).to_contain_text('data final')
    assert st['pedidos'] == []


def test_periodo_sem_leituras_e_erro_do_servidor_viram_frases(painel):
    page, state = painel
    st = _servidor(page, [([], False)])
    _abrir(page)
    _escolher(page, '2026-01-01', '2026-01-02')
    pw.expect(page.locator('#tabelaTelemetria')).to_contain_text('Nenhuma leitura neste período')
    st['status'] = 400
    _escolher(page, '2026-01-01', '2026-01-03')
    pw.expect(page.locator('#leiturasAviso')).to_contain_text('período')


def test_resposta_obsoleta_refaz_a_pagina_em_vez_de_travar_em_carregando(painel):
    page, state = painel
    st = _servidor(page, [([leitura(i) for i in range(50)], False)])
    _abrir(page)
    st['segurar'] = True
    _escolher(page, '2026-09-21', '2026-10-21')
    pw.expect(page.locator('#tabelaTelemetria')).to_contain_text('Carregando')
    page.wait_for_function('() => true')
    for _ in range(50):
        if st['presas']:
            break
        page.wait_for_timeout(100)
    assert st['presas'], 'a consulta do periodo nao saiu'
    page.evaluate('contextoVersao++')      # ex.: outro cadastro foi excluido enquanto a pagina carregava
    st['segurar'] = False
    rota, q = st['presas'].pop(0)
    rota.fulfill(json=st['corpo'](q))      # a resposta chega, mas ja e obsoleta
    pw.expect(page.locator('#tabelaTelemetria tr')).to_have_count(50)
    pw.expect(page.locator('#tabelaTelemetria')).not_to_contain_text('Carregando')


def test_foco_volta_ao_botao_depois_de_trocar_de_pagina(painel):
    page, state = painel
    _servidor(page, [([leitura(i) for i in range(50)], True), ([leitura(i) for i in range(50)], True), ([leitura(1)], False)])
    _abrir(page)
    _escolher(page, '2026-09-21', '2026-10-21')
    pw.expect(page.locator('#leiturasPagina')).to_contain_text('Página 1')
    pw.expect(page.locator('#leiturasProxima')).to_be_enabled()
    page.locator('#leiturasProxima').focus()
    page.keyboard.press('Enter')
    pw.expect(page.locator('#leiturasPagina')).to_contain_text('Página 2')
    pw.expect(page.locator('#leiturasProxima')).to_be_focused()
    page.keyboard.press('Enter')
    pw.expect(page.locator('#leiturasPagina')).to_contain_text('Página 3')
    pw.expect(page.locator('#leiturasProxima')).to_be_disabled()     # ultima pagina: o foco vai para o botao que resta
    pw.expect(page.locator('#leiturasAnterior')).to_be_focused()


def test_foco_sobrevive_a_recarga_por_resposta_obsoleta(painel):
    page, state = painel
    st = _servidor(page, [([leitura(i) for i in range(50)], True), ([leitura(i) for i in range(50)], True)])
    _abrir(page)
    _escolher(page, '2026-09-21', '2026-10-21')
    pw.expect(page.locator('#leiturasProxima')).to_be_enabled()
    st['segurar'] = True
    page.locator('#leiturasProxima').focus()
    page.keyboard.press('Enter')
    for _ in range(50):
        if st['presas']:
            break
        page.wait_for_timeout(100)
    assert st['presas'], 'a consulta da pagina 2 nao saiu'
    page.evaluate('contextoVersao++')      # o contexto muda com a resposta em voo
    st['segurar'] = False
    rota, q = st['presas'].pop(0)
    rota.fulfill(json=st['corpo'](q))      # chega obsoleta: a pagina e pedida de novo
    pw.expect(page.locator('#leiturasPagina')).to_contain_text('Página 2')
    pw.expect(page.locator('#leiturasProxima')).to_be_focused()
