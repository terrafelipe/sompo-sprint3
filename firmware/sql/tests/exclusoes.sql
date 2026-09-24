-- Runs after the fleet assertions, using their historical operation and tokens.
insert into usuario(usuario,senha,role,fk_fazenda_id_fazenda) values
 ('admin1','test','sompo',null),('admin2','test','sompo',null),('gestor1','test','gestor_fazenda',1);
create temp table evidence_before as select
 (select count(*) from eventos) eventos,(select count(*) from telemetria) telemetria,
 (select count(*) from registros_operacao) operacoes;
select pg_temp.check_true(not has_function_privilege('anon','excluir_cadastro(text,bigint,text)','EXECUTE'),'anonymous cannot delete');
select pg_temp.check_true(not has_function_privilege('authenticated','excluir_cadastro(text,bigint,text)','EXECUTE'),'browser cannot delete directly');
select pg_temp.check_true((excluir_cadastro('usuarios',1,'admin1')->>'erro')='propria_conta','cannot delete self');
select pg_temp.check_true((excluir_cadastro('usuarios',2,'admin1')->>'ok')::boolean,'delete other administrator');
select pg_temp.check_true((excluir_cadastro('usuarios',1,null)->>'erro')='ultimo_sompo','keep last administrator');
select pg_temp.check_true((excluir_cadastro('clientes',1,null)->>'erro')='cadastro_com_vinculos','customer dependency guard');
select pg_temp.check_true((excluir_cadastro('fazendas',1,null)->'dependencias'->>'usuarios')='1','farm reports linked users');
select pg_temp.check_true((select excluido_em is null from fazenda where id_fazenda=1),'conflict does not archive farm');
select pg_temp.check_true((excluir_cadastro('equipamentos',999,null)->>'erro')='nao_encontrado','missing record');
-- A failure after revocation must roll back both the credential and the links.
create function pg_temp.fail_archive() returns trigger language plpgsql as $$
begin if NEW.excluido_em is not null then raise exception 'Injected failure'; end if; return NEW; end $$;
create trigger fail_archive before update on equipamentos for each row execute function pg_temp.fail_archive();
select pg_temp.rejects($q$select excluir_cadastro('equipamentos',1,null)$q$,'injected failure');
select pg_temp.check_true(exists(select 1 from credenciais_dispositivo where equipamento_id=1),'failed archive retains credential');
select pg_temp.check_true((select ativo from operador_equipamento where equipamento_id=1 and operador_id=1),'failed archive retains authorization');
drop trigger fail_archive on equipamentos;
-- Archive a machine with immutable evidence and authorizations.
set role service_role;
select pg_temp.check_true((excluir_cadastro('equipamentos',1,null)->>'ok')::boolean,'service can archive machine');
reset role;
select pg_temp.check_true((excluir_cadastro('equipamentos',1,null)->>'ok')::boolean,'repeat deletion succeeds');
select pg_temp.check_true(not exists(select 1 from credenciais_dispositivo where equipamento_id=1),'credential revoked');
select pg_temp.rejects($q$select sincronizar_dispositivo('SOMPO-ESP32','secret-one')$q$,'deleted machine token rejected');
select pg_temp.rejects($q$select provisionar_dispositivo(1,repeat('a',64))$q$,'cannot reprovision archived machine');
select pg_temp.rejects($q$update equipamentos set ativo=true where id_equipamento=1$q$,'cannot reactivate machine');
select pg_temp.rejects($q$select definir_operadores_equipamento(1,array[1]::bigint[])$q$,'cannot authorize archived machine');
select pg_temp.check_true((excluir_cadastro('operadores',1,null)->>'ok')::boolean,'delete operator linked to archived machine');
select pg_temp.check_true((select operador_nome='A' from sessoes_operacao limit 1),'historical operator name retained');
-- A live machine loses an archived operator at its next sync.
select definir_operadores_equipamento(3,array[2]::bigint[]);
create temp table live_version as select config_versao from equipamentos where id_equipamento=3;
select pg_temp.check_true((excluir_cadastro('operadores',2,null)->>'ok')::boolean,'delete live operator');
select pg_temp.check_true((select e.config_versao>v.config_versao from equipamentos e,live_version v where e.id_equipamento=3),'operator deletion bumps config');
select pg_temp.check_true(sincronizar_dispositivo('DEVICE-2','secret-two')->'operadores'='[]'::jsonb,'archived operator not synchronized');
select concluir_migracao_dispositivos();
select pg_temp.rejects($q$select definir_operadores_equipamento(3,array[2]::bigint[])$q$,'cannot reauthorize deleted operator');
-- The badge of a deleted operator can be issued to someone new, but stays unique among live operators.
insert into operadores(nome,uid,fk_fazenda_id_fazenda) values('Reuso','12345678',2);
select pg_temp.check_true((select count(*)=1 from operadores where uid='12345678' and excluido_em is null),'deleted operator UID reusable');
select pg_temp.rejects($q$insert into operadores(nome,uid,fk_fazenda_id_fazenda) values('Dup','12-34-56-78',2)$q$,'live operator UID stays unique');
select pg_temp.check_true((excluir_cadastro('usuarios',3,null)->>'ok')::boolean,'archive farm login');
select pg_temp.check_true((excluir_cadastro('equipamentos',2,null)->>'ok')::boolean,'archive remaining machine');
select pg_temp.check_true((excluir_cadastro('fazendas',1,null)->>'ok')::boolean,'archive empty farm');
select pg_temp.rejects($q$insert into usuario(usuario,senha,role,fk_fazenda_id_fazenda) values('bad','test','gestor_fazenda',1)$q$,'no new users in deleted farm');
select pg_temp.rejects($q$insert into operadores(nome,uid,fk_fazenda_id_fazenda) values('bad','AAAAAAAA',1)$q$,'no new operators in deleted farm');
select pg_temp.check_true((excluir_cadastro('clientes',1,null)->>'ok')::boolean,'archive customer after dependencies');
select pg_temp.rejects($q$insert into fazenda(id_fazenda,nome,fk_cliente_id_cliente) values(99,'bad',1)$q$,'no new farms for deleted customer');
select pg_temp.check_true((select b.eventos=(select count(*) from eventos) and b.telemetria=(select count(*) from telemetria)
 and b.operacoes=(select count(*) from registros_operacao) from evidence_before b),'all historical evidence preserved');
select 'ALL DELETION SQL ASSERTIONS PASSED' result;
