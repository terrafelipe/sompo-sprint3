-- Runs after the deletion assertions: machine 1 is archived holding SOMPO-ESP32,
-- machine 3 is live in farm 2 with DEVICE-2 and a credential.
select pg_temp.check_true(not exists(select 1 from telemetria where dispositivo_id='SOMPO-ESP32' and equipamento_id is null),'legacy readings attributed');
select pg_temp.check_true((select bool_and(equipamento_id=1) from eventos where dispositivo_id='SOMPO-ESP32' and registro_id is null),'legacy events attributed to their machine');
-- The ID of an archived machine can be reused, but stays unique among live machines.
insert into equipamentos(nome,fk_cliente_id_cliente,fk_fazenda_id_fazenda,dispositivo_id) values('Novo',2,2,'SOMPO-ESP32');
select pg_temp.rejects($q$insert into equipamentos(nome,fk_cliente_id_cliente,fk_fazenda_id_fazenda,dispositivo_id) values('Dup',2,2,'SOMPO-ESP32')$q$,'live device ID unique');
-- A reading without machine (legacy path) is stamped with the live owner of the ID.
insert into telemetria(dispositivo_id,temp_escape) values('SOMPO-ESP32',50);
select pg_temp.check_true((select e.nome='Novo' from telemetria t join equipamentos e on e.id_equipamento=t.equipamento_id where t.temp_escape=50),'new reading goes to live owner');
select pg_temp.check_true((select sum(amostras)=1 from resumo_diario_maquina r join equipamentos e on e.id_equipamento=r.equipamento_id where e.nome='Novo'),'reused ID starts with empty history');
select pg_temp.check_true((select sum(amostras)>=1 from resumo_diario_maquina where equipamento_id=1),'archived machine keeps its history');
select pg_temp.check_true((select u.temp_escape=50 from ultima_telemetria_maquina u join equipamentos e on e.id_equipamento=u.equipamento_id where e.nome='Novo'),'latest reading per machine');
-- Moving a live machine to another ESP32: allowed, revokes the old credential, bumps config.
create temp table v3 as select config_versao from equipamentos where id_equipamento=3;
update equipamentos set dispositivo_id='DEVICE-3' where id_equipamento=3;
select pg_temp.check_true(not exists(select 1 from credenciais_dispositivo where equipamento_id=3),'device change revokes credential');
select pg_temp.check_true((select e.config_versao>v.config_versao from equipamentos e,v3 v where e.id_equipamento=3),'device change bumps config');
select pg_temp.rejects($q$select sincronizar_dispositivo('DEVICE-2','secret-two')$q$,'old device ID no longer syncs');
update equipamentos set dispositivo_id=null where id_equipamento=3;
select pg_temp.check_true((select dispositivo_id is null from equipamentos where id_equipamento=3),'device can be removed');
select pg_temp.check_true(not has_table_privilege('anon','public.resumo_diario_maquina','select')
 and not has_table_privilege('anon','public.ultima_telemetria_maquina','select'),'machine views are server only');
select 'ALL ESP32 SQL ASSERTIONS PASSED' result;
