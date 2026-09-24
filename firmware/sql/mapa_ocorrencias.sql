-- SOMPO: mapa da carteira (coordenadas da fazenda).
-- Aditivo e repetivel: so acrescenta colunas e regras; nao apaga nem altera dados.
-- Rodar depois de frota.sql e exclusoes.sql, no SQL Editor do Supabase.
begin;

-- Coordenadas opcionais (graus decimais). Fazenda sem coordenada fica fora do mapa.
alter table public.fazenda
 add column if not exists latitude numeric(9,6),
 add column if not exists longitude numeric(9,6);
alter table public.fazenda drop constraint if exists fazenda_latitude_valida;
alter table public.fazenda add constraint fazenda_latitude_valida check (latitude between -90 and 90);
alter table public.fazenda drop constraint if exists fazenda_longitude_valida;
alter table public.fazenda add constraint fazenda_longitude_valida check (longitude between -180 and 180);
alter table public.fazenda drop constraint if exists fazenda_coordenadas_juntas;
alter table public.fazenda add constraint fazenda_coordenadas_juntas check ((latitude is null) = (longitude is null));

commit;
