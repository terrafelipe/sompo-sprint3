"""Browser regressions with isolated HTTP fixtures; never writes to Supabase.

Install requirements-test.txt and Chromium (or set SOMPO_TEST_BROWSER=msedge).
"""
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest

pw = pytest.importorskip('playwright.sync_api')
HTML = (Path(__file__).parents[1] / 'static/index.html').read_text(encoding='utf-8')
FARMS = [dict(id_fazenda=i, nome=f'Fazenda {i}', fk_cliente_id_cliente=i,
              cliente=dict(nome=f'Cliente {i}')) for i in (1, 2)]


@pytest.fixture(params=[1280, 390], ids=['desktop', 'mobile'])
def painel(request):
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(channel=os.getenv('SOMPO_TEST_BROWSER') or None)
        page = browser.new_page(viewport={'width': request.param, 'height': 900})
        state = dict(role='sompo', fail=set(), posts=[], held=[], hold=None, errors=[],
                     sem_esp32=False, sem_maquinas=False)
        page.on('pageerror', lambda e: state['errors'].append(str(e)))

        def route(r):
            path = urlparse(r.request.url).path
            if urlparse(r.request.url).hostname != 'painel.test':
                r.continue_()
                return
            if path == '/':
                r.fulfill(body=HTML, content_type='text/html')
                return
            if path == state['hold']:
                state['held'].append(r)
                return
            if path in state['fail']:
                r.fulfill(status=502, json={'erro': 'indisponivel'})
                return
            if r.request.method in ('POST', 'PATCH'):
                state['posts'].append((path, r.request.post_data_json))
                if r.request.method == 'PATCH':
                    id = int(path.rsplit('/', 1)[-1])
                    r.fulfill(status=200, json={'ok': True, 'equipamento': {
                        **r.request.post_data_json, 'id_equipamento': id, 'dispositivo_id': f'ESP-{id}'}})
                else:
                    r.fulfill(status=201, json={})
                return
            data = {'dados': []}
            if path == '/me':
                data = dict(role=state['role'], fazenda_id=1, fazenda_nome='Fazenda 1')
            elif path == '/fazendas':
                data = {'dados': FARMS}
            elif path == '/clientes':
                data = {'dados': [dict(id_cliente=i, nome=f'Cliente {i}') for i in (1, 2)]}
            elif path.endswith('/resumo'):
                i = int(path.split('/')[2])
                data = dict(fazenda=FARMS[i-1], equipamentos=[] if state['sem_maquinas'] else [dict(
                    id_equipamento=i, nome=f'Trator {i}', fk_fazenda_id_fazenda=i, fk_cliente_id_cliente=i,
                    dispositivo_id=None if state['sem_esp32'] else f'ESP-{i}', fabricacao='2020-01-02',
                    ultima_manutencao='2026-09-01', valor_segurado='150000.50')])
            elif path == '/saude':
                data = {'api': 'ok', 'banco': 'ok'}
            elif path == '/relatorio/risco':
                data = {'score_furto': 5, 'score_incendio': 10}
            elif path.endswith('.docx'):
                r.fulfill(body=b'PK-test-download', content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                          headers={'Content-Disposition': 'attachment; filename=relatorio.docx'})
                return
            r.fulfill(json=data)

        page.route('**/*', route)
        page.goto('http://painel.test/')
        pw.expect(page.locator('#listaMaquinas')).to_contain_text('Trator 1')
        yield page, state
        assert not state['errors']
        browser.close()


def nav(page, view):
    page.locator(f'[data-nav="{view}"]:visible').click()
    pw.expect(page.locator('#tituloView')).to_have_text({
        'visao': 'Painel da máquina', 'risco': 'Análise de Risco', 'telemetria': 'Telemetria',
        'alertas': 'Alertas', 'maquinas': 'Máquinas', 'operadores': 'Operadores',
        'historico': 'Histórico', 'fazendas': 'Fazendas', 'clientes': 'Clientes', 'usuarios': 'Usuários'}[view])


def captura(page, nome):
    destino = os.getenv('SOMPO_TEST_ARTIFACTS')
    if destino:
        path = Path(destino)
        path.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path / f'{nome}-{page.viewport_size["width"]}.png'), full_page=True)


def test_menus_sem_maquina_refresh_e_word(painel):
    page, state = painel
    for view in ['visao','risco','telemetria','alertas','operadores','historico','fazendas','clientes','usuarios','maquinas']:
        nav(page, view)
        page.evaluate('carregarTudo()')
        assert page.evaluate('viewAtual') == view
        pw.expect(page.locator('#btnBaixar')).to_be_visible()
        pw.expect(page.locator('#btnBaixar')).to_be_disabled()
        if view in ['visao','risco','telemetria','alertas']:
            pw.expect(page.locator('#semMaquina')).to_be_visible()
    nav(page, 'telemetria')
    page.clock.install()
    page.clock.fast_forward(5100)
    assert page.evaluate('viewAtual') == 'telemetria'
    page.locator('#selecionarNoAviso').click()
    page.select_option('#equipamentoSel', '1')
    pw.expect(page.locator('#btnBaixar')).to_be_enabled()
    page.clock.fast_forward(5100)
    assert page.evaluate('[viewAtual,equipamentoSelecionado]') == ['telemetria', 1]
    with page.expect_download(), page.expect_request('**/relatorio/risco.docx?equipamento=1&dias=7'):
        page.locator('#btnBaixar').click()


def test_troca_fazenda_descarta_resposta_antiga(painel):
    page, state = painel
    page.select_option('#equipamentoSel', '1')
    state['hold'] = '/telemetria'
    page.evaluate('void carregarTelemetria()')
    page.wait_for_timeout(100)
    assert state['held']
    page.select_option('#fazendaSel', '2')
    pw.expect(page.locator('#equipamentoSel option')).to_have_count(2)
    pw.expect(page.locator('#equipamentoSel')).to_have_value('')
    assert page.evaluate('equipamentoSelecionado') is None
    for r in state['held']:
        r.fulfill(json={'dados':[{'nivel_risco':'DADO ANTIGO'}]})
    page.wait_for_timeout(100)
    assert 'DADO ANTIGO' not in page.locator('body').inner_text()
    assert page.evaluate('maquinasCache[0].id_equipamento') == 2
    pw.expect(page.locator('#semMaquina')).to_be_visible()


def test_carregamento_e_falha_atrasada(painel):
    page, state = painel
    nav(page, 'historico')
    state['hold'] = '/fazendas/2/resumo'
    page.select_option('#fazendaSel', '2')
    pw.expect(page.locator('#frotaEstado')).to_contain_text('Carregando')
    pw.expect(page.locator('#listaHistorico')).to_have_text('')
    assert state['held']
    page.select_option('#fazendaSel', '1')
    pw.expect(page.locator('#listaHistorico')).to_contain_text('Nenhuma sessão')
    for r in state['held']:
        r.fulfill(status=502, json={'erro':'offline'})
    page.wait_for_timeout(100)
    pw.expect(page.locator('#frotaEstado')).to_have_text('')
    assert page.evaluate('maquinasCache[0].id_equipamento') == 1


def test_permissoes_apos_navegar_e_redimensionar(painel):
    page, state = painel
    state['role'] = 'gestor_fazenda'
    page.reload()
    pw.expect(page.locator('#perfilTxt')).to_contain_text('Gestor')
    for width in [390,1280,390]:
        page.set_viewport_size({'width':width,'height':900})
        for view in ['historico','operadores','telemetria','maquinas']:
            nav(page, view)
            for blocked in ['fazendas','clientes','usuarios']:
                assert page.locator(f'[data-nav="{blocked}"]:visible').count() == 0
        page.evaluate("setView('usuarios')")
        assert page.evaluate('viewAtual') == 'maquinas'


def test_erros_vazio_retry_e_frota_independente(painel):
    page, state = painel
    for view, path, id in [('maquinas','/fazendas/1/resumo','listaMaquinas'),('historico','/operacoes','listaHistorico'),('operadores','/operadores','listaOperadores'),('clientes','/clientes','listaClientes')]:
        state['fail'].add(path)
        nav(page, view)
        pw.expect(page.locator('#'+id)).to_contain_text('indisponível' if view != 'operadores' else 'indisponíveis')
        state['fail'].remove(path)
        page.locator('#'+id+' [data-tentar]').click()
        pw.expect(page.locator('#'+id+' [data-tentar]')).to_have_count(0)
    pw.expect(page.locator('#listaHistorico')).to_contain_text('Nenhuma sessão')
    state['fail'].add('/fazendas/1/resumo')
    nav(page,'maquinas')
    nav(page,'fazendas')
    pw.expect(page.locator('#listaFazendas')).to_contain_text('Fazenda 2')


def test_formulario_detalhe_operador_e_atalho(painel):
    page, state = painel
    page.locator('[data-detalhe-maquina="1"]').click()
    for text in ['Cliente 1','02/01/2020','01/09/2026','150.000,50','ID do equipamento','ID do ESP32']:
        pw.expect(page.locator('#detCorpo')).to_contain_text(text)
    page.locator('#detFechar').click()
    page.locator('#btnNovaMaquina').click()
    for id, value in [('maqNome','Colheitadeira teste'),('maqTipo','Colheitadeira'),('maqModelo','M1'),('maqDispositivo','ESP-TESTE'),('maqFabricacao','2020-01-02'),('maqManutencao','2026-09-01'),('maqValor','150000.50')]:
        page.locator('#'+id).fill(value)
    captura(page, 'formulario')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.locator('#formMaquina button[type=submit]').click()
    pw.expect(page.locator('#formMaquina')).not_to_be_visible()
    payload = state['posts'][-1][1]
    assert payload['fabricacao']=='2020-01-02' and payload['valor_segurado']=='150000.50'
    assert 'fk_cliente_id_cliente' not in payload
    nav(page,'operadores')
    page.locator('#btnNovoOperador').click()
    page.locator('#opNome').fill('Operador teste')
    page.locator('#opUid').fill('AB CD EF 12')
    page.locator('#formOperador button[type=submit]').click()
    pw.expect(page.locator('#formOperador')).not_to_be_visible()
    assert state['posts'][-1][1]['matricula']==''
    nav(page,'fazendas')
    page.locator('[data-faz="1"]').click()
    page.locator('[data-vertelemetria="2"]').click()
    pw.expect(page.locator('#equipamentoSel')).to_have_value('2')
    assert page.evaluate('[viewAtual,dispositivo]') == ['telemetria','ESP-2']
    captura(page, 'telemetria')


def editar_e_salvar(page, id, nome):
    page.locator(f'#listaMaquinas [data-editar-maquina="{id}"]').click()
    pw.expect(page.locator('#formMaquina')).to_be_visible()
    page.locator('#maqNome').fill(nome)
    page.locator('#formMaquina button[type=submit]').click()
    pw.expect(page.locator('#formMaquina')).not_to_be_visible()


def test_editar_maquina(painel):
    page, state = painel
    page.locator('[data-editar-maquina="1"]').click()
    pw.expect(page.locator('#formMaquina')).to_be_visible()
    pw.expect(page.locator('#maqFormTitulo')).to_contain_text('Editar')
    for id, value in [('maqNome','Trator 1'),('maqValor','150000.50'),('maqFabricacao','2020-01-02')]:
        pw.expect(page.locator('#'+id)).to_have_value(value)
    pw.expect(page.locator('#maqFazenda')).to_be_disabled()
    pw.expect(page.locator('#maqDispositivo')).to_be_disabled()
    pw.expect(page.locator('#maqDispositivoAjuda')).to_be_visible()
    page.locator('#maqNome').fill('Trator 1B')
    page.locator('#maqValor').fill('99')
    captura(page, 'editar-maquina')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.locator('#formMaquina button[type=submit]').click()
    pw.expect(page.locator('#formMaquina')).not_to_be_visible()
    path, payload = state['posts'][-1]
    assert path == '/equipamentos/1' and payload['nome'] == 'Trator 1B' and payload['valor_segurado'] == '99'
    assert 'fk_fazenda_id_fazenda' not in payload and 'dispositivo_id' not in payload
    page.locator('#btnNovaMaquina').click()
    pw.expect(page.locator('#maqFormTitulo')).to_have_text('Nova máquina')
    pw.expect(page.locator('#maqNome')).to_have_value('')
    pw.expect(page.locator('#maqFazenda')).to_be_enabled()
    pw.expect(page.locator('#maqDispositivo')).to_be_enabled()
    pw.expect(page.locator('#maqDispositivoAjuda')).not_to_be_visible()


def test_editar_maquina_sem_esp32_e_via_detalhe(painel):
    page, state = painel
    state['sem_esp32'] = True
    page.select_option('#fazendaSel', '2')
    pw.expect(page.locator('#listaMaquinas')).to_contain_text('Trator 2')
    page.locator('[data-detalhe-maquina="2"]').click()
    page.locator('#detCorpo [data-editar-maquina="2"]').click()
    pw.expect(page.locator('#modalDetalhe')).not_to_be_visible()
    pw.expect(page.locator('#formMaquina')).to_be_visible()
    pw.expect(page.locator('#maqDispositivo')).to_be_enabled()
    pw.expect(page.locator('#maqDispositivoAjuda')).not_to_be_visible()
    page.locator('#maqDispositivo').fill('ESP-NOVO')
    page.locator('#formMaquina button[type=submit]').click()
    pw.expect(page.locator('#formMaquina')).not_to_be_visible()
    path, payload = state['posts'][-1]
    assert path == '/equipamentos/2' and payload['dispositivo_id'] == 'ESP-NOVO'
    assert 'fk_fazenda_id_fazenda' not in payload


def test_editar_maquina_selecionada_atualiza_dispositivo(painel):
    page, state = painel
    page.select_option('#equipamentoSel', '1')
    nav(page, 'maquinas')
    editar_e_salvar(page, 1, 'Trator 1C')
    assert state['posts'][-1][0] == '/equipamentos/1'
    assert page.evaluate('[equipamentoSelecionado, dispositivo]') == [1, 'ESP-1']
    pw.expect(page.locator('#listaMaquinas')).to_contain_text('Trator 1')
    pw.expect(page.locator('#equipamentoSel')).to_have_value('1')


def test_selecionar_no_aviso_mantem_aba(painel):
    page, state = painel
    nav(page, 'risco')
    page.locator('#selecionarNoAviso').click()
    # Com appearance: base-select o picker abre e o foco vai para uma <option> dentro do select.
    assert page.evaluate("document.getElementById('equipamentoSel').contains(document.activeElement)")
    assert page.evaluate("document.getElementById('equipamentoSel').matches(':open') || document.getElementById('equipamentoSelWrap').classList.contains('sel-destaque')")
    assert page.evaluate('viewAtual') == 'risco'
    pw.expect(page.locator('#semMaquina')).to_be_visible()
    page.keyboard.press('Escape')
    state['sem_maquinas'] = True
    page.select_option('#fazendaSel', '2')
    pw.expect(page.locator('#resumoFazendaNome')).to_have_text('Fazenda 2')
    nav(page, 'risco')
    page.locator('#selecionarNoAviso').click()
    pw.expect(page.locator('#tituloView')).to_have_text('Máquinas')
    assert page.evaluate('viewAtual') == 'maquinas'
    pw.expect(page.locator('#listaMaquinas')).to_contain_text('Nenhuma máquina')


def test_selects_estilizados(painel):
    page, state = painel
    ids = ['fazendaSel','equipamentoSel','maqFazenda','opFazenda','historicoDias','fzCliente','usRole','usFazenda']
    aparencia = [page.evaluate('id => getComputedStyle(document.getElementById(id)).appearance', id) for id in ids]
    if aparencia[0] != 'base-select':
        pytest.skip('Chromium sem appearance: base-select')
    assert aparencia == ['base-select'] * len(ids)
    assert page.evaluate("getComputedStyle(document.getElementById('equipamentoSel'), '::picker-icon').display") == 'none'
    assert page.evaluate("getComputedStyle(document.getElementById('historicoDias'), '::picker-icon').display") != 'none'
