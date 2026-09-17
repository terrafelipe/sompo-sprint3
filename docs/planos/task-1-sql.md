# Task 1 — SQL

Leia o contrato em equipamentos-operadores.md (mesma pasta). Implemente somente firmware/sql/frota.sql, firmware/sql/frota_ativar.sql se necessário, firmware/sql/tests/* e documentação de teste SQL. Não altere Python, UI ou firmware C++.

Migração aditiva idempotente para schema real existente (ver scripts atuais; equipamentos já existe e pertence cliente). Adicione as tabelas/campos/view/RPC do contrato, índices e RLS. Não rode preparar_supabase.sql em produção (ele contém DROP legado).

Invariantes em SQL: dispositivo único, crachá normalizado exclusivo, vínculos mesma fazenda, fazenda de equipamento sem troca após atribuição, dispositivo sem troca depois de atribuído; operador sem troca de fazenda. Atualização de nome/outros campos permitida. Cache antigo pode gerar histórico válido depois de revogar operador; não negar pelo ativo atual. RPC de ingestão associa apenas operador existente da fazenda (histórico), impede equipamento alheio, parâmetros desconhecidos não viram SQL. Campos de sessão/UUID/ocorrência preservados. Funções security definer com search_path seguro e grants mínimos. Credenciais só hash. Eventos/lifecycle imutáveis; retry mesmo UUID idempotente, payload conflitante não reescreve original.

Não inferir associação de ESP32 a equipamentos por cliente. Migração pode preencher fazenda quando cliente tem exatamente uma fazenda; dispositivo só caso documentado inequívoco Escavadeira Hidraulica 01 -> SOMPO-ESP32 e fazenda cliente correspondente também tenha esse dispositivo. Demais pendentes.

Testes SQL reais isolados: fixture tables legadas+roles anon/authenticated/service_role, migration twice, counts preserved, unique constraints, cross-farm authorization, RPC token, replay and conflicting payload, invalid operator, config version increments, lifecycle view interrupted and missing NTP. Docker está instalado; confirme daemon; se indisponível procure alternativas locais não destrutivas, não crie nada na produção. Registre limitações.

Antes de implementar escreva cenário de teste que falhe por falta de migração. Use apply_patch. Não spawn subagents. Não faça commits (controller integra alterações). Informe nomes de RPC/campos diferentes antes de mudar contrato. Relatório em docs/planos/task-1-report.md, com testes rodados e evidência. Status final curto.
