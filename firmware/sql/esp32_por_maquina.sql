-- SOMPO: ID do ESP32 editavel e reaproveitavel; o historico de leituras acompanha a MAQUINA.
-- Rodar depois de frota.sql, exclusoes.sql e mapa_ocorrencias.sql, no SQL Editor do Supabase,
-- e ANTES de publicar a API que consulta por maquina. Repetivel.
begin;

-- 1. So na primeira vez (enquanto o ID ainda e unico entre TODAS as maquinas): cada leitura
--    antiga sem maquina ganha a maquina dona do ID hoje, que e a mesma que o painel ja mostrava.
--    A evidencia continua imutavel para a aplicacao; o gatilho so desliga nesta transacao.
do $$ begin
 if to_regclass('public.equipamentos_dispositivo_unique') is not null then
  update public.telemetria t set equipamento_id=e.id_equipamento from public.equipamentos e
   where t.equipamento_id is null and e.dispositivo_id=t.dispositivo_id;
  alter table public.eventos disable trigger frota_eventos_imutaveis;
  update public.eventos ev set equipamento_id=e.id_equipamento from public.equipamentos e
   where ev.equipamento_id is null and e.dispositivo_id=ev.dispositivo_id;
  alter table public.eventos enable trigger frota_eventos_imutaveis;
  drop index public.equipamentos_dispositivo_unique;
 end if;
end $$;
-- O ID segue unico, mas so entre maquinas nao excluidas.
create unique index if not exists equipamentos_dispositivo_vivo_uk
 on public.equipamentos(dispositivo_id) where excluido_em is null;

-- 2. Leitura nova sem maquina (caminho antigo, sem token) ganha a maquina dona do ID agora.
create or replace function public.leitura_da_maquina() returns trigger
language plpgsql security definer set search_path=pg_catalog,public as $$
begin
 if NEW.equipamento_id is null then
  select id_equipamento into NEW.equipamento_id from public.equipamentos
   where dispositivo_id=NEW.dispositivo_id and excluido_em is null;
 end if;
 return NEW;
end $$;
drop trigger if exists leitura_da_maquina on public.telemetria;
create trigger leitura_da_maquina before insert on public.telemetria
 for each row execute function public.leitura_da_maquina();
drop trigger if exists leitura_da_maquina on public.eventos;
create trigger leitura_da_maquina before insert on public.eventos
 for each row execute function public.leitura_da_maquina();

-- 3. Mesmas regras de frota.sql, sem a trava de remanejamento; trocar o ESP32 sobe a versao
--    da configuracao.
create or replace function public.frota_validar_equipamento() returns trigger
language plpgsql set search_path=pg_catalog,public as $$
begin
 if TG_OP='UPDATE' then
  if OLD.fk_fazenda_id_fazenda is not null and NEW.fk_fazenda_id_fazenda is distinct from OLD.fk_fazenda_id_fazenda then
   raise exception 'A fazenda do equipamento nao pode ser transferida' using errcode='23514';
  end if;
  if NEW.ativo is distinct from OLD.ativo or NEW.dispositivo_id is distinct from OLD.dispositivo_id then
   NEW.config_versao:=OLD.config_versao+1;
  end if;
 end if;
 if NEW.dispositivo_id is not null and (btrim(NEW.dispositivo_id)='' or NEW.fk_fazenda_id_fazenda is null) then
  raise exception 'Dispositivo exige identificador e fazenda' using errcode='23514';
 end if;
 if NEW.fk_fazenda_id_fazenda is not null and not exists(
  select 1 from public.fazenda where id_fazenda=NEW.fk_fazenda_id_fazenda
   and fk_cliente_id_cliente is not distinct from NEW.fk_cliente_id_cliente) then
  raise exception 'Cliente do equipamento difere da fazenda' using errcode='23514';
 end if;
 return NEW;
end $$;

-- 4. Trocar ou tirar o ESP32 revoga a credencial da maquina: o aparelho novo precisa de outra.
create or replace function public.frota_dispositivo_trocado() returns trigger
language plpgsql security definer set search_path=pg_catalog,public as $$
begin
 delete from public.credenciais_dispositivo where equipamento_id=NEW.id_equipamento;
 return NEW;
end $$;
drop trigger if exists frota_dispositivo_trocado on public.equipamentos;
create trigger frota_dispositivo_trocado after update of dispositivo_id on public.equipamentos
 for each row when (OLD.dispositivo_id is distinct from NEW.dispositivo_id)
 execute function public.frota_dispositivo_trocado();

-- 5. Views por maquina (a API consulta estas; as antigas, por ID do ESP32, ficam para o legado).
create or replace view public.ultima_telemetria_maquina with(security_invoker=true) as
 select distinct on(equipamento_id) * from public.telemetria where equipamento_id is not null
 order by equipamento_id,criado_em desc,id desc;
create or replace view public.resumo_diario_maquina with(security_invoker=true) as
select
  equipamento_id,
  (criado_em at time zone 'America/Sao_Paulo')::date as dia,
  count(*)                              as amostras,
  round(avg(temp_escape)::numeric, 1)   as temp_escape_media,
  max(temp_escape)                      as temp_escape_max,
  round(avg(temp_ambiente)::numeric, 1) as temp_ambiente_media,
  round(avg(vibracao)::numeric, 3)      as vibracao_media,
  max(vibracao)                         as vibracao_max,
  bool_or(chama_detectada)              as houve_chama,
  bool_or(capo_aberto)                  as houve_capo_aberto
from public.telemetria
where equipamento_id is not null
group by equipamento_id, (criado_em at time zone 'America/Sao_Paulo')::date;

revoke all on public.ultima_telemetria_maquina,public.resumo_diario_maquina from public,anon,authenticated;
grant select on public.ultima_telemetria_maquina,public.resumo_diario_maquina to service_role;
revoke all on function public.leitura_da_maquina(),public.frota_dispositivo_trocado(),
 public.frota_validar_equipamento() from public,anon,authenticated;
commit;
