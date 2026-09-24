"""Mapa da própria fazenda no Início do gestor."""

from tests.test_painel import FARMS, captura, nav, painel, pw  # noqa: F401


def _abrir_inicio_gestor(page, state, coordenadas=None):
    page.route('**/tile.openstreetmap.org/**', lambda r: r.fulfill(status=204))
    page.route('**/server.arcgisonline.com/**', lambda r: r.fulfill(status=204))
    if coordenadas:
        fazenda = {**FARMS[0], 'latitude': coordenadas[0], 'longitude': coordenadas[1]}
        page.route('**/fazendas/1/resumo*', lambda r: r.fulfill(json={
            'fazenda': fazenda,
            'equipamentos': [dict(id_equipamento=1, nome='Trator 1', fk_fazenda_id_fazenda=1,
                                  fk_cliente_id_cliente=1, dispositivo_id='ESP-1',
                                  fabricacao='2020-01-02', ultima_manutencao='2026-09-01',
                                  valor_segurado='150000.50', comunicacao='sem_dados',
                                  operador_nome='Operador não identificado',
                                  scores=dict(score_furto=25, score_incendio=5,
                                              eventos_considerados=dict(total=0)))],
            'alertas_recentes': [],
        }))
    state['role'] = 'gestor_fazenda'
    page.reload()
    pw.expect(page.locator('#inicioGestor')).to_be_visible()


def test_gestor_ve_mapa_cerca_pino_e_abre_maquina_sem_recriar_no_refresh(painel):
    page, state = painel
    _abrir_inicio_gestor(page, state, (-22.7253, -47.6492))
    mapa = page.locator('#gMapaFazenda')
    pw.expect(mapa.locator('[data-mf-mapa]')).to_be_visible()
    pw.expect(mapa.locator('.leaflet-overlay-pane path.leaflet-interactive')).to_have_count(2)
    pw.expect(mapa.locator('.leaflet-tooltip')).to_contain_text('Cerca ilustrativa (1 km)')
    pw.expect(mapa.locator('[data-mf-maquina]')).to_have_count(1)
    mapa.scroll_into_view_if_needed()
    page.evaluate("window.__mapaGestorInicial = document.querySelector('#gMapaFazenda')._mf.mapa")
    page.evaluate('() => carregarInicioGestor()')
    assert page.evaluate("document.querySelector('#gMapaFazenda')._mf.mapa === window.__mapaGestorInicial")

    page.evaluate("aplicarTema('claro')")
    page.evaluate('() => carregarInicioGestor()')
    captura(page, 'gestor-mapa-claro')
    page.locator('#btnTema').click()
    pw.expect(page.locator('html')).to_have_attribute('data-tema', 'escuro')
    page.evaluate('() => carregarInicioGestor()')
    captura(page, 'gestor-mapa-escuro')

    mapa.locator('[data-mf-maquina="1"]').click()
    pw.expect(page.locator('#tituloView')).to_have_text('Painel da máquina')
    assert page.evaluate('equipamentoSelecionado') == 1
    assert not state['errors']


def test_gestor_sem_coordenadas_ve_orientacao_sem_edicao(painel):
    page, state = painel
    _abrir_inicio_gestor(page, state)
    mapa = page.locator('#gMapaFazenda')
    pw.expect(mapa.locator('[data-mf-vazio]')).to_be_visible()
    pw.expect(mapa).to_contain_text('Peça à Sompo para informar a localização da fazenda.')
    pw.expect(mapa.locator('[data-mf-mapa]')).to_be_hidden()
    assert mapa.locator('[data-mf-informar]').count() == 0
    assert not state['errors']
