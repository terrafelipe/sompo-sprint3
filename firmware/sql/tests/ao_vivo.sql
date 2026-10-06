-- Modo ao vivo: o painel liga por equipamentos.ao_vivo_ate e a placa le o intervalo
-- na resposta de registrar_dispositivo. Maquina propria (LIVE-1) para nao depender
-- do estado deixado pelos outros testes.
insert into equipamentos(nome,fk_cliente_id_cliente,fk_fazenda_id_fazenda,dispositivo_id) values('Ao vivo',2,2,'LIVE-1');
select provisionar_dispositivo((select id_equipamento from equipamentos where dispositivo_id='LIVE-1' and excluido_em is null),
 encode(sha256(convert_to('secret-live','UTF8')),'hex'));
create temp table vv as select config_versao from equipamentos where dispositivo_id='LIVE-1' and excluido_em is null;
select pg_temp.check_true((registrar_dispositivo('LIVE-1','secret-live','telemetria',
 '{"registro_id":"60000000-0000-0000-0000-000000000001","config_versao":1,"boot_id":"30000000-0000-0000-0000-000000000009","sequencia":1,"uptime_ms":10,"temp_escape":40}')
 ->>'telemetria_ms')::int=10000,'normal interval without live mode');
update equipamentos set ao_vivo_ate=now()+interval '2 hours' where dispositivo_id='LIVE-1' and excluido_em is null;
select pg_temp.check_true((registrar_dispositivo('LIVE-1','secret-live','eventos',
 '{"registro_id":"60000000-0000-0000-0000-000000000002","tipo":"chama_detectada","config_versao":1,"boot_id":"30000000-0000-0000-0000-000000000009","sequencia":2,"uptime_ms":20}')
 ->>'telemetria_ms')::int=2000,'live interval while ao_vivo_ate is in the future');
select pg_temp.check_true((select (r->>'duplicado')::boolean and (r->>'telemetria_ms')::int=2000 from (select registrar_dispositivo('LIVE-1','secret-live','eventos',
 '{"registro_id":"60000000-0000-0000-0000-000000000002","tipo":"chama_detectada","config_versao":1,"boot_id":"30000000-0000-0000-0000-000000000009","sequencia":2,"uptime_ms":20}') r) x),
 'duplicate delivery also carries the interval');
select pg_temp.check_true((select e.config_versao=v.config_versao from equipamentos e,vv v where e.dispositivo_id='LIVE-1' and e.excluido_em is null),
 'live mode does not bump config version');
update equipamentos set ao_vivo_ate=now()-interval '1 second' where dispositivo_id='LIVE-1' and excluido_em is null;
select pg_temp.check_true((registrar_dispositivo('LIVE-1','secret-live','telemetria',
 '{"registro_id":"60000000-0000-0000-0000-000000000003","config_versao":1,"boot_id":"30000000-0000-0000-0000-000000000009","sequencia":3,"uptime_ms":30}')
 ->>'telemetria_ms')::int=10000,'expired live mode falls back to normal');
select pg_temp.rejects($q$select registrar_dispositivo('LIVE-1','wrong','telemetria','{"registro_id":"60000000-0000-0000-0000-000000000004","config_versao":1,"boot_id":"30000000-0000-0000-0000-000000000009","sequencia":4,"uptime_ms":40}')$q$,
 'bad credential still rejected');
select 'ALL AO VIVO SQL ASSERTIONS PASSED' result;
