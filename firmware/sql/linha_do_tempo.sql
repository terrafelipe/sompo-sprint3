-- Apply after frota.sql. Linha do tempo do Painel da maquina: a telemetria agregada por faixa
-- no banco, para 7 dias e periodos longos nao trazerem dezenas de milhares de linhas para a API.
-- Mesma regra do linha_do_tempo.agregar (Python): leitura em (p_inicio, p_fim], a do fim cai na
-- ultima faixa. Somente leitura; so o service_role (a API) executa. Idempotente.
begin;
create or replace function public.linha_do_tempo_faixas(p_equipamento bigint,p_dispositivo text,
 p_inicio timestamptz,p_fim timestamptz,p_minutos int)
returns table(inicio timestamptz,leituras int,motor_ligado boolean,temp_max real,risco text)
language plpgsql stable security invoker set search_path=pg_catalog,public as $$
declare
 v_passo interval; v_n int; v_seg int;
begin
 if p_minutos is null or p_minutos<1 or p_minutos>1440 or p_inicio is null or p_fim is null or p_fim<=p_inicio then
  raise exception 'Janela ou faixa invalida' using errcode='22023';
 end if;
 v_passo:=make_interval(mins=>p_minutos); v_seg:=p_minutos*60;
 v_n:=ceil(extract(epoch from p_fim-p_inicio)/v_seg)::int;
 if v_n>2000 then raise exception 'Faixas demais' using errcode='22023'; end if;
 -- Dois ramos (maquina ou ID do ESP32) em vez de um OR: cada um usa o proprio indice,
 -- inclusive no plano generico que o plpgsql passa a usar depois de algumas chamadas.
 if p_equipamento is not null then
  return query
  with a as (
   select least(v_n-1,floor(extract(epoch from t.criado_em-p_inicio)/v_seg)::int) i,count(*)::int n,
    coalesce(bool_or(t.motor_ligado),false) m,max(t.temp_escape) tm,
    max(case upper(t.nivel_risco) when 'CRITICO' then 2 when 'ALTO' then 2 when 'ATENCAO' then 1 when 'MEDIO' then 1
         when 'SEGURO' then 0 when 'BAIXO' then 0 end) g
   from public.telemetria t
   where t.equipamento_id=p_equipamento and t.criado_em>p_inicio and t.criado_em<=p_fim group by 1)
  select p_inicio+s*v_passo,coalesce(a.n,0),coalesce(a.m,false),a.tm,
   case a.g when 2 then 'CRITICO' when 1 then 'ATENCAO' when 0 then 'SEGURO' end
  from generate_series(0,v_n-1) s left join a on a.i=s order by s;
 else
  return query
  with a as (
   select least(v_n-1,floor(extract(epoch from t.criado_em-p_inicio)/v_seg)::int) i,count(*)::int n,
    coalesce(bool_or(t.motor_ligado),false) m,max(t.temp_escape) tm,
    max(case upper(t.nivel_risco) when 'CRITICO' then 2 when 'ALTO' then 2 when 'ATENCAO' then 1 when 'MEDIO' then 1
         when 'SEGURO' then 0 when 'BAIXO' then 0 end) g
   from public.telemetria t
   where t.dispositivo_id=p_dispositivo and t.criado_em>p_inicio and t.criado_em<=p_fim group by 1)
  select p_inicio+s*v_passo,coalesce(a.n,0),coalesce(a.m,false),a.tm,
   case a.g when 2 then 'CRITICO' when 1 then 'ATENCAO' when 0 then 'SEGURO' end
  from generate_series(0,v_n-1) s left join a on a.i=s order by s;
 end if;
end $$;
revoke all on function public.linha_do_tempo_faixas(bigint,text,timestamptz,timestamptz,int) from public,anon,authenticated;
grant execute on function public.linha_do_tempo_faixas(bigint,text,timestamptz,timestamptz,int) to service_role;
commit;
