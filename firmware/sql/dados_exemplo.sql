-- SOMPO - Dados de exemplo para as tabelas de NEGOCIO (cliente/equipamentos/riscos/sinistros).
--
-- As tabelas do SENSOR (telemetria/eventos) sao alimentadas pelo ESP32 e ja tem dado real.
-- Estas quatro aqui sao o modelo de negocio do seguro (o ERD da Sompo) e ficam vazias num
-- projeto so de sensor - este script popula alguns registros de demonstracao para a
-- apresentacao, respeitando as chaves estrangeiras:
--
--   cliente  <--  equipamentos  <--  riscos  -->  telemetria (leitura real do sensor)
--                      ^                ^
--                      |                |
--                      +---- sinistros --+
--
-- Rode no SQL Editor do Supabase (o editor usa o papel de servico e ignora o RLS, entao os
-- inserts passam). E idempotente: os `where not exists` evitam duplicar se rodar de novo.
--
-- OBS: o painel (API/Render) mostra so telemetria/eventos/scores - estes registros aparecem
-- no Table Editor do Supabase, nao no painel.

-- ==========================================================================
-- 1. Clientes
-- ==========================================================================
insert into public.cliente (nome, cnpj, endereco, telefone, email)
select 'Construtora Andrade Ltda', '12.345.678/0001-90', 'Av. Paulista, 1000 - Sao Paulo/SP', '(11) 3555-1000', 'contato@construtoraandrade.com.br'
where not exists (select 1 from public.cliente where cnpj = '12.345.678/0001-90');

insert into public.cliente (nome, cnpj, endereco, telefone, email)
select 'Mineradora Vale Verde S.A.', '98.765.432/0001-10', 'Rod. dos Bandeirantes, km 45 - Jundiai/SP', '(11) 4820-2200', 'seguros@valeverde.com.br'
where not exists (select 1 from public.cliente where cnpj = '98.765.432/0001-10');

-- ==========================================================================
-- 2. Equipamentos (cada um pertence a um cliente)
-- ==========================================================================
-- O "Escavadeira Hidraulica 01" e a maquina monitorada pelo ESP32 (dispositivo SOMPO-ESP32).
insert into public.equipamentos (nome, tipo, modelo, fabricacao, ultima_manutencao, valor_segurado, fk_cliente_id_cliente)
select 'Escavadeira Hidraulica 01', 'Escavadeira', 'CAT 320 GX', '2022-03-15', '2026-06-10', 850000.00,
       (select id_cliente from public.cliente where cnpj = '12.345.678/0001-90')
where not exists (select 1 from public.equipamentos where nome = 'Escavadeira Hidraulica 01');

insert into public.equipamentos (nome, tipo, modelo, fabricacao, ultima_manutencao, valor_segurado, fk_cliente_id_cliente)
select 'Retroescavadeira 02', 'Retroescavadeira', 'JCB 3CX', '2021-08-20', '2026-05-22', 420000.00,
       (select id_cliente from public.cliente where cnpj = '12.345.678/0001-90')
where not exists (select 1 from public.equipamentos where nome = 'Retroescavadeira 02');

insert into public.equipamentos (nome, tipo, modelo, fabricacao, ultima_manutencao, valor_segurado, fk_cliente_id_cliente)
select 'Caminhao Basculante 03', 'Caminhao', 'Volvo FMX 460', '2023-01-10', '2026-07-01', 610000.00,
       (select id_cliente from public.cliente where cnpj = '98.765.432/0001-10')
where not exists (select 1 from public.equipamentos where nome = 'Caminhao Basculante 03');

-- ==========================================================================
-- 3. Riscos (ligados a um equipamento e a uma leitura REAL de telemetria)
-- ==========================================================================
insert into public.riscos (tipo, gravidade, descricao, data_hora, fk_telemetria_id_telemetria, fk_equipamentos_id_equipamento)
select 'Furto', 'Alta', 'Vibracao detectada com a maquina desligada (possivel adulteracao)', now(),
       (select id from public.telemetria order by criado_em desc limit 1),
       (select id_equipamento from public.equipamentos where nome = 'Escavadeira Hidraulica 01')
where not exists (select 1 from public.riscos where descricao like 'Vibracao detectada%');

insert into public.riscos (tipo, gravidade, descricao, data_hora, fk_telemetria_id_telemetria, fk_equipamentos_id_equipamento)
select 'Incendio', 'Media', 'Temperatura do escape acima do limiar de atencao', now() - interval '1 day',
       (select id from public.telemetria order by criado_em desc limit 1 offset 1),
       (select id_equipamento from public.equipamentos where nome = 'Escavadeira Hidraulica 01')
where not exists (select 1 from public.riscos where descricao like 'Temperatura do escape%');

insert into public.riscos (tipo, gravidade, descricao, data_hora, fk_telemetria_id_telemetria, fk_equipamentos_id_equipamento)
select 'Furto', 'Media', 'Capo aberto com a maquina desligada', now() - interval '2 days',
       (select id from public.telemetria order by criado_em desc limit 1 offset 2),
       (select id_equipamento from public.equipamentos where nome = 'Retroescavadeira 02')
where not exists (select 1 from public.riscos where descricao like 'Capo aberto%');

-- ==========================================================================
-- 4. Sinistros (ligados a um equipamento e ao risco que o originou)
-- ==========================================================================
insert into public.sinistros (data_hora, causa, descricao, prejuizo, fk_equipamentos_id_equipamento, fk_riscos_id_risco)
select now() - interval '3 days', 'Furto', 'Tentativa de furto da escavadeira durante a madrugada; alarme disparado e partida sem cracha autorizado.', 15000.00,
       (select id_equipamento from public.equipamentos where nome = 'Escavadeira Hidraulica 01'),
       (select id_risco from public.riscos where tipo = 'Furto' and gravidade = 'Alta' order by id_risco limit 1)
where not exists (select 1 from public.sinistros where descricao like 'Tentativa de furto da escavadeira%');

insert into public.sinistros (data_hora, causa, descricao, prejuizo, fk_equipamentos_id_equipamento, fk_riscos_id_risco)
select now() - interval '10 days', 'Incendio', 'Principio de incendio no compartimento do motor, contido pela equipe em campo.', 48000.00,
       (select id_equipamento from public.equipamentos where nome = 'Escavadeira Hidraulica 01'),
       (select id_risco from public.riscos where tipo = 'Incendio' order by id_risco limit 1)
where not exists (select 1 from public.sinistros where descricao like 'Principio de incendio%');

-- ==========================================================================
-- Conferencia (opcional)
-- ==========================================================================
-- select 'cliente' t, count(*) from public.cliente
-- union all select 'equipamentos', count(*) from public.equipamentos
-- union all select 'riscos', count(*) from public.riscos
-- union all select 'sinistros', count(*) from public.sinistros;

-- ==========================================================================
-- LIMPAR (descomente para zerar e recomecar - respeita a ordem das FKs)
-- ==========================================================================
-- delete from public.sinistros;
-- delete from public.riscos;
-- delete from public.equipamentos;
-- delete from public.cliente;
