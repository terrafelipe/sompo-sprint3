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
 v_passo interval; v_n int;
begin
 if p_minutos is null or p_minutos<1 or p_minutos>1440 or p_inicio is null or p_fim is null or p_fim<=p_inicio then
  raise exception 'Janela ou faixa invalida' using errcode='22023';
 end if;
 v_passo:=make_interval(mins=>p_minutos);
 v_n:=ceil(extract(epoch from p_fim-p_inicio)/(p_minutos*60))::int;
 if v_n>2000 then raise exception 'Faixas demais' using errcode='22023'; end if;
 return query
 with l as (
  select least(v_n-1,floor(extract(epoch from t.criado_em-p_inicio)/(p_minutos*60))::int) i,
   t.temp_escape,t.motor_ligado m,
   case upper(t.nivel_risco) when 'CRITICO' then 2 when 'ALTO' then 2 when 'ATENCAO' then 1 when 'MEDIO' then 1
    when 'SEGURO' then 0 when 'BAIXO' then 0 end g,upper(t.nivel_risco) r
  from public.telemetria t
  where ((p_equipamento is not null and t.equipamento_id=p_equipamento) or (p_equipamento is null and t.dispositivo_id=p_dispositivo))
   and t.criado_em>p_inicio and t.criado_em<=p_fim
 ), a as (
  select i,count(*)::int n,coalesce(bool_or(m),false) m,max(temp_escape) tm,
   (array_agg(r order by g desc nulls last))[1] r,max(g) g
  from l group by i
 )
 select p_inicio+s*v_passo,coalesce(a.n,0),coalesce(a.m,false),a.tm,case when a.g is null then null else a.r end
 from generate_series(0,v_n-1) s left join a on a.i=s order by s;
end $$;
revoke all on function public.linha_do_tempo_faixas(bigint,text,timestamptz,timestamptz,int) from public,anon,authenticated;
grant execute on function public.linha_do_tempo_faixas(bigint,text,timestamptz,timestamptz,int) to service_role;
commit;
