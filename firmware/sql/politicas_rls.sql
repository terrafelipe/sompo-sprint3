-- SOMPO - Politicas de acesso das tabelas gravadas pelo ESP32
-- Rodar no SQL Editor do painel do Supabase.
--
-- PROBLEMA QUE ISTO RESOLVE
-- A chave publishable fica gravada na flash do ESP32 e sai de la com um
-- esptool e cinco minutos. Sem RLS ela e uma chave de administrador: testamos
-- e, com ela, um DELETE em /rest/v1/eventos apagou a tabela inteira (HTTP 204).
-- Num produto cuja funcao e provar que houve furto, a trilha de evidencia ser
-- apagavel por quem esta furtando anula o produto.
--
-- MODELO DEPOIS DESTE SCRIPT
--   publishable (anon) -> so INSERT em telemetria e eventos. Nao le, nao
--                         altera, nao apaga.
--   secret (service_role) -> ignora RLS por definicao; a API Flask continua
--                         lendo tudo normalmente, sem mudanca no codigo dela.
--
-- E idempotente: pode rodar de novo sem quebrar.

-- ---------------------------------------------------------------------------
-- 1. Liga o RLS (sem politica, o padrao passa a ser negar tudo)
-- ---------------------------------------------------------------------------

alter table public.telemetria    enable row level security;
alter table public.eventos       enable row level security;
alter table public.resumo_diario enable row level security;

-- ---------------------------------------------------------------------------
-- 2. O dispositivo so escreve
-- ---------------------------------------------------------------------------

drop policy if exists "dispositivo insere telemetria" on public.telemetria;
create policy "dispositivo insere telemetria"
  on public.telemetria
  for insert
  to anon
  with check (true);

drop policy if exists "dispositivo insere eventos" on public.eventos;
create policy "dispositivo insere eventos"
  on public.eventos
  for insert
  to anon
  with check (true);

-- Nenhuma politica de select/update/delete para 'anon': com o RLS ligado, a
-- ausencia de politica ja e a negacao. Nao existe "policy de negar" a escrever.

-- ---------------------------------------------------------------------------
-- 3. Tabelas de negocio: o dispositivo nao tem nada que ver com elas
-- ---------------------------------------------------------------------------
-- cliente guarda CNPJ, endereco, telefone e email; sinistros guarda prejuizo;
-- equipamentos guarda valor_segurado. Nada disso e assunto de um sensor - e
-- hoje a chave do ESP32 le todas (conferido: HTTP 200 nas quatro).
--
-- RLS ligado e NENHUMA politica: 'anon' perde o acesso por completo. A API
-- Flask usa a secret key (service_role), que ignora RLS, entao ela nao muda.

alter table public.cliente      enable row level security;
alter table public.equipamentos enable row level security;
alter table public.sinistros    enable row level security;
alter table public.riscos       enable row level security;

-- ---------------------------------------------------------------------------
-- 4. Trilha de evidencia: nem o service_role deveria reescrever o passado
-- ---------------------------------------------------------------------------
-- Impede UPDATE/DELETE em eventos no nivel do banco, para qualquer papel que
-- respeite RLS. O service_role ainda passa por cima (e por isso a secret key
-- nunca pode circular), mas remove a chance de um script da API corromper a
-- trilha por engano.

revoke update, delete on public.eventos from anon, authenticated;

-- ---------------------------------------------------------------------------
-- 5. Indices para as consultas que a API faz
-- ---------------------------------------------------------------------------
-- Toda consulta da API filtra por dispositivo_id e ordena por criado_em desc
-- (ver supabase_client.py). Sem indice isso e varredura de tabela inteira, e a
-- telemetria cresce a cada 30 s por maquina.

create index if not exists idx_telemetria_dispositivo_data
  on public.telemetria (dispositivo_id, criado_em desc);

create index if not exists idx_eventos_dispositivo_data
  on public.eventos (dispositivo_id, criado_em desc);

-- ---------------------------------------------------------------------------
-- 6. Conferencia
-- ---------------------------------------------------------------------------
-- Depois de rodar, estas duas linhas devem mostrar rowsecurity = true e apenas
-- as politicas de INSERT acima.

-- select tablename, rowsecurity from pg_tables
--   where schemaname = 'public' and tablename in ('telemetria','eventos');
-- select tablename, policyname, cmd, roles from pg_policies
--   where schemaname = 'public';
