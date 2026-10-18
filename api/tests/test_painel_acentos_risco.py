"""Classe de risco com acento na tela (MÉDIO, ATENÇÃO, CRÍTICO) sem quebrar busca nem cores."""
from datetime import datetime, timezone

from tests.test_painel import painel, pw, nav  # noqa: F401


def test_nome_da_classe_acentua_so_o_que_o_firmware_manda_sem_acento(painel):
    page, _ = painel
    assert page.evaluate("() => ['MEDIO', 'ATENCAO', 'CRITICO', 'ALTO', 'BAIXO', 'SEGURO', null].map(nomeClasse)") == \
        ['MÉDIO', 'ATENÇÃO', 'CRÍTICO', 'ALTO', 'BAIXO', 'SEGURO', None]


def test_busca_das_listas_ignora_acento_e_caixa(painel):
    page, _ = painel
    achados = page.evaluate("""() => {
      document.body.insertAdjacentHTML('beforeend', '<input data-busca="tbTeste" value="medio"><div id="tbTeste">'
        + '<div data-linha>Fazenda Aurora · MÉDIO</div><div data-linha>Fazenda Boa Vista · BAIXO</div>'
        + '<div data-sem-resultado hidden>nada</div></div>');
      const ocultas = () => [...document.querySelectorAll('#tbTeste [data-linha]')].map(e => e.hidden);
      const r = {};
      aplicarBusca('tbTeste'); r.medio = ocultas();
      document.querySelector('[data-busca="tbTeste"]').value = 'MÉDIO'; aplicarBusca('tbTeste'); r.medioAcento = ocultas();
      document.querySelector('[data-busca="tbTeste"]').value = 'fazenda'; aplicarBusca('tbTeste'); r.fazenda = ocultas();
      return r;
    }""")
    assert achados == {'medio': [False, True], 'medioAcento': [False, True], 'fazenda': [False, False]}


def test_kpi_de_risco_mostra_atencao_acentuada(painel):
    page, state = painel
    agora = datetime.now(timezone.utc).isoformat()
    page.route('**/telemetria*', lambda r: r.fulfill(json={'dados': [dict(
        registro_id='x1', criado_em=agora, ocorrido_em=agora, recebido_em=agora, nivel_risco='ATENCAO', temp_escape=120,
        temp_ambiente=27, umidade_ar=50, vibracao=0.1, chama_detectada=False, capo_aberto=False,
        tanque_aberto=False, motor_ligado=True)]}))
    nav(page, 'visao')
    page.select_option('#equipamentoSel', '1')
    pw.expect(page.locator('#kpiRisco')).to_have_text('ATENÇÃO')
    assert page.evaluate("() => estadoRisco('ATENCAO')") == 'atencao'   # a logica segue pela chave sem acento
    assert not state['errors']
