"""Mapa da fazenda (Inicio da Sompo > Mapa > Fazenda): satelite/ruas, cerca ilustrativa e maquinas."""
from tests.test_painel import painel, pw, nav  # noqa: F401


def _tiles_offline(page):
    # Tiles e geocodificacao simulados: o teste nao depende dos servidores publicos.
    page.route('**/tile.openstreetmap.org/**', lambda r: r.fulfill(status=204))
    page.route('**/server.arcgisonline.com/**', lambda r: r.fulfill(status=204))
    page.route('**/nominatim.openstreetmap.org/**', lambda r: r.fulfill(
        json=[dict(lat='-22.9056', lon='-47.0608', display_name='Campinas, São Paulo, Brasil')]))


def _abrir_mapa_fazenda(page, fazenda):
    nav(page, 'inicio')
    page.locator('[data-modo-inicio="mapa"]').click()
    page.locator('[data-modo-mapa="fazenda"]').click()
    pw.expect(page.locator('[data-modo-mapa="fazenda"]')).to_have_attribute('aria-pressed', 'true')
    page.locator('#mapaFazendaSel').select_option(str(fazenda))


def test_mapa_da_fazenda_mostra_cerca_sede_e_camadas(painel):
    page, state = painel
    _tiles_offline(page)
    state['coords'] = {1: (-22.7253, -47.6492)}
    _abrir_mapa_fazenda(page, 1)
    mapa = page.locator('#mapaFazenda')
    # Cerca (L.circle) + pino da sede (circleMarker): dois paths interativos.
    pw.expect(mapa.locator('path.leaflet-interactive')).to_have_count(2)
    pw.expect(mapa.locator('.leaflet-control-layers')).to_contain_text('Satélite')
    pw.expect(mapa.locator('.leaflet-control-layers')).to_contain_text('Ruas')
    pw.expect(mapa.locator('.leaflet-control-attribution')).to_contain_text('Esri, Maxar, Earthstar Geographics')
    pw.expect(mapa).to_contain_text('Cerca ilustrativa (1 km)')
    pw.expect(mapa).to_contain_text('o ESP32 ainda não envia GPS')
    # Satelite e o padrao; o filtro escuro so vale para a camada de ruas.
    pw.expect(mapa.locator('.mf-satelite')).to_have_count(1)
    pw.expect(mapa.locator('.mf-ruas')).to_have_count(0)
    # Trocar para Ruas.
    mapa.locator('.leaflet-control-layers label', has_text='Ruas').click()
    pw.expect(mapa.locator('.mf-ruas')).to_have_count(1)
    pw.expect(mapa.locator('.mf-satelite')).to_have_count(0)
    # A sede abre o popup com o nome.
    mapa.locator('path.leaflet-interactive').last.click()
    pw.expect(mapa.locator('.leaflet-popup')).to_contain_text('Fazenda 1')
    # O refresh de 5 s reaproveita o mesmo mapa (nao recria nem pisca).
    assert page.evaluate("""async () => {
        const antes = document.querySelector('#mapaFazenda .leaflet-container');
        await carregarTudo();
        return antes === document.querySelector('#mapaFazenda .leaflet-container');
    }""")
    pw.expect(mapa.locator('.mf-ruas')).to_have_count(1)
    assert not state['errors']


def test_mapa_da_fazenda_sem_localizacao_abre_o_editor(painel):
    page, state = painel
    _tiles_offline(page)
    state['coords'] = {1: (-22.7253, -47.6492)}
    _abrir_mapa_fazenda(page, 2)
    mapa = page.locator('#mapaFazenda')
    pw.expect(mapa).to_contain_text('Esta fazenda ainda não tem localização.')
    pw.expect(mapa.locator('.leaflet-container')).to_be_hidden()
    mapa.get_by_role('button', name='Informar localização').click()
    pw.expect(page.locator('#detTitulo')).to_have_text('Fazenda 2')
    # Ao salvar, o Inicio recarrega e o mapa da fazenda aparece.
    state['coords'][2] = (-22.9056, -47.0608)
    page.locator('#fzLat').fill('-22.9056')
    page.locator('#fzLon').fill('-47.0608')
    page.locator('#detCorpo [data-salvar-coord]').click()
    pw.expect(page.locator('#fzCoordMsg')).to_contain_text('salva')
    pw.expect(mapa.locator('path.leaflet-interactive')).to_have_count(2)
    pw.expect(mapa.get_by_text('Esta fazenda ainda não tem localização.')).to_be_hidden()
    assert not state['errors']


def test_mapa_da_fazenda_lista_maquinas_e_abre_o_painel(painel):
    page, state = painel
    _tiles_offline(page)
    state['coords'] = {1: (-22.7253, -47.6492), 2: (-22.9056, -47.0608)}
    _abrir_mapa_fazenda(page, 2)
    lista = page.locator('#mapaFazenda [data-mf-lista]')
    pw.expect(lista).to_contain_text('Trator 2')
    pw.expect(lista).to_contain_text('Posição GPS ainda não enviada pelo ESP32')
    # Maquina de outra fazenda: troca a fazenda antes de abrir o Painel.
    lista.locator('[data-mf-maquina="2"]').click()
    pw.expect(page.locator('#tituloView')).to_have_text('Painel da máquina')
    assert page.evaluate('String(fazendaSelecionada)') == '2'
    assert page.evaluate('String(equipamentoSelecionado)') == '2'
    assert not state['errors']


def test_alternancia_carteira_fazenda_lembra_a_escolha(painel):
    page, state = painel
    _tiles_offline(page)
    state['coords'] = {1: (-22.7253, -47.6492)}
    _abrir_mapa_fazenda(page, 1)
    pw.expect(page.locator('#mapaCarteira')).to_be_hidden()
    # A escolha fica lembrada ao sair e voltar ao Inicio.
    nav(page, 'fazendas')
    nav(page, 'inicio')
    pw.expect(page.locator('[data-modo-mapa="fazenda"]')).to_have_attribute('aria-pressed', 'true')
    pw.expect(page.locator('#mapaFazendaSel')).to_have_value('1')
    page.locator('[data-modo-mapa="carteira"]').click()
    pw.expect(page.locator('[data-modo-mapa="carteira"]')).to_have_attribute('aria-pressed', 'true')
    pw.expect(page.locator('#mapaFazenda')).to_be_hidden()
    pw.expect(page.locator('#mapaCarteira path.leaflet-interactive')).to_have_count(1)
    pw.expect(page.locator('#semLocalizacao')).to_contain_text('Fazenda 2')
    assert not state['errors']
