from unittest.mock import patch

from app import app


def test_listar_fazendas():
    client = app.test_client()
    linhas = [{'id_fazenda': 1, 'nome': 'Santa Rita', 'cliente': {'nome': 'Construtora Andrade Ltda'}}]
    with patch('app.consultar_fazendas', return_value=linhas), patch('app.consultar_gestores', return_value=[]):
        response = client.get('/fazendas')
    assert response.status_code == 200
    data = response.get_json()
    assert data['total'] == 1
    assert data['dados'][0]['nome'] == 'Santa Rita'


def test_listar_clientes():
    client = app.test_client()
    with patch('app.consultar_clientes', return_value=[{'id_cliente': 1, 'nome': 'Construtora Andrade Ltda'}]):
        response = client.get('/clientes')
    assert response.status_code == 200
    assert response.get_json()['total'] == 1


def test_criar_cliente_sucesso():
    client = app.test_client()
    criado = {'id_cliente': 3, 'nome': 'Fazendas Reunidas', 'cnpj': '11.111.111/0001-11'}
    with patch('app.inserir_tabela', return_value=criado) as mock_inserir:
        response = client.post('/clientes', json={
            'nome': '  Fazendas Reunidas  ',
            'cnpj': '11.111.111/0001-11',
            'telefone': '(11) 90000-0000',
            'endereco': 'Rua X, 1 - SP',
            'email': '',
        })
    assert response.status_code == 201
    data = response.get_json()
    assert data['ok'] is True
    assert data['cliente']['id_cliente'] == 3
    tabela, payload = mock_inserir.call_args.args
    assert tabela == 'cliente'
    assert payload['nome'] == 'Fazendas Reunidas'      # sem espaços
    assert payload['cnpj'] == '11.111.111/0001-11'
    assert 'email' not in payload                       # campo vazio (opcional) é omitido


def test_criar_cliente_sem_telefone_da_400():
    client = app.test_client()
    with patch('app.inserir_tabela') as mock_inserir:
        response = client.post('/clientes', json={'nome': 'X', 'cnpj': '1', 'endereco': 'Rua Y'})
    assert response.status_code == 400
    assert response.get_json()['erro'] == 'telefone_obrigatorio'
    mock_inserir.assert_not_called()


def test_criar_cliente_sem_nome_da_400():
    client = app.test_client()
    with patch('app.inserir_tabela') as mock_inserir:
        response = client.post('/clientes', json={'cnpj': '00.000.000/0001-00'})
    assert response.status_code == 400
    assert response.get_json()['erro'] == 'nome_obrigatorio'
    mock_inserir.assert_not_called()


def test_criar_fazenda_sucesso():
    client = app.test_client()
    criado = {'id_fazenda': 7, 'nome': 'Santa Rita', 'area_ha': 1200.0, 'fk_cliente_id_cliente': 1}
    with patch('app.inserir_tabela', return_value=criado) as mock_inserir:
        response = client.post('/fazendas', json={
            'nome': '  Santa Rita  ',
            'localizacao': 'Ribeirão Preto/SP',
            'area_ha': '1200',
            'fk_cliente_id_cliente': '1',
        })
    assert response.status_code == 201
    data = response.get_json()
    assert data['ok'] is True
    assert data['fazenda']['id_fazenda'] == 7
    # Nome vem sem espaços, area vira float e cliente vira int no payload enviado ao Supabase.
    tabela, payload = mock_inserir.call_args.args
    assert tabela == 'fazenda'
    assert payload['nome'] == 'Santa Rita'
    assert payload['area_ha'] == 1200.0
    assert payload['fk_cliente_id_cliente'] == 1


def test_criar_fazenda_sem_nome_da_400():
    client = app.test_client()
    with patch('app.inserir_tabela') as mock_inserir:
        response = client.post('/fazendas', json={'localizacao': 'SP'})
    assert response.status_code == 400
    assert response.get_json()['erro'] == 'nome_obrigatorio'
    mock_inserir.assert_not_called()


def test_criar_fazenda_area_invalida_da_400():
    client = app.test_client()
    with patch('app.inserir_tabela') as mock_inserir:
        response = client.post('/fazendas', json={
            'nome': 'X', 'localizacao': 'SP', 'area_ha': 'abc', 'fk_cliente_id_cliente': '1',
        })
    assert response.status_code == 400
    assert response.get_json()['erro'] == 'area_invalida'
    mock_inserir.assert_not_called()


def test_criar_fazenda_sem_localizacao_da_400():
    client = app.test_client()
    with patch('app.inserir_tabela') as mock_inserir:
        response = client.post('/fazendas', json={'nome': 'X'})
    assert response.status_code == 400
    assert response.get_json()['erro'] == 'localizacao_obrigatoria'
    mock_inserir.assert_not_called()


# ---------------------------------------------------------------------------
# PATCH /fazendas/<id>: edicao (Sompo), inclusive as coordenadas do mapa.
# ---------------------------------------------------------------------------
def _patch(corpo, retorno=None, **kw):
    client = app.test_client()
    with patch('app.atualizar_tabela', return_value=retorno if retorno is not None else {'id_fazenda': 5}, **kw) as mock:
        response = client.patch('/fazendas/5', json=corpo)
    return response, mock


def test_patch_fazenda_salva_coordenadas():
    response, mock = _patch({'latitude': '-22.7253', 'longitude': -47.6492})
    assert response.status_code == 200
    assert response.get_json()['ok'] is True
    tabela, filtros, dados = mock.call_args.args
    assert tabela == 'fazenda'
    assert filtros == {'id_fazenda': 'eq.5', 'excluido_em': 'is.null'}
    assert dados == {'latitude': -22.7253, 'longitude': -47.6492}


def test_patch_fazenda_limpa_coordenadas_e_edita_campos():
    response, mock = _patch({'latitude': None, 'longitude': None, 'nome': '  Santa Rita  ', 'area_ha': '120.5'})
    assert response.status_code == 200
    assert mock.call_args.args[2] == {'latitude': None, 'longitude': None, 'nome': 'Santa Rita', 'area_ha': 120.5}


def test_patch_fazenda_valida_coordenadas():
    casos = [({'latitude': 91, 'longitude': 0}, 'latitude_invalida'),
             ({'latitude': 0, 'longitude': -180.5}, 'longitude_invalida'),
             ({'latitude': 'abc', 'longitude': 0}, 'latitude_invalida'),
             ({'latitude': -10}, 'coordenadas_incompletas'),
             ({'nome': '   '}, 'nome_obrigatorio'),
             ({}, 'nada_para_atualizar')]
    for corpo, erro in casos:
        response, mock = _patch(corpo)
        assert response.status_code == 400, corpo
        assert response.get_json()['erro'] == erro, corpo
        mock.assert_not_called()


def test_patch_fazenda_inexistente_ou_excluida_404():
    response, _ = _patch({'latitude': 1, 'longitude': 1}, retorno={})
    assert response.status_code == 404


def test_patch_fazenda_sem_migracao_avisa():
    from supabase_client import SupabaseError
    response, _ = _patch({'latitude': 1, 'longitude': 1}, side_effect=SupabaseError(400, 'PGRST204'))
    assert response.status_code == 409
    assert response.get_json()['erro'] == 'migracao_pendente'


def test_gestor_nao_edita_fazenda():
    client = app.test_client()
    with client.session_transaction() as s:
        s.update(logado=True, role='gestor_fazenda', fazenda_id=5)
    with patch('app.atualizar_tabela') as mock:
        assert client.patch('/fazendas/5', json={'latitude': 1, 'longitude': 1}).status_code == 403
    mock.assert_not_called()


def test_patch_fazenda_recusa_booleanos_area_invalida_e_corpo_que_nao_e_objeto():
    for corpo, erro in [({'latitude': True, 'longitude': False}, 'latitude_invalida'),
                        ({'area_ha': True}, 'area_invalida'), ({'area_ha': -5}, 'area_invalida'),
                        ({'area_ha': 'nan'}, 'area_invalida'), ([1], 'nada_para_atualizar')]:
        response, mock = _patch(corpo)
        assert response.status_code == 400 and response.get_json()['erro'] == erro, corpo
        mock.assert_not_called()
