"""Modo ao vivo na secao Telemetria atual (rede isolada; nunca toca no Supabase)."""
from datetime import datetime, timedelta, timezone
import json
import re
from urllib.parse import parse_qs, urlparse

from tests.test_painel import painel, pw  # noqa: F401


def agora(seg=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=seg)).isoformat()


def _servidor(page, ligado_ate=None):
    """Finge o /ao-vivo: cada GET entrega e esvazia a fila; POST liga/desliga."""
    st = dict(ate=ligado_ate, fila=[], posts=[], falhar=False, desdes=[], vencer_cursor=False)

    def ao_vivo(r):
        if r.request.method == 'POST':
            st['posts'].append(r.request.post_data_json)
            st['ate'] = agora(7200) if r.request.post_data_json['ligar'] else None
            r.fulfill(json={'ok': True, 'ao_vivo_ate': st['ate']})
            return
        desde = parse_qs(urlparse(r.request.url).query).get('desde', [None])[0]
        st['desdes'].append(desde)
        if st['vencer_cursor'] and desde:   # cursor mais velho que a janela de 10 min: o servidor recusa uma vez
            st['vencer_cursor'] = False
            st['indice_400'] = len(st['desdes']) - 1
            r.fulfill(status=400, json={'erro': 'desde_invalido'})
            return
        if st['falhar']:
            r.fulfill(status=502, json={'erro': 'falha_na_consulta'})
            return
        lote, st['fila'] = st['fila'], []
        d = dict(telemetria=[], eventos=[], operacoes=[], ao_vivo_ate=st['ate'], cursor=agora(-1), agora=agora())
        for tabela, row in lote:
            d[tabela].append(row)
        r.fulfill(json=d, headers={'Cache-Control': 'no-store'})
    page.route(re.compile(r'.*/ao-vivo(\?.*)?$'), ao_vivo)
    return st


def leitura(n, **x):
    t = datetime.now(timezone.utc)
    return ('telemetria', {**dict(registro_id=f't{n}', ocorrido_em=(t - timedelta(seconds=0.8)).isoformat(),
                                  recebido_em=t.isoformat(), criado_em=t.isoformat(), temp_escape=31, temp_ambiente=27.3,
                                  umidade_ar=58, vibracao=0.02, chama_detectada=False, capo_aberto=False,
                                  tanque_aberto=False, motor_ligado=False, operador_autorizado=None,
                                  nivel_risco='SEGURO'), **x})


def _ja_ligada(page):
    page.evaluate(f"maquinasCache.forEach(m => m.ao_vivo_ate = {json.dumps(agora(3600))})")


def _abrir(page):
    page.select_option('#equipamentoSel', '1')
    page.wait_for_load_state('networkidle')
    page.locator('#secTelemetria').scroll_into_view_if_needed()


LIGADA = "() => document.querySelector('#secTelemetria').classList.contains('ao-vivo')"
DESLIGADA = "() => !document.querySelector('#secTelemetria').classList.contains('ao-vivo')"


def test_liga_mostra_terminal_com_gravado_e_desliga(painel):
    page, _ = painel
    st = _servidor(page)
    _abrir(page)
    assert 'ao-vivo' not in (page.locator('#secTelemetria').get_attribute('class') or '')
    page.click('#btnAoVivo')
    page.wait_for_function(LIGADA)
    assert st['posts'] == [{'ligar': True}]
    pw.expect(page.locator('#txtAoVivo')).to_have_text('Desligar')
    pw.expect(page.locator('#aoVivoCont')).to_have_text(re.compile(r'^(1:59:\d\d|2:00:00)$'))
    st['fila'].append(leitura(1))
    linha = page.locator('#aoVivoTerminal .av-ln').last
    pw.expect(linha).to_contain_text('escape 31 °C', timeout=5000)
    pw.expect(linha.locator('.av-ok')).to_have_text('✓ gravado · chegou em 0,8 s')
    page.click('#btnAoVivo')
    page.wait_for_function(DESLIGADA)
    assert st['posts'][-1] == {'ligar': False}


def test_evento_mostra_faixa_linha_vermelha_e_tile_em_alerta(painel):
    page, _ = painel
    st = _servidor(page, ligado_ate=agora(3600))
    _ja_ligada(page)
    _abrir(page)
    st['fila'] += [leitura(1, chama_detectada=True),
                   ('eventos', dict(registro_id='e1', tipo='chama_detectada', severidade=4,
                                    ocorrido_em=agora(-1), recebido_em=agora()))]
    pw.expect(page.locator('#aoVivoFaixa')).to_contain_text('Chama detectada', timeout=5000)
    pw.expect(page.locator('#aoVivoTerminal .av-ln.av-fogo')).to_have_count(1)
    pw.expect(page.locator('#kpis [data-kpi="chama"]')).to_have_class(re.compile(r'\bav-alerta\b'))
    # A carga de 5 s (o /telemetria do fixture vem vazio) nao apaga o que o ao vivo pintou.
    page.wait_for_timeout(5500)
    pw.expect(page.locator('#kpis [data-kpi="chama"]')).to_have_class(re.compile(r'\bav-alerta\b'))


def test_maquina_ja_ao_vivo_abre_ligada_esperando_a_placa(painel):
    page, _ = painel
    _servidor(page, ligado_ate=agora(3600))
    _ja_ligada(page)
    _abrir(page)
    page.wait_for_function(LIGADA)
    pw.expect(page.locator('#aoVivoAguarda')).to_be_visible()


def test_cracha_repetido_pelo_recuo_do_cursor_nao_duplica(painel):
    page, _ = painel
    st = _servidor(page, ligado_ate=agora(3600))
    _ja_ligada(page)
    _abrir(page)
    op = ('operacoes', dict(registro_id='o1', tipo='inicio', uid='04A1B2C3', operador_nome='Ana Souza',
                            ocorrido_em=agora(-1), recebido_em=agora()))
    st['fila'].append(op)
    pw.expect(page.locator('#aoVivoTerminal .av-ln.av-cracha')).to_contain_text('Ana Souza iniciou o turno', timeout=5000)
    st['fila'].append(op)
    page.wait_for_timeout(2500)
    pw.expect(page.locator('#aoVivoTerminal .av-ln.av-cracha')).to_have_count(1)


def test_relogio_da_placa_errado_mostra_so_gravado(painel):
    page, _ = painel
    st = _servidor(page, ligado_ate=agora(3600))
    _ja_ligada(page)
    _abrir(page)
    tabela, row = leitura(1)
    row['ocorrido_em'] = agora(30)   # placa adiantada: latencia negativa
    st['fila'].append((tabela, row))
    pw.expect(page.locator('#aoVivoTerminal .av-ln .av-ok').last).to_have_text('✓ gravado', timeout=5000)


def test_leitura_cabe_no_terminal_do_celular(painel):
    """No celular o selo comprido ("gravado · chegou em") empurrava a leitura para fora da tela."""
    page, _ = painel
    st = _servidor(page, ligado_ate=agora(3600))
    _ja_ligada(page)
    _abrir(page)
    st['fila'].append(leitura(1))
    linha = page.locator('#aoVivoTerminal .av-ln').last
    pw.expect(linha.locator('.av-ok')).to_have_text('✓ gravado · chegou em 0,8 s', timeout=5000)
    largura = linha.locator('.av-txt').evaluate('e => e.getBoundingClientRect().width')
    assert largura >= 140, f'leitura espremida: {largura:.0f}px'


def test_tres_falhas_seguidas_avisam(painel):
    page, _ = painel
    st = _servidor(page, ligado_ate=agora(3600))
    st['falhar'] = True
    _ja_ligada(page)
    _abrir(page)
    pw.expect(page.locator('#aoVivoAviso')).to_have_text('sem conexão com o servidor', timeout=15000)


def test_cursor_vencido_apos_pausa_longa_volta_a_janela_padrao(painel):
    """Aba escondida por mais de 10 min: o servidor recusa o cursor velho (400) e o painel recomeca sem ele."""
    page, _ = painel
    st = _servidor(page, ligado_ate=agora(3600))
    _ja_ligada(page)
    _abrir(page)
    page.wait_for_function("() => !!aoVivo.cursor", timeout=8000)
    st['vencer_cursor'] = True
    st['fila'].append(leitura(1))
    pw.expect(page.locator('#aoVivoTerminal .av-ln').last).to_contain_text('escape 31 °C', timeout=10000)
    assert st['desdes'][st['indice_400'] + 1] is None   # o pedido seguinte ao 400 vai sem `desde`


def test_desligado_nao_mostra_terminal_nem_tela_cheia(painel):
    page, _ = painel
    _servidor(page)
    _abrir(page)
    assert page.locator('#aoVivoTerminal').is_hidden()
    assert page.locator('#btnTelaCheia').is_hidden()
    assert page.locator('#btnAoVivo').is_visible()
