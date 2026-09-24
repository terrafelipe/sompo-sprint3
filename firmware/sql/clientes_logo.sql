-- SOMPO: logo opcional do cliente (circulo antes do nome na aba Clientes).
-- Rodar depois de exclusoes.sql e esp32_por_maquina.sql, no SQL Editor do Supabase,
-- e ANTES de publicar a API que le/grava logo_url. Aditivo e repetivel.
begin;
alter table public.cliente add column if not exists logo_url text;

-- O link vira <img src> no painel: so https e ate 500 caracteres (a API valida o mesmo).
do $$ begin
 if not exists(select 1 from pg_constraint where conrelid='public.cliente'::regclass
  and conname='cliente_logo_url_https') then
  alter table public.cliente add constraint cliente_logo_url_https
   check (logo_url is null or (logo_url ~ '^https://' and char_length(logo_url) <= 500));
 end if;
end $$;
commit;
