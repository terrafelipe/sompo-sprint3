\set ON_ERROR_STOP on
create function pg_temp.check_true(ok boolean, label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAIL: %',label; end if; end $$;
create function pg_temp.rejects(statement text, label text) returns void language plpgsql as $$
begin
 begin execute statement; exception when others then return; end;
 raise exception 'FAIL accepted invalid action: %',label;
end $$;
select pg_temp.check_true(to_regclass('public.operadores') is not null,'migration creates fleet schema');
select pg_temp.check_true((select count(*)=4 from equipamentos),'legacy equipment preserved');
select pg_temp.check_true((select count(*)=1 from telemetria),'legacy telemetry preserved');
select pg_temp.check_true((select count(*)=1 from eventos),'legacy events preserved');
select pg_temp.check_true((select count(*)=1 from equipamentos where dispositivo_id is not null),'only documented device mapped');
select pg_temp.check_true((select fk_fazenda_id_fazenda is null from equipamentos where id_equipamento=4),'ambiguous farm untouched');
select pg_temp.check_true((select operador_id is null and registro_id is null from eventos limit 1),'legacy history unattributed');
update equipamentos set dispositivo_id='DEVICE-2' where id_equipamento=3;
select pg_temp.rejects($q$update equipamentos set dispositivo_id='DEVICE-2' where id_equipamento=2$q$,'unique device');
select pg_temp.rejects($q$update equipamentos set dispositivo_id='NEW' where id_equipamento=1$q$,'device permanent');
select pg_temp.rejects($q$update equipamentos set fk_fazenda_id_fazenda=2 where id_equipamento=1$q$,'farm permanent');
select pg_temp.rejects($q$update equipamentos set fk_cliente_id_cliente=2 where id_equipamento=1$q$,'equipment customer matches farm');
insert into operadores(nome,uid,fk_fazenda_id_fazenda) values ('A','aa:bb:cc:dd',1),('B','12345678',2);
select pg_temp.check_true((select uid='AABBCCDD' from operadores where id_operador=1),'UID normalized');
select pg_temp.rejects($q$insert into operadores(nome,uid,fk_fazenda_id_fazenda) values ('C','AA-BB-CC-DD',1)$q$,'UID unique');
select pg_temp.rejects($q$insert into operadores(nome,uid,fk_fazenda_id_fazenda) values ('C','xyz12345',1)$q$,'UID format');
select pg_temp.rejects($q$update operadores set fk_fazenda_id_fazenda=2 where id_operador=1$q$,'operator farm permanent');
select pg_temp.rejects($q$select definir_operadores_equipamento(1,array[2]::bigint[])$q$,'cross-farm authorization');
select definir_operadores_equipamento(1,array[1]::bigint[]);
select provisionar_dispositivo(1,encode(sha256(convert_to('secret-one','UTF8')),'hex'));
select provisionar_dispositivo(3,encode(sha256(convert_to('secret-two','UTF8')),'hex'));
select pg_temp.rejects($q$select sincronizar_dispositivo('SOMPO-ESP32','wrong')$q$,'wrong token');
select pg_temp.rejects($q$select sincronizar_dispositivo('SOMPO-ESP32',null)$q$,'null token');
select pg_temp.check_true((sincronizar_dispositivo('SOMPO-ESP32','secret-one')->'operadores')='[{"operador_id":1,"uid":"AABBCCDD"}]'::jsonb,'authorized config');
create temp table version_before as select config_versao from equipamentos where id_equipamento=1;
update operadores set ativo=false where id_operador=1;
select pg_temp.check_true((select e.config_versao>v.config_versao from equipamentos e,version_before v where e.id_equipamento=1),'revocation increments version');
select pg_temp.check_true((sincronizar_dispositivo('SOMPO-ESP32','secret-one')->'operadores')='[]'::jsonb,'revoked operator absent');
-- Old cached authorization is historical evidence, even after revocation.
select pg_temp.check_true(registrar_dispositivo('SOMPO-ESP32','secret-one','operacao',
 '{"registro_id":"10000000-0000-0000-0000-000000000001","operador_id":1,"sessao_id":"20000000-0000-0000-0000-000000000001","tipo":"inicio","uid":"AABBCCDD","config_versao":1,"ocorrido_em":"2026-09-16T10:00:00Z","boot_id":"30000000-0000-0000-0000-000000000001","sequencia":1,"uptime_ms":10}')='{"ok":true,"duplicado":false}'::jsonb,'historical cached start');
select pg_temp.check_true(registrar_dispositivo('SOMPO-ESP32','secret-one','operacao',
 '{"registro_id":"10000000-0000-0000-0000-000000000001","operador_id":1,"sessao_id":"20000000-0000-0000-0000-000000000001","tipo":"inicio","uid":"AABBCCDD","config_versao":1,"ocorrido_em":"2026-09-16T10:00:00Z","boot_id":"30000000-0000-0000-0000-000000000001","sequencia":1,"uptime_ms":10}')='{"ok":true,"duplicado":true}'::jsonb,'retry idempotent');
select registrar_dispositivo('SOMPO-ESP32','secret-one','operacao',
 '{"registro_id":"10000000-0000-0000-0000-000000000002","operador_id":1,"sessao_id":"20000000-0000-0000-0000-000000000001","tipo":"fim","motivo":"reinicio","config_versao":1,"ocorrido_em":null,"boot_id":"30000000-0000-0000-0000-000000000002","sequencia":1,"uptime_ms":1}');
select pg_temp.check_true((select status='interrompida' and fim_em is null and inicio_em='2026-09-16T10:00:00Z' from sessoes_operacao),'interrupted without invented NTP time');
select pg_temp.rejects($q$update registros_operacao set motivo='changed'$q$,'immutable lifecycle');
select pg_temp.rejects($q$delete from eventos$q$,'immutable events');
select pg_temp.rejects($q$select registrar_dispositivo('SOMPO-ESP32','secret-one','operacao','{"registro_id":"10000000-0000-0000-0000-000000000001","tipo":"tentativa_negada","config_versao":1,"boot_id":"30000000-0000-0000-0000-000000000001","sequencia":1,"uptime_ms":10}')$q$,'conflicting UUID');
select pg_temp.rejects($q$select registrar_dispositivo('SOMPO-ESP32','secret-one','eventos','{"registro_id":"40000000-0000-0000-0000-000000000001","equipamento_id":3,"tipo":"incendio","config_versao":1,"boot_id":"30000000-0000-0000-0000-000000000001","sequencia":2,"uptime_ms":10}')$q$,'foreign equipment');
select pg_temp.rejects($q$select registrar_dispositivo('SOMPO-ESP32','secret-one','eventos','{"registro_id":"40000000-0000-0000-0000-000000000001","operador_id":2,"tipo":"incendio","config_versao":1,"boot_id":"30000000-0000-0000-0000-000000000001","sequencia":2,"uptime_ms":10}')$q$,'foreign operator');
select pg_temp.rejects($q$select registrar_dispositivo('SOMPO-ESP32','secret-one','eventos','{"registro_id":"40000000-0000-0000-0000-000000000001","operador_id":999,"tipo":"incendio","config_versao":1,"boot_id":"30000000-0000-0000-0000-000000000001","sequencia":2,"uptime_ms":10}')$q$,'missing operator');
select registrar_dispositivo('SOMPO-ESP32','secret-one','eventos','{"registro_id":"40000000-0000-0000-0000-000000000001","tipo":"incendio","config_versao":1,"boot_id":"30000000-0000-0000-0000-000000000001","sequencia":2,"uptime_ms":10,"sql":"drop table operadores"}');
select registrar_dispositivo('SOMPO-ESP32','secret-one','telemetria','{"registro_id":"50000000-0000-0000-0000-000000000001","temp_escape":101,"config_versao":1,"boot_id":"30000000-0000-0000-0000-000000000001","sequencia":3,"uptime_ms":11}');
select pg_temp.check_true((select ocorrido_em is null and criado_em=recebido_em and temp_escape=101 from telemetria where registro_id is not null),'telemetry received fallback preserves null occurrence');
select pg_temp.check_true(not has_table_privilege('anon','credenciais_dispositivo','SELECT'),'credentials private');
select pg_temp.check_true(not has_function_privilege('anon','provisionar_dispositivo(bigint,text)','EXECUTE'),'provision service only');
select pg_temp.check_true(not has_function_privilege('authenticated','definir_operadores_equipamento(bigint,bigint[])','EXECUTE'),'management service only');
select pg_temp.rejects($q$select concluir_migracao_dispositivos()$q$,'activation blocks unsynchronized device');
select sincronizar_dispositivo('DEVICE-2','secret-two');
select concluir_migracao_dispositivos();
select pg_temp.check_true(not exists(select 1 from pg_policies where tablename in ('telemetria','eventos') and cmd='INSERT'),'legacy policies removed only at activation');
set role anon;
select sincronizar_dispositivo('SOMPO-ESP32','secret-one');
reset role;
select 'ALL FLEET SQL ASSERTIONS PASSED' as result;
