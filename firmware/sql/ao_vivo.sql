-- Apply after esp32_por_maquina.sql. Modo ao vivo: o painel grava ate quando a
-- placa deve mandar telemetria a cada 2 s; a placa le o intervalo na resposta de
-- registrar_dispositivo. Idempotente.
begin;
alter table public.equipamentos add column if not exists ao_vivo_ate timestamptz;

create or replace function public.registrar_dispositivo(p_dispositivo_id text,p_token text,p_categoria text,p_registro jsonb)
returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
declare
 v_e public.equipamentos%rowtype; v_recibo public.recibos_dispositivo%rowtype;
 v_t public.telemetria%rowtype; v_ev public.eventos%rowtype; v_op public.registros_operacao%rowtype;
 v_id uuid; v_operador bigint; v_sessao uuid; v_now timestamptz:=clock_timestamp(); v_data jsonb;
begin
 select e.* into v_e from public.equipamentos e join public.credenciais_dispositivo c on c.equipamento_id=e.id_equipamento
 where e.dispositivo_id=p_dispositivo_id and c.token_hash=encode(sha256(convert_to(p_token,'UTF8')),'hex');
 if not found then raise exception 'Credencial invalida' using errcode='28000'; end if;
 if p_categoria is null or p_categoria not in ('telemetria','eventos','operacao') or jsonb_typeof(p_registro) is distinct from 'object' then
  raise exception 'Categoria/registro invalido' using errcode='22023';
 end if;
 v_id:=(p_registro->>'registro_id')::uuid;
 v_operador:=(p_registro->>'operador_id')::bigint;
 v_sessao:=(p_registro->>'sessao_id')::uuid;
 if v_id is null or (p_registro->>'boot_id')::uuid is null or (p_registro->>'config_versao')::bigint is null
  or (p_registro->>'config_versao')::bigint<1 or (p_registro->>'sequencia')::bigint is null
  or (p_registro->>'sequencia')::bigint<0 or (p_registro->>'uptime_ms')::bigint is null
  or (p_registro->>'uptime_ms')::bigint<0 then
  raise exception 'Identidade/ordem do registro obrigatoria' using errcode='22023';
 end if;
 if (p_registro->>'equipamento_id') is not null and (p_registro->>'equipamento_id')::bigint<>v_e.id_equipamento
  or (p_registro->>'dispositivo_id') is not null and p_registro->>'dispositivo_id'<>p_dispositivo_id then
  raise exception 'Equipamento alheio a credencial' using errcode='42501';
 end if;
 if v_operador is not null and not exists(select 1 from public.operadores o
  join public.operador_equipamento oe on oe.operador_id=o.id_operador
  where o.id_operador=v_operador and o.fk_fazenda_id_fazenda=v_e.fk_fazenda_id_fazenda and oe.equipamento_id=v_e.id_equipamento) then
  raise exception 'Operador sem vinculo historico com o equipamento' using errcode='23514';
 end if;
 -- Serializes competing deliveries of a UUID, including different categories.
 perform pg_advisory_xact_lock(hashtextextended(v_id::text,0));
 select * into v_recibo from public.recibos_dispositivo where registro_id=v_id;
 if found then
  if v_recibo.equipamento_id<>v_e.id_equipamento or v_recibo.categoria<>p_categoria or v_recibo.payload<>p_registro then
   raise exception 'UUID reutilizado com payload conflitante' using errcode='23505';
  end if;
  return jsonb_build_object('ok',true,'duplicado',true,
   'telemetria_ms',case when v_e.ao_vivo_ate>v_now then 2000 else 10000 end);
 end if;
 if v_sessao is not null then
  perform pg_advisory_xact_lock(hashtextextended(v_sessao::text,1));
  if exists(select 1 from public.registros_operacao where sessao_id=v_sessao
   and (equipamento_id<>v_e.id_equipamento or operador_id is distinct from v_operador)) then
   raise exception 'Sessao de outro equipamento/operador' using errcode='23514';
  end if;
 end if;
 v_data:=p_registro||jsonb_build_object('equipamento_id',v_e.id_equipamento,'dispositivo_id',p_dispositivo_id,
  'recebido_em',v_now,'criado_em',coalesce((p_registro->>'ocorrido_em')::timestamptz,v_now));
 -- Explicit column lists: unknown JSON keys cannot become identifiers or SQL.
 if p_categoria='telemetria' then
  v_t:=jsonb_populate_record(null::public.telemetria,v_data);
  insert into public.telemetria(dispositivo_id,criado_em,temp_escape,temp_ambiente,umidade_ar,chama_detectada,
   vibracao,motor_ligado,capo_aberto,tanque_aberto,operador_autorizado,nivel_risco,registro_id,equipamento_id,
   operador_id,sessao_id,uid,config_versao,ocorrido_em,recebido_em,boot_id,sequencia,uptime_ms)
  values(v_t.dispositivo_id,v_t.criado_em,v_t.temp_escape,v_t.temp_ambiente,v_t.umidade_ar,v_t.chama_detectada,
   v_t.vibracao,v_t.motor_ligado,v_t.capo_aberto,v_t.tanque_aberto,v_t.operador_autorizado,v_t.nivel_risco,
   v_t.registro_id,v_t.equipamento_id,v_t.operador_id,v_t.sessao_id,v_t.uid,v_t.config_versao,
   v_t.ocorrido_em,v_t.recebido_em,v_t.boot_id,v_t.sequencia,v_t.uptime_ms);
 elsif p_categoria='eventos' then
  v_ev:=jsonb_populate_record(null::public.eventos,v_data);
  insert into public.eventos(dispositivo_id,criado_em,tipo,severidade,temp_escape,detalhes,registro_id,equipamento_id,
   operador_id,sessao_id,uid,config_versao,ocorrido_em,recebido_em,boot_id,sequencia,uptime_ms)
  values(v_ev.dispositivo_id,v_ev.criado_em,v_ev.tipo,v_ev.severidade,v_ev.temp_escape,v_ev.detalhes,
   v_ev.registro_id,v_ev.equipamento_id,v_ev.operador_id,v_ev.sessao_id,v_ev.uid,v_ev.config_versao,
   v_ev.ocorrido_em,v_ev.recebido_em,v_ev.boot_id,v_ev.sequencia,v_ev.uptime_ms);
 else
  v_op:=jsonb_populate_record(null::public.registros_operacao,v_data);
  insert into public.registros_operacao values(v_op.*);
 end if;
 insert into public.recibos_dispositivo values(v_id,v_e.id_equipamento,p_categoria,p_registro);
 return jsonb_build_object('ok',true,'duplicado',false,
  'telemetria_ms',case when v_e.ao_vivo_ate>v_now then 2000 else 10000 end);
end $$;
revoke all on function public.registrar_dispositivo(text,text,text,jsonb) from public;
grant execute on function public.registrar_dispositivo(text,text,text,jsonb) to anon,authenticated,service_role;
commit;
