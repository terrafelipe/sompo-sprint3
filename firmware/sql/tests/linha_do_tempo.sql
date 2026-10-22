-- Linha do tempo: a telemetria agregada por faixa no banco (24 h, 7 dias e Periodo do painel).
-- Maquina propria (LDT-1) e telemetria inserida direto, sem depender dos outros testes.
insert into equipamentos(nome,fk_cliente_id_cliente,fk_fazenda_id_fazenda,dispositivo_id) values('Linha do tempo',2,2,'LDT-1');
create temp table ldt as select id_equipamento eq from equipamentos where dispositivo_id='LDT-1' and excluido_em is null;
-- janela de 24 h: (2026-10-21 22:00Z, 2026-10-22 22:00Z]
insert into telemetria(dispositivo_id,equipamento_id,criado_em,temp_escape,motor_ligado,nivel_risco)
select 'LDT-1',eq,v.t::timestamptz,v.temp,v.motor,v.risco from ldt,(values
 ('2026-10-21T22:00:00Z',99,true,'CRITICO'),     -- exatamente no inicio: fora
 ('2026-10-22T09:31:00Z',40,false,'ATENCAO'),
 ('2026-10-22T09:33:00Z',63,true,'CRITICO'),      -- mesma faixa de 5 min (09:30-09:35)
 ('2026-10-22T22:00:00Z',30,false,'SEGURO')       -- exatamente no fim: ultima faixa
) v(t,temp,motor,risco);
insert into telemetria(dispositivo_id,equipamento_id,criado_em,temp_escape,motor_ligado,nivel_risco)
values('OUTRO-1',null,'2026-10-22T09:32:00Z',500,true,'CRITICO');
create temp table f as select * from linha_do_tempo_faixas((select eq from ldt),null,'2026-10-21T22:00:00Z','2026-10-22T22:00:00Z',5);
select pg_temp.check_true((select count(*)=288 from f),'24 h in 5 min bins');
select pg_temp.check_true((select sum(leituras)=3 from f),'start excluded, end included, other machine ignored');
select pg_temp.check_true((select inicio='2026-10-21T22:00:00Z'::timestamptz from f order by inicio limit 1),'first bin starts at window start');
select pg_temp.check_true((select leituras=2 and temp_max=63 and motor_ligado and risco='CRITICO' from f where inicio='2026-10-22T09:30:00Z'),
 'bin keeps max temperature, any motor on and worst risk');
select pg_temp.check_true((select leituras=1 and temp_max=30 from f order by inicio desc limit 1),'reading at window end lands in last bin');
select pg_temp.check_true((select leituras=0 and not motor_ligado and temp_max is null and risco is null from f where inicio='2026-10-22T12:00:00Z'),
 'empty bin');
select pg_temp.check_true((select sum(leituras)=1 from linha_do_tempo_faixas(null,'OUTRO-1','2026-10-21T22:00:00Z','2026-10-22T22:00:00Z',60)),
 'without machine filters by device id');
select pg_temp.check_true((select count(*)=24 from linha_do_tempo_faixas((select eq from ldt),null,'2026-10-21T22:00:00Z','2026-10-22T22:00:00Z',60)),
 '24 h in 60 min bins');
select pg_temp.rejects($q$select * from linha_do_tempo_faixas(1,null,'2026-10-21T22:00:00Z','2026-10-22T22:00:00Z',0)$q$,'zero minute bins');
select pg_temp.rejects($q$select * from linha_do_tempo_faixas(1,null,'2026-10-21T22:00:00Z','2026-10-22T22:00:00Z',1441)$q$,'bins over one day');
select pg_temp.rejects($q$select * from linha_do_tempo_faixas(1,null,'2026-10-22T22:00:00Z','2026-10-22T22:00:00Z',5)$q$,'empty window');
select pg_temp.rejects($q$select * from linha_do_tempo_faixas(1,null,'2025-10-22T22:00:00Z','2026-10-22T22:00:00Z',5)$q$,'more than 2000 bins');
select pg_temp.check_true(not has_function_privilege('anon','public.linha_do_tempo_faixas(bigint,text,timestamptz,timestamptz,integer)','execute'),'anon cannot call');
select pg_temp.check_true(not has_function_privilege('authenticated','public.linha_do_tempo_faixas(bigint,text,timestamptz,timestamptz,integer)','execute'),'authenticated cannot call');
select pg_temp.check_true(has_function_privilege('service_role','public.linha_do_tempo_faixas(bigint,text,timestamptz,timestamptz,integer)','execute'),'service role can call');
select 'ALL LINHA DO TEMPO SQL ASSERTIONS PASSED' result;
