"""Browser regressions with isolated HTTP fixtures; never writes to Supabase.

Install requirements-test.txt and Chromium (or set SOMPO_TEST_BROWSER=msedge).
"""
import os
from datetime import date, datetime, timedelta, timezone
import re
from pathlib import Path
from urllib.parse import urlparse

import pytest

pw = pytest.importorskip('playwright.sync_api')
HTML = (Path(__file__).parents[1] / 'static/index.html').read_text(encoding='utf-8')
FARMS = [dict(id_fazenda=i, nome=f'Fazenda {i}', fk_cliente_id_cliente=i, localizacao='Campinas - SP',
              cliente=dict(nome=f'Cliente {i}')) for i in (1, 2)]


@pytest.fixture(params=[1280, 390], ids=['desktop', 'mobile'])
def painel(request):
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(channel=os.getenv('SOMPO_TEST_BROWSER') or None)
        page = browser.new_page(viewport={'width': request.param, 'height': 900})
        state = dict(role='sompo', fail=set(), posts=[], held=[], hold=None, errors=[],
                     sem_esp32=False, sem_maquinas=False, deleted=set(), deletes=[], delete_error=None, manut={}, valor={}, scores={}, coords={}, ocorrencias=[], eventos=[])
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
            if r.request.method == 'DELETE':
                state['deletes'].append(path)
                if state['delete_error']:
                    r.fulfill(status=409, json=state['delete_error'])
                else:
                    state['deleted'].add(path)
                    r.fulfill(json={'ok': True})
                return
            if path.startswith('/ocorrencias') and r.request.method in ('POST', 'PATCH'):
                corpo = r.request.post_data_json
                state['posts'].append((path, corpo))
                if r.request.method == 'POST':
                    oc = {**dict(id_ocorrencia=len(state['ocorrencias']) + 1, status='aberta', criado_em='2026-09-18T12:00:00Z',
                                 fazenda_id=1, fazenda_nome='Fazenda 1', equipamento_nome='Trator 1'), **corpo}
                    state['ocorrencias'].append(oc)
                    r.fulfill(status=201, json={'ok': True, 'ocorrencia': oc})
                else:
                    oc = next(o for o in state['ocorrencias'] if o['id_ocorrencia'] == int(path.rsplit('/', 1)[-1]))
                    oc.update(corpo)
                    r.fulfill(json={'ok': True, 'ocorrencia': oc})
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
                data = {'dados': [{**f, **dict(zip(('latitude', 'longitude'), state['coords'].get(f['id_fazenda'], (None, None))))}
                                  for f in FARMS if f'/fazendas/{f["id_fazenda"]}' not in state['deleted']]}
            elif path == '/clientes':
                data = {'dados': [dict(id_cliente=i, nome=f'Cliente {i}') for i in (1, 2) if f'/clientes/{i}' not in state['deleted']]}
            elif path == '/usuarios':
                data = {'dados': [] if '/usuarios/7' in state['deleted'] else [dict(id_usuario=7, usuario='gestor.teste', role='gestor_fazenda', fazenda=FARMS[0])]}
            elif path == '/usuarios/7':
                data = {'usuario': dict(id_usuario=7, usuario='gestor.teste', role='gestor_fazenda', criado_em='2026-09-01T12:00:00Z', fazenda=FARMS[0])}
            elif path == '/operadores':
                data = {'dados': [] if '/operadores/7' in state['deleted'] else [dict(id_operador=7, nome='Ana', uid='01020304', ativo=True)]}
            elif path == '/resumo':
                # Resumo diario do dispositivo (grafico "Temperatura por dia").
                data = {'dados': [
                    dict(dia='2026-09-17', amostras=40, temp_escape_max=80.5, temp_escape_media=42.0, temp_ambiente_media=24.8),
                    dict(dia='2026-09-18', amostras=35, temp_escape_max=61.0, temp_escape_media=38.2, temp_ambiente_media=25.1)]}
            elif path.endswith('/resumo'):
                i = int(path.split('/')[2])
                data = dict(fazenda=FARMS[i-1], equipamentos=[] if state['sem_maquinas'] or f'/equipamentos/{i}' in state['deleted'] else [dict(
                    id_equipamento=i, nome=f'Trator {i}', fk_fazenda_id_fazenda=i, fk_cliente_id_cliente=i,
                    dispositivo_id=None if state['sem_esp32'] else f'ESP-{i}', fabricacao='2020-01-02',
                    ultima_manutencao=state['manut'].get(i, '2026-09-01'), valor_segurado=state['valor'].get(i, '150000.50'),
                    scores=state['scores'].get(i))])
                data['alertas_recentes'] = [] if not data['equipamentos'] else [dict(
                    id=10 + k, tipo=t, severidade=sev, equipamento_id=i, equipamento_nome=f'Trator {i}',
                    horario_ocorrencia='2026-09-18T12:00:00Z', criado_em='2026-09-18T12:00:00Z')
                    for k, (t, sev) in enumerate([('furto_capo', 2), ('escape_critico', 4)])]
            elif path == '/ocorrencias':
                data = {'dados': state['ocorrencias']}
            elif path == '/ocorrencias/responsaveis':
                data = {'dados': [dict(id_usuario=1, usuario='ana.sompo', role='sompo')]}
            elif path == '/eventos':
                data = {'dados': state['eventos']}
            elif path == '/saude':
                data = {'api': 'ok', 'banco': 'ok'}
            elif path == '/relatorio/risco':
                data = {'score_furto': 5, 'score_incendio': 10}
            elif path.endswith('.pdf'):
                r.fulfill(body=b'%PDF-test-download', content_type='application/pdf',
                          headers={'Content-Disposition': 'attachment; filename=relatorio.pdf'})
                return
            r.fulfill(json=data)

        page.route('**/*', route)
        page.goto('http://painel.test/')
        # O perfil Sompo abre no Inicio (carteira); a fazenda e escolhida pelo cartao.
        page.locator('[data-abrir-fazenda="1"]').click()
        pw.expect(page.locator('#listaMaquinas')).to_contain_text('Trator 1')
        # Abrir a fazenda dispara cargas em paralelo; o teste so comeca com a rede quieta
        # (senao uma resposta tardia sobrescreve o que o teste alterou na pagina).
        page.wait_for_load_state('networkidle')
        yield page, state
        assert not state['errors']
        browser.close()


def nav(page, view):
    page.locator(f'[data-nav="{view}"]:visible').click()
    pw.expect(page.locator('#tituloView')).to_have_text({
        'inicio': 'Início', 'visao': 'Painel da máquina', 'maquinas': 'Máquinas', 'operadores': 'Operadores',
        'historico': 'Histórico', 'ocorrencias': 'Ocorrências', 'manutencao': 'Manutenção', 'exposicao': 'Exposição financeira', 'fazendas': 'Fazendas', 'clientes': 'Clientes',
        'usuarios': 'Usuários'}[view])


def acao(page, seletor):
    """Acoes secundarias ficam no menu ⋯ (popover): abre o menu do item antes de clicar."""
    alvo = page.locator(seletor).first
    if not alvo.is_visible():
        menu = alvo.evaluate("e => e.closest('[popover]')?.id")
        if menu:
            page.locator(f'[popovertarget="{menu}"]').click()
    return alvo


def captura(page, nome):
    destino = os.getenv('SOMPO_TEST_ARTIFACTS')
    if destino:
        path = Path(destino)
        path.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path / f'{nome}-{page.viewport_size["width"]}.png'), full_page=True)


def test_inicio_mostra_carteira_e_abre_a_fazenda(painel):
    page, state = painel
    nav(page, 'inicio')
    pw.expect(page.locator('#barraContexto')).to_be_hidden()
    cards = page.locator('#listaInicio [data-abrir-fazenda]')
    pw.expect(cards).to_have_count(2)
    pw.expect(page.locator('#inicioResumo')).to_contain_text('2 fazendas · 2 máquinas')
    pw.expect(cards.nth(1)).to_contain_text('Fazenda 2')
    page.locator('[data-busca="listaInicio"]').fill('fazenda 2')
    pw.expect(page.locator('#listaInicio [data-abrir-fazenda]:visible')).to_have_count(1)
    page.locator('[data-abrir-fazenda="2"]').click()
    pw.expect(page.locator('#tituloView')).to_have_text('Máquinas')
    pw.expect(page.locator('#listaMaquinas')).to_contain_text('Trator 2')
    assert page.evaluate('String(fazendaSelecionada)') == '2'


def test_menus_sem_maquina_refresh_e_pdf(painel):
    page, state = painel
    # Risco, Alertas e Telemetria agora sao partes do Painel da maquina (visao).
    for view in ['visao','operadores','historico','fazendas','clientes','usuarios','maquinas']:
        nav(page, view)
        page.evaluate('carregarTudo()')
        assert page.evaluate('viewAtual') == view
        pw.expect(page.locator('#btnBaixar')).to_be_visible()
        pw.expect(page.locator('#btnBaixar')).to_be_disabled()
        if view == 'visao':
            pw.expect(page.locator('#semMaquina')).to_be_visible()
    nav(page, 'visao')
    page.clock.install()
    page.clock.fast_forward(5100)
    assert page.evaluate('viewAtual') == 'visao'
    page.select_option('#equipamentoSel', '1')
    pw.expect(page.locator('#btnBaixar')).to_be_enabled()
    page.clock.fast_forward(5100)
    assert page.evaluate('[viewAtual,equipamentoSelecionado]') == ['visao', 1]
    with page.expect_download(), page.expect_request('**/relatorio/risco.pdf?equipamento=1&dias=7'):
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
        for view in ['historico','operadores','visao','maquinas']:
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
    acao(page, '[data-detalhe-maquina="1"]').click()
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
    assert page.evaluate('[viewAtual,dispositivo]') == ['visao','ESP-2']
    captura(page, 'telemetria')


def editar_e_salvar(page, id, nome):
    acao(page, f'#listaMaquinas [data-editar-maquina="{id}"]').click()
    pw.expect(page.locator('#formMaquina')).to_be_visible()
    page.locator('#maqNome').fill(nome)
    page.locator('#formMaquina button[type=submit]').click()
    pw.expect(page.locator('#formMaquina')).not_to_be_visible()


def test_editar_maquina(painel):
    page, state = painel
    acao(page, '#listaMaquinas [data-editar-maquina="1"]').click()
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
    acao(page, '[data-detalhe-maquina="2"]').click()
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


def test_selects_estilizados(painel):
    page, state = painel
    ids = ['fazendaSel','equipamentoSel','maqFazenda','opFazenda','historicoDias','fzCliente','usRole','usFazenda']
    aparencia = [page.evaluate('id => getComputedStyle(document.getElementById(id)).appearance', id) for id in ids]
    if aparencia[0] != 'base-select':
        pytest.skip('Chromium sem appearance: base-select')
    assert aparencia == ['base-select'] * len(ids)
    assert page.evaluate("getComputedStyle(document.getElementById('equipamentoSel'), '::picker-icon').display") == 'none'
    assert page.evaluate("getComputedStyle(document.getElementById('historicoDias'), '::picker-icon').display") != 'none'


def test_nome_longo_maquina_sem_sobrepor_seta(painel):
    page, state = painel
    nome = 'Escavadeira Hidráulica 01'
    page.evaluate('(nome)=>{maquinasCache[0].nome=nome; preencherSeletorMaquinas(maquinasCache)}', nome)
    page.select_option('#equipamentoSel', '1')
    pw.expect(page.locator('#equipamentoSel')).to_have_attribute('title', nome)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    assert page.locator('#equipamentoSel').evaluate('''s=>{
      const text=s.querySelector('selectedcontent'), r=text.getBoundingClientRect();
      const arrow=s.nextElementSibling.getBoundingClientRect();
      return r.right<=arrow.left && text.scrollWidth<=text.clientWidth;
    }''')
    captura(page, 'seletor-nome-completo')
    page.evaluate("maquinasCache[0].nome='Escavadeira '+ 'muito longa '.repeat(12); preencherSeletorMaquinas(maquinasCache)")
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    assert page.locator('#equipamentoSel selectedcontent').evaluate('e=>getComputedStyle(e).textOverflow') == 'ellipsis'


def test_seletores_header_alinhados_e_fazenda_sem_sobrepor_seta(painel):
    page, state = painel
    nome = 'Fazenda Santo Antônio'
    page.locator('#fazendaSel option[value="1"]').evaluate('(o,n)=>o.textContent=n', nome)
    page.select_option('#fazendaSel', '2')
    page.select_option('#fazendaSel', '1')

    larguras = page.evaluate('''()=>['fazendaSelWrap','equipamentoSelWrap']
      .map(id=>document.getElementById(id).getBoundingClientRect().width)''')
    assert abs(larguras[0] - larguras[1]) <= 1
    assert page.locator('#fazendaSel').evaluate('''s=>{
      const text=s.querySelector('selectedcontent');
      if(!text) return false;
      const r=text.getBoundingClientRect(), arrow=s.nextElementSibling.getBoundingClientRect();
      return r.right<=arrow.left && text.scrollWidth<=text.clientWidth;
    }''')
    captura(page, 'seletores-header')


@pytest.mark.parametrize('tipo,view,id', [('equipamentos','maquinas',1), ('operadores','operadores',7),
    ('clientes','clientes',1), ('fazendas','fazendas',1), ('usuarios','usuarios',7)])
def test_excluir_cadastro_confirma_cancela_e_atualiza(painel, tipo, view, id):
    page, state = painel
    if tipo == 'equipamentos':
        page.select_option('#equipamentoSel', '1')
    nav(page, view)
    if tipo == 'clientes':
        page.locator('[data-cli="0"]').click()
    elif tipo == 'fazendas':
        page.locator('[data-faz="0"]').click()
    elif tipo == 'operadores':
        page.locator('[data-op="0"]').click()          # linha abre o detalhe; Excluir fica nele
    elif tipo == 'usuarios':
        page.locator('[data-usuario-detalhe="7"]').click()
    seletor = f'[data-excluir-tipo="{tipo}"][data-excluir-id="{id}"]'
    acao(page, seletor).click()
    pw.expect(page.locator('#confirmarExclusao')).to_be_visible()
    pw.expect(page.locator('#exclusaoDescricao')).to_contain_text('histórico será preservado')
    page.locator('#exclusaoCancelar').click()
    assert not state['deletes']
    acao(page, seletor).click()
    page.locator('#exclusaoConfirmar').click()
    pw.expect(page.locator('#confirmarExclusao')).not_to_be_visible()
    assert state['deletes'] == [f'/{tipo}/{id}']
    pw.expect(page.locator('#cadastroAviso')).to_contain_text('Cadastro excluído')
    pw.expect(page.locator(f'[data-excluir-tipo="{tipo}"][data-excluir-id="{id}"]')).to_have_count(0)
    if tipo == 'equipamentos':
        assert page.evaluate('equipamentoSelecionado') is None
        pw.expect(page.locator('#btnBaixar')).to_be_disabled()
        pw.expect(page.locator('#listaMaquinas')).to_contain_text('Nenhuma máquina')
    if tipo == 'fazendas':
        # Sem escolha automatica: excluida a fazenda aberta, nenhuma fica selecionada
        # (a proxima e escolhida pelo usuario no Inicio ou no seletor).
        pw.expect(page.locator('#fazendaSel')).to_have_value('')
        assert page.evaluate('fazendaSelecionada') is None


def test_exclusao_bloqueada_exibe_dependencias(painel):
    page, state = painel
    state['delete_error'] = {'erro': 'cadastro_com_vinculos', 'dependencias': {'maquinas': 2, 'usuarios': 1}}
    nav(page, 'fazendas')
    page.locator('[data-faz="0"]').click()
    page.locator('[data-excluir-tipo="fazendas"]').click()
    page.locator('#exclusaoConfirmar').click()
    pw.expect(page.locator('#exclusaoErro')).to_contain_text('2 máquinas, 1 usuários')
    pw.expect(page.locator('#confirmarExclusao')).to_be_visible()
    assert not state['deleted']


def test_detalhe_usuario_completo(painel):
    page, state = painel
    nav(page, 'usuarios')
    acao(page, '[data-usuario-detalhe="7"]').click()
    pw.expect(page.locator('#detTitulo')).to_have_text('gestor.teste')
    for texto in ['Fazenda 1', 'Cliente 1', 'Data de cadastro', '01/09/2026', 'Não informado']:
        pw.expect(page.locator('#detCorpo')).to_contain_text(texto)
    pw.expect(page.locator('#detCorpo')).not_to_contain_text('Senha')
    captura(page, 'usuario-detalhes')


def test_excluir_ultima_fazenda_limpa_seletores(painel):
    page, state = painel
    state['deleted'].add('/fazendas/2')
    nav(page, 'fazendas')
    page.locator('[data-faz="0"]').click()
    page.locator('[data-excluir-tipo="fazendas"]').click()
    page.locator('#exclusaoConfirmar').click()
    # Na tela Fazendas a barra de contexto ja fica oculta: espera o sinal da propria
    # exclusao (classe hidden nos seletores), e nao so a invisibilidade.
    pw.expect(page.locator('#fazendaSelWrap')).to_have_class(re.compile(r'\bhidden\b'))
    pw.expect(page.locator('#equipamentoSelWrap')).to_have_class(re.compile(r'\bhidden\b'))
    assert page.evaluate('[fazendaSelecionada,equipamentoSelecionado]') == [None, None]
    nav(page, 'maquinas')
    pw.expect(page.locator('#listaMaquinas')).to_contain_text('Nenhuma fazenda selecionada')


def test_excluir_erro_e_envio_unico(painel):
    page, state = painel
    nav(page, 'operadores')
    state['fail'].add('/operadores/7')
    page.locator('[data-op="0"]').click()
    page.locator('[data-excluir-tipo="operadores"]').click()
    page.locator('#exclusaoConfirmar').click()
    pw.expect(page.locator('#exclusaoErro')).to_contain_text('Não foi possível excluir')
    pw.expect(page.locator('#exclusaoConfirmar')).to_be_enabled()
    state['fail'].clear()
    state['hold'] = '/operadores/7'
    page.locator('#exclusaoConfirmar').click()
    pw.expect(page.locator('#exclusaoConfirmar')).to_be_disabled()
    page.keyboard.press('Escape')
    pw.expect(page.locator('#confirmarExclusao')).to_be_visible()
    page.evaluate('confirmarExclusao()')
    assert len(state['held']) == 1
    state['deleted'].add('/operadores/7')
    state['held'][0].fulfill(json={'ok': True})
    pw.expect(page.locator('#confirmarExclusao')).not_to_be_visible()


def test_gestor_abre_no_inicio_da_propria_fazenda(painel):
    page, state = painel
    state['role'] = 'gestor_fazenda'
    page.reload()
    pw.expect(page.locator('#tituloView')).to_have_text('Início')
    pw.expect(page.locator('#inicioGestor')).to_be_visible()
    assert page.locator('#inicioCarteira').is_hidden()
    pw.expect(page.locator('#gMaquinas')).to_have_text('1')
    pw.expect(page.locator('#gMaquinasLista [data-g-maquina]')).to_have_count(1)
    pw.expect(page.locator('#gAlertasLista [data-g-alerta]')).to_have_count(2)
    # O alerta abre o painel da maquina dele; a linha da maquina tambem.
    page.locator('#gAlertasLista [data-g-alerta]').first.click()
    pw.expect(page.locator('#tituloView')).to_have_text('Painel da máquina')
    assert page.evaluate('equipamentoSelecionado') == 1
    nav(page, 'inicio')
    page.locator('#gMaquinasLista [data-g-maquina="1"]').click()
    pw.expect(page.locator('#tituloView')).to_have_text('Painel da máquina')
    assert not state['errors']


def test_manutencao_ordena_por_urgencia_e_edita_maquina_de_outra_fazenda(painel):
    page, state = painel
    hoje = date.today()
    # Regra: proxima = ultima + 180 dias. Trator 1 vence em 10 dias; Trator 2 venceu ha 20.
    state['manut'] = {1: (hoje - timedelta(days=170)).isoformat(), 2: (hoje - timedelta(days=200)).isoformat()}
    nav(page, 'manutencao')
    linhas = page.locator('#listaManutencao [data-manut]')
    pw.expect(linhas).to_have_count(2)
    pw.expect(linhas.nth(0)).to_contain_text('Trator 2')
    pw.expect(linhas.nth(0)).to_contain_text('Vencida')
    pw.expect(linhas.nth(1)).to_contain_text('Trator 1')
    pw.expect(linhas.nth(1)).to_contain_text('Vence em até 30 dias')
    pw.expect(page.locator('[data-section="manutencao"]')).to_contain_text('180 dias')
    # Detalhe -> Editar: a maquina e da Fazenda 2, entao o painel troca de fazenda antes do formulario.
    linhas.nth(0).click()
    pw.expect(page.locator('#detTitulo')).to_have_text('Trator 2')
    page.locator('#detCorpo [data-editar-maquina]').click()
    pw.expect(page.locator('#maqNome')).to_have_value('Trator 2')
    assert page.evaluate('[viewAtual, String(fazendaSelecionada)]') == ['maquinas', '2']
    assert not state['errors']


def test_manutencao_do_gestor_so_tem_a_fazenda_dele(painel):
    page, state = painel
    state['role'] = 'gestor_fazenda'
    state['manut'] = {1: None}
    page.reload()
    nav(page, 'manutencao')
    pw.expect(page.locator('#listaManutencao [data-manut]')).to_have_count(1)
    pw.expect(page.locator('#listaManutencao')).to_contain_text('Sem registro')
    assert page.locator('#listaManutencao th', has_text='Fazenda').count() == 0


def test_exposicao_soma_valor_e_separa_risco_alto(painel):
    page, state = painel
    state['scores'] = {1: dict(score_furto=80, score_incendio=0), 2: dict(score_furto=10, score_incendio=0)}
    state['valor'] = {2: '50000'}
    nav(page, 'exposicao')
    pw.expect(page.locator('#xTotal')).to_have_attribute('title', re.compile(r'200\.000,50'))
    pw.expect(page.locator('#xAlto')).to_have_attribute('title', re.compile(r'150\.000,50'))
    pw.expect(page.locator('#xAltoPct')).to_have_text('75%')
    linhas = page.locator('#listaExposicao [data-linha]')
    pw.expect(linhas).to_have_count(2)
    pw.expect(linhas.nth(0)).to_contain_text('Fazenda 1')
    pw.expect(linhas.nth(0)).to_contain_text('ALTO')
    pw.expect(page.locator('#xFaixas [data-faixa]')).to_have_count(2)
    assert not state['errors']


def test_exposicao_do_gestor_e_por_maquina_e_conta_sem_valor(painel):
    page, state = painel
    state['role'] = 'gestor_fazenda'
    state['valor'] = {1: None}
    page.reload()
    nav(page, 'exposicao')
    pw.expect(page.locator('#xSemValor')).to_have_text('1')
    pw.expect(page.locator('#listaExposicao')).to_contain_text('Trator 1')
    assert page.locator('#listaExposicao th', has_text='Fazenda').count() == 0


def _mapa_offline(page):
    # Tiles e geocodificacao simulados: o teste nao depende dos servidores publicos do OSM.
    page.route('**/tile.openstreetmap.org/**', lambda r: r.fulfill(status=204))
    page.route('**/nominatim.openstreetmap.org/**', lambda r: r.fulfill(
        json=[dict(lat='-22.9056', lon='-47.0608', display_name='Campinas, São Paulo, Brasil')]))


def test_mapa_da_carteira_mostra_pinos_e_abre_a_fazenda(painel):
    page, state = painel
    _mapa_offline(page)
    state['coords'] = {1: (-22.7253, -47.6492)}
    nav(page, 'inicio')
    page.locator('[data-modo-inicio="mapa"]').click()
    pw.expect(page.locator('#mapaCarteira path.leaflet-interactive')).to_have_count(1)
    pw.expect(page.locator('#semLocalizacao')).to_contain_text('Fazenda 2')
    page.locator('#mapaCarteira path.leaflet-interactive').click()
    pw.expect(page.locator('.leaflet-popup')).to_contain_text('Fazenda 1')
    page.locator('.leaflet-popup [data-abrir-fazenda]').click()
    pw.expect(page.locator('#tituloView')).to_have_text('Máquinas')
    assert page.evaluate('String(fazendaSelecionada)') == '1'
    assert not state['errors']


def test_localizacao_da_fazenda_busca_cidade_e_salva(painel):
    page, state = painel
    _mapa_offline(page)
    nav(page, 'inicio')
    page.locator('[data-modo-inicio="mapa"]').click()
    page.locator('#semLocalizacao [data-localizar-fazenda="2"]').click()
    page.locator('#detCorpo [data-buscar-cidade]').click()
    pw.expect(page.locator('#fzLat')).to_have_value('-22.905600')
    pw.expect(page.locator('#fzCoordAchado')).to_contain_text('Campinas')
    page.locator('#detCorpo [data-salvar-coord]').click()
    pw.expect(page.locator('#fzCoordMsg')).to_contain_text('salva')
    assert ('/fazendas/2', {'latitude': -22.9056, 'longitude': -47.0608}) in state['posts']
    # Sem a migracao no Supabase a API responde 409: a tela diz o que falta.
    page.route('**/fazendas/2', lambda r: r.fulfill(status=409, json={'erro': 'migracao_pendente'})
               if r.request.method == 'PATCH' else r.fallback())
    page.locator('#detCorpo [data-salvar-coord]').click()
    pw.expect(page.locator('#fzCoordMsg')).to_contain_text('mapa_ocorrencias.sql')
    assert not state['errors']


def _ocorrencia(i, titulo, status, **extra):
    return dict(id_ocorrencia=i, titulo=titulo, status=status, fazenda_id=1, fazenda_nome='Fazenda 1',
                equipamento_id=1, equipamento_nome='Trator 1', tipo='furto_capo', criado_em='2026-09-18T12:00:00Z', **extra)


def test_ocorrencias_quadro_move_e_edita(painel):
    page, state = painel
    state['ocorrencias'] = [_ocorrencia(1, 'Capô aberto', 'aberta'), _ocorrencia(2, 'Cerca', 'em_verificacao')]
    nav(page, 'ocorrencias')
    pw.expect(page.locator('[data-coluna="aberta"] [data-oc]')).to_have_count(1)
    pw.expect(page.locator('[data-coluna="em_verificacao"] [data-oc]')).to_have_count(1)
    pw.expect(page.locator('[data-contador-ocorr]:visible')).to_have_text('2')
    page.locator('[data-oc="1"] [data-mover="resolvida"]').click()
    pw.expect(page.locator('[data-coluna="resolvida"] [data-oc="1"]')).to_have_count(1)
    assert ('/ocorrencias/1', {'status': 'resolvida'}) in state['posts']
    pw.expect(page.locator('[data-contador-ocorr]:visible')).to_have_text('1')
    # Detalhe: responsavel e nota.
    page.locator('[data-oc="2"] [data-abrir-oc]').click()
    page.locator('#ocResponsavel').select_option('1')
    page.locator('#ocNota').fill('Cerca refeita')
    page.locator('#detCorpo [data-salvar-oc]').click()
    pw.expect(page.locator('#ocMsg')).to_contain_text('salva')
    assert ('/ocorrencias/2', {'status': 'em_verificacao', 'responsavel_id': 1, 'nota': 'Cerca refeita'}) in state['posts']
    assert not state['errors']


def test_alerta_vira_ocorrencia_e_relato_manual(painel):
    page, state = painel
    agora = datetime.now(timezone.utc).isoformat()
    state['eventos'] = [dict(id=77, dispositivo_id='ESP-1', tipo='furto_capo', severidade=2, criado_em=agora)]
    page.select_option('#equipamentoSel', '1')
    page.locator('#eventos [data-ev]').first.click()
    page.locator('#mevAcoes [data-abrir-ocorrencia]').click()
    pw.expect(page.locator('#mevAcoes')).to_contain_text('Ocorrência aberta')
    assert ('/ocorrencias', {'equipamento_id': 1, 'evento_id': 77, 'tipo': 'furto_capo', 'titulo': 'Capô aberto'}) in state['posts']
    page.locator('#mevFechar').click()
    nav(page, 'ocorrencias')
    page.locator('#btnNovaOcorrencia').click()
    page.locator('#ocFazendaForm').select_option('2')
    page.locator('#ocTitulo').fill('Cerca quebrada')
    page.locator('#formOcorrencia [type="submit"]').click()
    pw.expect(page.locator('[data-coluna="aberta"] [data-oc]')).to_have_count(2)
    assert ('/ocorrencias', {'fazenda_id': 2, 'equipamento_id': None, 'titulo': 'Cerca quebrada', 'descricao': ''}) in state['posts']
    assert not state['errors']


def test_ocorrencias_sem_migracao_avisa(painel):
    page, state = painel
    page.route('**/ocorrencias', lambda r: r.fulfill(status=409, json={'erro': 'migracao_pendente'}))
    nav(page, 'ocorrencias')
    pw.expect(page.locator('#ocAviso')).to_contain_text('mapa_ocorrencias.sql')
    assert not state['errors']
