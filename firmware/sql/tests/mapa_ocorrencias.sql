-- Runs after the fleet assertions (farms still live) and before the deletion assertions.
select pg_temp.check_true((select count(*)=4 from fazenda),'mapa: farms preserved');
select pg_temp.check_true((select count(*)=4 from fazenda where latitude is null and longitude is null),'mapa: coordinates start empty');
set role service_role;
update fazenda set latitude=-22.7253, longitude=-47.6492 where id_fazenda=2;
reset role;
select pg_temp.check_true((select latitude=-22.7253 and longitude=-47.6492 from fazenda where id_fazenda=2),'mapa: service saves coordinates');
select pg_temp.rejects($q$update fazenda set latitude=91, longitude=0 where id_fazenda=3$q$,'mapa: latitude out of range');
select pg_temp.rejects($q$update fazenda set latitude=0, longitude=-181 where id_fazenda=3$q$,'mapa: longitude out of range');
select pg_temp.rejects($q$update fazenda set latitude=-10 where id_fazenda=3$q$,'mapa: latitude without longitude');
update fazenda set latitude=null, longitude=null where id_fazenda=2;
-- Ocorrencias: fila de tratamento dos alertas (fazenda 2; limpas no fim para nao afetar as exclusoes).
select pg_temp.check_true(to_regclass('public.ocorrencias') is not null,'ocorrencias: table exists');
set role service_role;
insert into ocorrencias(fazenda_id,equipamento_id,evento_id,tipo,titulo,criado_por)
 values (2,3,(select min(id) from eventos),'furto_capo','Capo aberto fora de hora','admin');
reset role;
select pg_temp.check_true((select status='aberta' and resolvido_em is null and atualizado_em is not null
 from ocorrencias where titulo='Capo aberto fora de hora'),'ocorrencias: opens with defaults');
select pg_temp.rejects($q$insert into ocorrencias(fazenda_id,titulo,evento_id) values (2,'dup',(select min(id) from eventos))$q$,'ocorrencias: one per event');
select pg_temp.rejects($q$insert into ocorrencias(fazenda_id,titulo,status) values (2,'x','fechada')$q$,'ocorrencias: invalid status');
select pg_temp.rejects($q$insert into ocorrencias(fazenda_id,titulo) values (2,'   ')$q$,'ocorrencias: blank title');
select pg_temp.rejects($q$insert into ocorrencias(titulo) values ('sem fazenda')$q$,'ocorrencias: farm required');
insert into ocorrencias(fazenda_id,titulo) values (2,'Manual sem evento'),(2,'Outra manual');
select pg_temp.check_true((select count(*)=2 from ocorrencias where evento_id is null),'ocorrencias: many manual entries');
update ocorrencias set atualizado_em=now()-interval '1 day' where titulo='Capo aberto fora de hora';
update ocorrencias set status='resolvida' where titulo='Capo aberto fora de hora';
select pg_temp.check_true((select resolvido_em is not null and atualizado_em>now()-interval '1 minute'
 from ocorrencias where titulo='Capo aberto fora de hora'),'ocorrencias: resolving stamps dates');
update ocorrencias set status='aberta' where titulo='Capo aberto fora de hora';
select pg_temp.check_true((select resolvido_em is null from ocorrencias where titulo='Capo aberto fora de hora'),'ocorrencias: reopening clears resolution');
set role anon;
select pg_temp.rejects($q$select 1 from ocorrencias$q$,'ocorrencias: anon cannot read');
reset role;
delete from ocorrencias;
select 'ALL MAP SQL ASSERTIONS PASSED' result;
