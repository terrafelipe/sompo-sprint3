"""Os tres cenarios do /relatorio/risco.
Todos devem responder HTTP 200; so muda o campo origem_da_analise."""
from unittest.mock import patch

from app import app

EVENTOS = [{'id': 1, 'tipo': 'furto_adulteracao', 'severidade': 4}]   # furto -> score 40


def _get():
    client = app.test_client()
    return client.get('/relatorio/risco?dispositivo=SOMPO-ESP32&dias=7')


def test_origem_prompt_apenas_sem_chave():
    with patch('app.consultar_resumo', return_value=[]), \
         patch('app.consultar_eventos', return_value=EVENTOS), \
         patch('llm.LLM_API_KEY', ''):
        r = _get()
    assert r.status_code == 200
    data = r.get_json()
    assert data['origem_da_analise'] == 'prompt_apenas'
    assert 'prompt_gerado' in data


def test_origem_llm_com_provedor_ok():
    # Provedor devolve numeros proprios (score_furto=999); devem ser IGNORADOS -
    # o score final vem do calculo deterministico (40).
    fake = {
        'justificativa_furto': 'texto do llm',
        'justificativa_incendio': '',
        'recomendacoes': ['r1'],
        'limitacoes': '',
        'score_furto': 999,
    }
    with patch('app.consultar_resumo', return_value=[]), \
         patch('app.consultar_eventos', return_value=EVENTOS), \
         patch('llm.LLM_API_KEY', 'chave-fake'), \
         patch('llm._chamar_provedor', return_value=fake):
        r = _get()
    assert r.status_code == 200
    data = r.get_json()
    assert data['origem_da_analise'] == 'llm'
    assert data['justificativa_furto'] == 'texto do llm'
    assert data['score_furto'] == 40   # forcado do scores.py, nao os 999 do LLM


def test_origem_fallback_provedor_fora():
    def explode(_prompt):
        raise RuntimeError('provedor fora do ar')

    with patch('app.consultar_resumo', return_value=[]), \
         patch('app.consultar_eventos', return_value=EVENTOS), \
         patch('llm.LLM_API_KEY', 'chave-fake'), \
         patch('llm._chamar_provedor', side_effect=explode):
        r = _get()
    assert r.status_code == 200
    data = r.get_json()
    assert data['origem_da_analise'] == 'fallback'
    assert data['score_furto'] == 40
    assert 'provedor fora do ar' in data['limitacoes']


EVENTOS_DOIS_EIXOS = [
    {'id': 1, 'tipo': 'furto_capo', 'severidade': 2},
    {'id': 2, 'tipo': 'chama_detectada', 'severidade': 5},
    {'id': 3, 'tipo': 'chama_detectada', 'severidade': 5},
]


def _get_com(eventos, provedor, url='/relatorio/risco?dispositivo=SOMPO-ESP32&dias=7'):
    with patch('app.consultar_resumo', return_value=[]), \
         patch('app.consultar_eventos', return_value=eventos), \
         patch('llm.LLM_API_KEY', 'chave-fake'), \
         patch('llm._chamar_provedor', side_effect=provedor):
        return app.test_client().get(url)


def test_llm_com_campo_vazio_e_complementado_pelo_sistema():
    # A IA as vezes devolve a justificativa de um eixo vazia e nenhuma recomendacao:
    # a tela nao pode ficar em branco -> o texto deterministico completa o que faltou.
    fake = {'justificativa_furto': 'texto do llm', 'justificativa_incendio': '',
            'recomendacoes': [], 'limitacoes': ''}
    data = _get_com(EVENTOS_DOIS_EIXOS, lambda _p: fake).get_json()
    assert data['origem_da_analise'] == 'llm'
    assert data['justificativa_furto'] == 'texto do llm'
    assert 'incendio' in data['justificativa_incendio'].lower()
    assert data['recomendacoes']
    assert data['resumo']
    assert set(data['complementado_pelo_sistema']) >= {'justificativa_incendio', 'recomendacoes', 'resumo'}


def test_termos_tecnicos_viram_nomes_legiveis():
    fake = {'justificativa_furto': "9 eventos de furto_capo associados ao sensor 'reed_capo' "
                                   "e 10 de operador_nao_autorizado pela origem 'rc522'.",
            'justificativa_incendio': 'chama_detectada pelo ky026.',
            'recomendacoes': ['Revisar o reed_tanque.'], 'limitacoes': '', 'resumo': 'ok'}
    data = _get_com(EVENTOS_DOIS_EIXOS, lambda _p: fake).get_json()
    texto = ' '.join([data['justificativa_furto'], data['justificativa_incendio'], *data['recomendacoes']])
    # Os ids crus somem (o modelo do sensor pode ficar entre parenteses, ex. "(RC522)").
    for tecnico in ('furto_capo', 'reed_capo', "'rc522'", 'operador_nao_autorizado', 'chama_detectada', 'ky026', 'reed_tanque'):
        assert tecnico not in texto
    assert 'capô aberto' in texto and 'sensor do capô' in texto and 'partida sem crachá' in texto
    assert 'leitor de crachá (RC522)' in texto and 'sensor de chama (KY-026)' in texto
    assert 'sensor sensor' not in texto


def test_detalhamento_pontos_e_faixas_vao_para_a_tela():
    data = _get_com(EVENTOS_DOIS_EIXOS, lambda _p: {'justificativa_furto': 'a', 'justificativa_incendio': 'b',
                                                     'recomendacoes': ['c'], 'limitacoes': '', 'resumo': 'd'}).get_json()
    assert data['detalhamento']['chama_detectada'] == {'eixo': 'incendio', 'quantidade': 2, 'pontos': 140}
    assert data['pontos_acumulados'] == {'furto': 10, 'incendio': 140}
    assert data['score_incendio'] == 100   # teto
    assert data['faixas'] == {'medio': 34, 'alto': 67}
    assert data['gerado_em']


def test_novo_1_ignora_o_cache_da_ia():
    chamadas = []
    def provedor(_p):
        chamadas.append(1)
        return {'justificativa_furto': f'versao {len(chamadas)}', 'justificativa_incendio': 'x',
                'recomendacoes': ['r'], 'limitacoes': '', 'resumo': 's'}
    with patch('app.consultar_resumo', return_value=[]), \
         patch('app.consultar_eventos', return_value=EVENTOS_DOIS_EIXOS), \
         patch('llm.LLM_API_KEY', 'chave-fake'), \
         patch('llm._chamar_provedor', side_effect=provedor):
        c = app.test_client()
        c.get('/relatorio/risco?dispositivo=SOMPO-ESP32&dias=7')
        segunda = c.get('/relatorio/risco?dispositivo=SOMPO-ESP32&dias=7').get_json()
        nova = c.get('/relatorio/risco?dispositivo=SOMPO-ESP32&dias=7&novo=1').get_json()
    assert segunda['justificativa_furto'] == 'versao 1'    # cache reaproveitado
    assert nova['justificativa_furto'] == 'versao 2'       # "Gerar de novo" chama a IA outra vez
    assert len(chamadas) == 2


def test_nome_legivel_nao_duplica_quando_a_ia_ja_usou_o_nome():
    from relatorios import legivel
    assert legivel('partida sem crachá (leitor de crachá (RC522))') == 'partida sem crachá (leitor de crachá (RC522))'
    assert legivel('pelo leitor de crachá (rc522)') == 'pelo leitor de crachá (RC522)'
    assert legivel("origem 'rc522'") == 'origem leitor de crachá (RC522)'


def test_relatorio_compara_com_o_periodo_anterior():
    # Busca 2x a janela e separa pela data: os scores atuais usam so os ultimos N dias;
    # "anterior" (N dias antes deles) alimenta a variacao dos cards na tela.
    from datetime import datetime, timedelta, timezone
    agora = datetime.now(timezone.utc)
    eventos = [
        {'id': 1, 'tipo': 'chama_detectada', 'severidade': 5, 'criado_em': (agora - timedelta(days=1)).isoformat()},
        {'id': 2, 'tipo': 'furto_capo', 'severidade': 2, 'criado_em': (agora - timedelta(days=10)).isoformat()},
        {'id': 3, 'tipo': 'furto_capo', 'severidade': 2, 'criado_em': (agora - timedelta(days=9)).isoformat()},
    ]
    janelas = []
    def do_banco(_disp, dias=7):
        janelas.append(dias)
        return eventos
    with patch('app.consultar_resumo', return_value=[]), \
         patch('app.consultar_eventos', side_effect=do_banco), \
         patch('llm.LLM_API_KEY', ''):
        data = app.test_client().get('/relatorio/risco?dispositivo=SOMPO-ESP32&dias=7').get_json()
    assert janelas == [14]
    assert (data['score_furto'], data['score_incendio']) == (0, 70)
    assert [e['id'] for e in data['eventos']] == [1]
    assert data['anterior'] == {'score_furto': 20, 'score_incendio': 0,
                                'eventos': {'furto': 2, 'incendio': 0, 'total': 2}}


def test_prompt_leva_so_os_eventos_mais_recentes_em_janelas_longas():
    # 90 dias podem ter ~700 eventos: o prompt leva o detalhamento completo (totais exatos)
    # e so uma amostra dos mais recentes, para nao ficar enorme e lento.
    from relatorios import LIMITE_EVENTOS_PROMPT, montar_prompt
    from scores import calcular_scores
    eventos = [{'id': i, 'tipo': 'chama_detectada', 'severidade': 5} for i in range(150)]   # mais recente primeiro
    prompt = montar_prompt('SOMPO-ESP32', 90, calcular_scores('SOMPO-ESP32', 90, eventos), eventos)
    assert LIMITE_EVENTOS_PROMPT == 60
    assert prompt.count('"tipo": "chama_detectada"') == 60
    assert '"id": 0,' in prompt and '"id": 59,' in prompt and '"id": 60,' not in prompt
    assert '"quantidade": 150' in prompt          # o detalhamento continua com o total real
    assert '60 de 150' in prompt
