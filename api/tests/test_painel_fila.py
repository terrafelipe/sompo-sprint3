"""Fila de requisicoes do painel: no maximo 4 em voo e nova tentativa em HTTP 429/503."""
import time
from urllib.parse import urlparse

from tests.test_painel import painel, pw, nav  # noqa: F401

LINHA_DO_TEMPO = '**/telemetria/linha-do-tempo*'


def _abrir_maquina(page, sem_relogio=False):
    nav(page, 'visao')
    if sem_relogio:
        # Sem a atualizacao de 5 s: so a nova tentativa do getJSON pode recuperar a secao.
        page.evaluate("pausar('manual')")
    page.select_option('#equipamentoSel', '1')


def test_429_passageiro_repete_e_carrega(painel):
    page, state = painel
    chamadas = []

    def rota(r):
        chamadas.append(r.request.url)
        if len(chamadas) == 1:
            r.fulfill(status=429, json={'erro': 'ocupado'})
        else:
            r.fallback()
    page.route(LINHA_DO_TEMPO, rota)
    _abrir_maquina(page, sem_relogio=True)
    pw.expect(page.locator('#linhaTempo')).to_contain_text('Sem leituras desta máquina')
    assert 'indisponível' not in page.locator('#linhaTempo').inner_text()
    assert len(chamadas) >= 2
    pw.expect(page.locator('#avisoConexao')).to_be_hidden()


def test_503_passageiro_tambem_repete(painel):
    page, state = painel
    chamadas = []

    def rota(r):
        chamadas.append(r.request.url)
        if len(chamadas) == 1:
            r.fulfill(status=503, json={'erro': 'ocupado'})
        else:
            r.fallback()
    page.route(LINHA_DO_TEMPO, rota)
    _abrir_maquina(page, sem_relogio=True)
    pw.expect(page.locator('#linhaTempo')).to_contain_text('Sem leituras desta máquina')
    assert len(chamadas) >= 2


def test_429_sempre_mostra_indisponivel_sem_travar_a_fila(painel):
    page, state = painel
    chamadas = []

    def rota(r):
        chamadas.append(r.request.url)
        r.fulfill(status=429, json={'erro': 'ocupado'})
    page.route(LINHA_DO_TEMPO, rota)
    _abrir_maquina(page)
    pw.expect(page.locator('#linhaTempo')).to_contain_text('Linha do tempo indisponível', timeout=8000)
    # 1 tentativa + 2 repeticoes; a faixa "Sem conexao" e so para rede fora ou tempo esgotado.
    assert len(chamadas) == 3
    pw.expect(page.locator('#avisoConexao')).to_be_hidden()
    # As outras secoes carregaram e a fila continua andando depois do esgotamento.
    pw.expect(page.locator('#tabelaTelemetria')).not_to_contain_text('indisponível')
    assert page.evaluate("getJSON('/saude').then(d => d.api)") == 'ok'


def test_outros_status_nao_repetem(painel):
    page, state = painel
    chamadas = []

    def rota(r):
        chamadas.append(r.request.url)
        r.fulfill(status=500, json={'erro': 'falha'})
    page.route(LINHA_DO_TEMPO, rota)
    _abrir_maquina(page)
    pw.expect(page.locator('#linhaTempo')).to_contain_text('Linha do tempo indisponível')
    page.wait_for_timeout(600)
    assert len(chamadas) == 1


def test_no_maximo_quatro_requisicoes_em_voo(painel):
    page, state = painel
    em_voo = []
    pico = 0

    def rota(r):
        u = urlparse(r.request.url)
        if u.hostname != 'painel.test' or u.path == '/':
            r.fallback()
            return
        em_voo.append((time.monotonic(), r))
    page.route('**/*', rota)
    _abrir_maquina(page)
    # Segura cada requisicao ~300 ms e mede quantas ficam abertas ao mesmo tempo.
    fim = time.monotonic() + 4
    atendidas = 0
    while time.monotonic() < fim:
        page.wait_for_timeout(30)
        pico = max(pico, len(em_voo))
        agora = time.monotonic()
        for item in [x for x in em_voo if agora - x[0] >= 0.3]:
            em_voo.remove(item)
            item[1].fallback()
            atendidas += 1
    for _, r in em_voo:
        r.fallback()
    assert atendidas >= 6
    assert pico == 4
    pw.expect(page.locator('#linhaTempo')).to_contain_text('Sem leituras desta máquina')


def test_na_fila_e_obsoleto_sai_sem_fazer_fetch(painel):
    page, state = painel
    urls = []
    page.on('request', lambda req: urls.append(req.url))
    presas = []
    page.route('**/presa*', lambda r: presas.append(r))
    page.evaluate("""() => {
      [1, 2, 3, 4].forEach(i => getJSON('/presa?n=' + i).catch(() => null));
      window.__naFila = getJSON('/na-fila').then(() => 'ok', e => e.obsoleto ? 'obsoleto' : e.message);
    }""")
    page.wait_for_timeout(200)
    assert len(presas) == 4
    page.evaluate('contextoVersao++')
    # Libera as vagas: quem estava na fila acorda, ve que ficou obsoleto e nao busca nada.
    for r in presas:
        r.fulfill(json={})
    assert page.evaluate('window.__naFila') == 'obsoleto'
    assert not any('/na-fila' in u for u in urls)
