-- Apply after usuarios.sql and frota.sql, before deploying the API.
-- Logical deletion: immutable evidence and foreign keys remain intact.
begin;
alter table public.cliente add column if not exists excluido_em timestamptz;
alter table public.fazenda add column if not exists excluido_em timestamptz;
alter table public.usuario add column if not exists excluido_em timestamptz;
alter table public.operadores add column if not exists excluido_em timestamptz;
alter table public.equipamentos add column if not exists excluido_em timestamptz;

-- Serialize short management transactions BEFORE they acquire row locks. This
-- also covers inserts/updates outside the API and the last-administrator check.
create or replace function public.cadastro_serializar() returns trigger
language plpgsql set search_path=pg_catalog,public as $$
begin
 perform pg_advisory_xact_lock(736021,1);
 return null;
end $$;

create or replace function public.cadastro_validar() returns trigger
language plpgsql set search_path=pg_catalog,public as $$
declare dados jsonb:=to_jsonb(NEW); alvo bigint;
begin
 if TG_OP='UPDATE' and to_jsonb(OLD)->>'excluido_em' is not null then
  raise exception 'Cadastro excluido' using errcode='23514';
 end if;
 -- Revoking an authorization must remain possible during deletion.
 if TG_TABLE_NAME='operador_equipamento' and dados->>'ativo'='false' then return NEW; end if;
 alvo:=(dados->>'fk_cliente_id_cliente')::bigint;
 if alvo is not null and not exists(select 1 from public.cliente where id_cliente=alvo and excluido_em is null) then
  raise exception 'Cliente excluido' using errcode='23514';
 end if;
 alvo:=(dados->>'fk_fazenda_id_fazenda')::bigint;
 if alvo is not null and not exists(select 1 from public.fazenda where id_fazenda=alvo and excluido_em is null) then
  raise exception 'Fazenda excluida' using errcode='23514';
 end if;
 alvo:=(dados->>'equipamento_id')::bigint;
 if alvo is not null and not exists(select 1 from public.equipamentos where id_equipamento=alvo and excluido_em is null) then
  raise exception 'Equipamento excluido' using errcode='23514';
 end if;
 alvo:=(dados->>'operador_id')::bigint;
 if alvo is not null and not exists(select 1 from public.operadores where id_operador=alvo and excluido_em is null) then
  raise exception 'Operador excluido' using errcode='23514';
 end if;
 return NEW;
end $$;

do $$ declare t text; begin
 foreach t in array array['cliente','fazenda','usuario','operadores','equipamentos','operador_equipamento','credenciais_dispositivo'] loop
  execute format('drop trigger if exists cadastro_serializar on public.%I',t);
  execute format('create trigger cadastro_serializar before insert or update or delete on public.%I for each statement execute function public.cadastro_serializar()',t);
  execute format('drop trigger if exists cadastro_validar on public.%I',t);
  execute format('create trigger cadastro_validar before insert or update on public.%I for each row execute function public.cadastro_validar()',t);
 end loop;
end $$;

-- Do not touch archived equipment when an operator changes later.
create or replace function public.frota_versao_operador() returns trigger
language plpgsql set search_path=pg_catalog,public as $$
begin
 if NEW.uid is distinct from OLD.uid or NEW.ativo is distinct from OLD.ativo then
  update public.equipamentos set config_versao=config_versao+1
  where excluido_em is null and id_equipamento in
   (select equipamento_id from public.operador_equipamento where operador_id=NEW.id_operador);
 end if;
 return NEW;
end $$;

create or replace function public.excluir_cadastro(p_tipo text,p_id bigint,p_usuario text default null)
returns jsonb language plpgsql security invoker set search_path=pg_catalog,public as $$
declare tabela text; pk text; registro jsonb; deps jsonb:='{}'; n bigint;
begin
 perform pg_advisory_xact_lock(736021,1);
 case p_tipo
  when 'clientes' then tabela:='cliente'; pk:='id_cliente';
  when 'fazendas' then tabela:='fazenda'; pk:='id_fazenda';
  when 'usuarios' then tabela:='usuario'; pk:='id_usuario';
  when 'operadores' then tabela:='operadores'; pk:='id_operador';
  when 'equipamentos' then tabela:='equipamentos'; pk:='id_equipamento';
  else return jsonb_build_object('erro','tipo_invalido');
 end case;
 execute format('select to_jsonb(t) from public.%I t where %I=$1',tabela,pk) into registro using p_id;
 if registro is null then return jsonb_build_object('erro','nao_encontrado'); end if;
 if registro->>'excluido_em' is not null then return jsonb_build_object('ok',true); end if;
 if p_tipo='usuarios' then
  if registro->>'usuario'=p_usuario then return jsonb_build_object('erro','propria_conta'); end if;
  if registro->>'role'='sompo' and (select count(*) from public.usuario where role='sompo' and excluido_em is null)<=1 then
   return jsonb_build_object('erro','ultimo_sompo');
  end if;
 elsif p_tipo='clientes' then
  select count(*) into n from public.fazenda where fk_cliente_id_cliente=p_id and excluido_em is null;
  if n>0 then deps:=deps||jsonb_build_object('fazendas',n); end if;
  select count(*) into n from public.equipamentos where fk_cliente_id_cliente=p_id and excluido_em is null;
  if n>0 then deps:=deps||jsonb_build_object('maquinas',n); end if;
 elsif p_tipo='fazendas' then
  select count(*) into n from public.usuario where fk_fazenda_id_fazenda=p_id and excluido_em is null;
  if n>0 then deps:=deps||jsonb_build_object('usuarios',n); end if;
  select count(*) into n from public.operadores where fk_fazenda_id_fazenda=p_id and excluido_em is null;
  if n>0 then deps:=deps||jsonb_build_object('operadores',n); end if;
  select count(*) into n from public.equipamentos where fk_fazenda_id_fazenda=p_id and excluido_em is null;
  if n>0 then deps:=deps||jsonb_build_object('maquinas',n); end if;
 end if;
 if deps<>'{}'::jsonb then return jsonb_build_object('erro','cadastro_com_vinculos','dependencias',deps); end if;
 if p_tipo='equipamentos' then
  update public.operador_equipamento set ativo=false where equipamento_id=p_id and ativo;
  delete from public.credenciais_dispositivo where equipamento_id=p_id;
  update public.equipamentos set ativo=false,excluido_em=now() where id_equipamento=p_id;
 elsif p_tipo='operadores' then
  update public.operador_equipamento set ativo=false where operador_id=p_id and ativo;
  update public.operadores set ativo=false,excluido_em=now() where id_operador=p_id;
 else
  execute format('update public.%I set excluido_em=now() where %I=$1',tabela,pk) using p_id;
 end if;
 return jsonb_build_object('ok',true);
end $$;

-- Existing fleet RPCs lock equipment rows before writing. Acquire the same
-- management lock first, so sync/provisioning and deletion cannot deadlock.
create or replace function public.provisionar_dispositivo(p_equipamento_id bigint,p_token_hash text)
returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
begin
 perform pg_advisory_xact_lock(736021,1);
 perform 1 from public.equipamentos where id_equipamento=p_equipamento_id
  and excluido_em is null and dispositivo_id is not null and fk_fazenda_id_fazenda is not null for update;
 if not found then raise exception 'Equipamento sem dispositivo/fazenda' using errcode='22023'; end if;
 insert into public.credenciais_dispositivo(equipamento_id,token_hash) values(p_equipamento_id,lower(p_token_hash));
 return jsonb_build_object('equipamento_id',p_equipamento_id);
end $$;

create or replace function public.definir_operadores_equipamento(p_equipamento_id bigint,p_operador_ids bigint[])
returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
declare v_fazenda bigint; v_result jsonb;
begin
 perform pg_advisory_xact_lock(736021,1);
 select fk_fazenda_id_fazenda into v_fazenda from public.equipamentos
 where id_equipamento=p_equipamento_id and excluido_em is null for update;
 if v_fazenda is null or p_operador_ids is null then raise exception 'Equipamento/fazenda/lista invalido' using errcode='22023'; end if;
 if exists(select 1 from unnest(p_operador_ids) id where id is null or not exists(
  select 1 from public.operadores o where o.id_operador=id and o.fk_fazenda_id_fazenda=v_fazenda and o.excluido_em is null)) then
  raise exception 'Operador inexistente ou de outra fazenda' using errcode='23514';
 end if;
 update public.operador_equipamento set ativo=false where equipamento_id=p_equipamento_id
  and ativo and not (operador_id=any(p_operador_ids));
 insert into public.operador_equipamento(equipamento_id,operador_id,ativo)
  select p_equipamento_id,id,true from (select distinct unnest(p_operador_ids) id) ids
  on conflict(equipamento_id,operador_id) do update set ativo=true where not operador_equipamento.ativo;
 select coalesce(jsonb_agg(to_jsonb(v) order by operador_id),'[]'::jsonb) into v_result
  from public.operador_equipamento v where equipamento_id=p_equipamento_id;
 return v_result;
end $$;

create or replace function public.sincronizar_dispositivo(p_dispositivo_id text,p_token text)
returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
declare v_e public.equipamentos%rowtype; v_operadores jsonb;
begin
 perform pg_advisory_xact_lock(736021,1);
 select e.* into v_e from public.equipamentos e join public.credenciais_dispositivo c on c.equipamento_id=e.id_equipamento
 where e.dispositivo_id=p_dispositivo_id and e.excluido_em is null
  and c.token_hash=encode(sha256(convert_to(p_token,'UTF8')),'hex') for update of e;
 if not found then raise exception 'Credencial invalida' using errcode='28000'; end if;
 select coalesce(jsonb_agg(jsonb_build_object('operador_id',o.id_operador,'uid',o.uid) order by o.id_operador),'[]'::jsonb)
 into v_operadores from public.operadores o join public.operador_equipamento oe on oe.operador_id=o.id_operador
 where oe.equipamento_id=v_e.id_equipamento and oe.ativo and o.ativo and v_e.ativo and o.excluido_em is null;
 update public.equipamentos set config_versao_aplicada=v_e.config_versao,config_sincronizada_em=now()
 where id_equipamento=v_e.id_equipamento;
 return jsonb_build_object('equipamento_id',v_e.id_equipamento,'versao',v_e.config_versao,'operadores',v_operadores);
end $$;

create or replace function public.concluir_migracao_dispositivos() returns jsonb
language plpgsql security definer set search_path=pg_catalog,public as $$
begin
 perform pg_advisory_xact_lock(736021,1);
 lock table public.equipamentos in share row exclusive mode;
 if exists(select 1 from public.equipamentos e left join public.credenciais_dispositivo c on c.equipamento_id=e.id_equipamento
  where e.excluido_em is null and e.dispositivo_id is not null and (c.equipamento_id is null or e.config_sincronizada_em is null
   or e.config_versao_aplicada is distinct from e.config_versao)) then
  raise exception 'Todos dispositivos precisam credencial e configuracao sincronizada' using errcode='23514';
 end if;
 drop policy if exists "anon insere telemetria" on public.telemetria;
 drop policy if exists "anon insere eventos" on public.eventos;
 revoke insert on public.telemetria,public.eventos from anon,authenticated;
 return jsonb_build_object('ok',true);
end $$;
revoke all on function public.excluir_cadastro(text,bigint,text) from public,anon,authenticated;
grant execute on function public.excluir_cadastro(text,bigint,text) to service_role;
grant select,update on public.cliente,public.fazenda,public.usuario to service_role;
grant delete on public.credenciais_dispositivo to service_role;
revoke all on function public.cadastro_serializar(),public.cadastro_validar() from public,anon,authenticated;
commit;
