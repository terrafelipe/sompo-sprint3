"""Texto da IA fora do caminho critico: medidores com ia=0 (rapido) e a explicacao da IA
pedida a parte, uma vez por (maquina, periodo) e a cada "Gerar de novo"."""
from urllib.parse import parse_qs, urlparse

from tests.test_painel import painel, pw, nav  # noqa: F401

TEMPLATE = 'Resumo de template do sistema.'
TEXTO_IA = 'Resumo escrito pela IA.'


def _base(**extra):
    return {**dict(score_furto=50, score_incendio=80, classificacao_furto='MEDIO', classificacao_incendio='ALTO',
                   faixas={'medio': 34, 'alto': 67}, pontos_acumulados={'furto': 50, 'incendio': 80},
                   detalhamento={'furto_capo': {'eixo': 'furto', 'quantidade': 2, 'pontos': 50}},
                   justificativa_furto='Justificativa de template.', justificativa_incendio='Incendio de template.',
                   recomendacoes=['Recomendacao de template.'], limitacoes='Texto por template.'), **extra}


def _rotas(page, segurar=True):
    """ia=0 responde na hora; a rota com IA fica presa (atrasada) ate o teste soltar."""
    estado = {'rapidas': 0, 'ia': [], 'presas': [], 'n': 0}

    def responder(r):
        q = parse_qs(urlparse(r.request.url).query)
        estado['n'] += 1
        if q.get('ia') == ['0']:
            estado['rapidas'] += 1
            r.fulfill(json=_base(resumo=TEMPLATE, origem_da_analise='prompt_apenas',
                                 gerado_em=f'2026-09-24T12:00:{estado["n"] % 60:02d}Z'))
            return
        estado['ia'].append(r.request.url)
        if segurar:
            estado['presas'].append(r)
        else:
            r.fulfill(json=_base(resumo=TEXTO_IA, origem_da_analise='llm', gerado_em='2026-09-24T12:00:00Z'))
    page.route('**/relatorio/risco?*', responder)
    return estado


def _soltar_ia(estado, resumo=TEXTO_IA):
    r = estado['presas'].pop(0)
    r.fulfill(json=_base(resumo=resumo, justificativa_furto='Justificativa da IA.', recomendacoes=['Recomendacao da IA.'],
                         origem_da_analise='llm', gerado_em='2026-09-24T12:00:00Z'))


def test_medidores_antes_da_ia_e_texto_da_ia_sem_redesenhar(painel):
    page, state = painel
    estado = _rotas(page)
    page.select_option('#equipamentoSel', '1')
    # (a) medidores e pilulas chegam pelo ia=0 enquanto a IA ainda nao respondeu.
    page.wait_for_selector('#gaugeFurto .arco-valor')
    pw.expect(page.locator('#kpiFurtoPill')).to_have_text('MEDIO')
    pw.expect(page.locator('#classifIncendio')).to_have_text('ALTO')
    pw.expect(page.locator('#riscoResumo')).to_have_text('Gerando explicação da IA…')
    pw.expect(page.locator('#justFurto')).to_have_text('Justificativa de template.')
    assert len(estado['presas']) == 1
    assert 'ia=0' not in estado['ia'][0]
    page.evaluate("document.querySelector('#gaugeFurto .arco-valor').dataset.marca = 'original'")
    # (b) a IA responde: entra o texto, o medidor continua o mesmo elemento.
    _soltar_ia(estado)
    pw.expect(page.locator('#riscoResumo')).to_have_text(TEXTO_IA)
    pw.expect(page.locator('#justFurto')).to_have_text('Justificativa da IA.')
    pw.expect(page.locator('#recs')).to_contain_text('Recomendacao da IA.')
    pw.expect(page.locator('#origemBadge')).to_contain_text('IA')
    assert page.locator('#gaugeFurto .arco-valor').get_attribute('data-marca') == 'original'
    # Refresh depois da IA: o texto da IA fica, sem voltar ao template.
    page.evaluate('carregarRisco()')
    page.wait_for_load_state('networkidle')
    pw.expect(page.locator('#riscoResumo')).to_have_text(TEXTO_IA)
    assert page.locator('#gaugeFurto .arco-valor').get_attribute('data-marca') == 'original'
    assert not state['errors']


def test_refresh_pede_a_ia_uma_vez_e_gerar_de_novo_usa_novo(painel):
    page, state = painel
    nav(page, 'visao')
    estado = _rotas(page, segurar=False)
    page.clock.install()
    page.select_option('#equipamentoSel', '1')
    pw.expect(page.locator('#riscoResumo')).to_have_text(TEXTO_IA)
    # O relogio de 5 s foi criado antes do clock.install: religa sob o relogio falso.
    page.evaluate("pausar('aba'); retomar()")
    page.wait_for_load_state('networkidle')
    # (c) 3 ciclos do refresh de 5 s: so o ia=0 se repete.
    for _ in range(3):
        # Um tick pode cair sobre a carga anterior ainda pendente (carregarTudo reaproveita):
        # o ciclo so conta quando um ia=0 novo sai.
        antes = estado['rapidas']
        for _tick in range(4):
            page.clock.run_for(5100)
            page.wait_for_load_state('networkidle')
            if estado['rapidas'] > antes:
                break
        assert estado['rapidas'] > antes
    assert len(estado['ia']) == 1
    # (d) "Gerar de novo" pede a IA com novo=1.
    with page.expect_request(lambda req: '/relatorio/risco?' in req.url and 'novo=1' in req.url
                             and 'ia=0' not in req.url):
        page.locator('#btnRegerar').click()
    pw.expect(page.locator('#btnRegerar')).to_be_enabled()
    assert len(estado['ia']) == 2
    pw.expect(page.locator('#riscoResumo')).to_have_text(TEXTO_IA)
    assert not state['errors']


def test_ia_de_outro_periodo_e_descartada_e_falha_fica_no_template(painel):
    page, state = painel
    nav(page, 'visao')
    estado = _rotas(page)
    page.select_option('#equipamentoSel', '1')
    pw.expect(page.locator('#riscoResumo')).to_have_text('Gerando explicação da IA…')
    # Troca de periodo no meio: a IA de 7 dias chega depois e e descartada.
    page.locator('[data-periodo="30"]:visible').first.click()
    page.wait_for_function('n => document.querySelectorAll("[data-periodo=\\"30\\"][aria-pressed=\\"true\\"]").length', arg=1)
    page.wait_for_load_state('networkidle')
    assert len(estado['presas']) == 2 and 'dias=30' in estado['ia'][1]
    _soltar_ia(estado, resumo='Texto velho de 7 dias.')
    page.wait_for_load_state('networkidle')
    pw.expect(page.locator('#riscoResumo')).to_have_text('Gerando explicação da IA…')
    # A IA de 30 dias falha: fica o texto de template, sem "indisponivel".
    estado['presas'].pop(0).fulfill(status=502, json={'erro': 'falha'})
    pw.expect(page.locator('#riscoResumo')).to_have_text(TEMPLATE)
    pw.expect(page.locator('#justFurto')).to_have_text('Justificativa de template.')
    pw.expect(page.locator('#secRisco')).not_to_contain_text('indisponível')
    pw.expect(page.locator('#gaugeFurto .arco-valor')).to_have_count(1)
    assert not state['errors']
