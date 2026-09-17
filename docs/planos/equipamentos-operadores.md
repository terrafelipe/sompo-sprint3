# Equipamentos e operadores — plano de implementação aprovado

Objetivo: fazenda com várias máquinas, cada uma com ESP32 exclusivo, operadores sem login e identificação RFID histórica.

## Requisitos

- Sompo gerencia todas as fazendas; gestor gerencia apenas equipamentos e operadores da própria fazenda.
- Operador pertence a uma fazenda e pode ser autorizado em várias máquinas dela.
- Dashboard inicia em resumo das máquinas. Detalhe preserva painel existente e identifica equipamento/operador.
- RFID inicia/encerra sessão; outro crachá autorizado troca operador. Reinício encerra de forma interrompida e exige nova identificação.
- Autorizações sincronizadas a cada 60s, cache persistente offline, revogação aplicada ao sincronizar.
- Eventos e transições persistentes em LittleFS, limite 512 KiB, UUID idempotente. Telemetria mantém só amostra recente.
- História carimbada na origem: IDs da máquina, operador, sessão, versão da configuração, ocorrido/recebido, boot e sequência.
- Sem relógio: ocorrido_em nulo, não inventar fim. Incêndio sempre monitorado; não existe bloqueio físico do motor.
- Migração aditiva/idempotente preserva existentes; registros antigos sem operador.
- Dados e relatórios filtrados por equipamento e período completo, sem truncar em 500.
- Não atribuir culpa ao operador só por presença.
- Sem transferência de fazenda nem remanejamento de dispositivo já usado nesta versão.

## Contrato compartilhado

equipamentos: campos existentes + fk_fazenda_id_fazenda bigint nullable para legados, dispositivo_id text unique nullable, ativo bool, config_versao bigint default 1, config_versao_aplicada bigint nullable, config_sincronizada_em timestamptz nullable.
operadores: id_operador bigint PK, nome text, matricula text nullable, fk_fazenda_id_fazenda bigint, uid text UNIQUE (hex uppercase sem separadores, 4/7/10 bytes), ativo bool.
operador_equipamento: equipamento_id bigint + operador_id bigint PK, ativo bool; mesma fazenda obrigatório.
credenciais_dispositivo: equipamento_id PK, token_hash text, criado_em. Sem SELECT público.
registros_operacao: registro_id uuid PK, dispositivo_id, equipamento_id, operador_id nullable, sessao_id uuid nullable, tipo ('inicio','fim','tentativa_negada'), motivo nullable, uid nullable, config_versao, ocorrido_em nullable, recebido_em default now(), boot_id uuid, sequencia bigint, uptime_ms bigint.
view sessoes_operacao: sessao_id, equipamento_id, operador_id, fazenda_id, equipamento_nome, operador_nome, inicio_em, fim_em, recebido_em, status ('aberta','encerrada','interrompida'), motivo.
telemetria/eventos adicionam registro_id uuid unique nullable, equipamento_id, operador_id, sessao_id, uid, config_versao, ocorrido_em nullable, recebido_em default now(), boot_id, sequencia, uptime_ms. criado_em segue compatibilidade: ocorrido_em ou recebimento; presença de registro_id distingue protocolo novo.

RPC sincronizar_dispositivo(p_dispositivo_id text,p_token text) -> objeto {equipamento_id,versao,operadores:[{operador_id,uid}]}; atualiza sincronização, autenticação SHA256(token). Versão incrementada por alterações de autorizações, UID, ativo de operador/equipamento.
RPC registrar_dispositivo(p_dispositivo_id text,p_token text,p_categoria text,p_registro jsonb) -> objeto {ok:true,duplicado:bool}; categorias telemetria,eventos,operacao; extrai campos permitidos, atribui equipamento por credencial, verifica vínculos históricos sem revalidar autorização atual, UUID idempotente e nenhum UPDATE no histórico.
RPC provisionar_dispositivo(p_equipamento_id bigint,p_token_hash text) -> objeto com equipamento_id; apenas service_role.
RPC definir_operadores_equipamento(p_equipamento_id bigint,p_operador_ids bigint[]) -> lista de vínculos; operação atômica, mantém vínculos revogados com ativo=false.
RPC concluir_migracao_dispositivos() -> remove policies legadas de INSERT apenas quando todos equipamentos com dispositivo têm credencial e configuração sincronizada; apenas service_role, execução manual documentada.

API nova Blueprint frota: GET/POST /equipamentos, GET/PATCH /equipamentos/<id>, GET/POST /operadores, GET/PATCH /operadores/<id>, GET/PUT /equipamentos/<id>/operadores (body operador_ids), POST /equipamentos/<id>/credencial (token só retornado na geração), GET /operacoes, GET /fazendas/<id>/resumo.
Listas {dados,total}; cadastros {ok:true,equipamento|operador}; autorizações {dados,total}; resumo {fazenda,equipamentos:[...campos equipamento,ultima_telemetria,scores,operador_nome,comunicacao,config_pendente]}.
Rotas antigas aceitam ?equipamento=<id>; ?dispositivo ainda resolve equipamento; sem seleção retorna 400. Sompo pode consultar legado não cadastrado por dispositivo explicitamente; gestor nunca. /me inclui fazenda_id e fazenda_nome, sem dispositivo forçado.
Histórico filtros equipamento,operador,dias (padrão7,1..365), pagina,limite; {dados,total,pagina,limite}. Listagens máquinas/operadores ?fazenda=<id> (gestor força própria). Interface envia fk_fazenda_id_fazenda, nome, dispositivo_id, demais campos existentes. ativo somente boolean JSON.

## Tarefas

1. SQL/migração/RPC e testes de integração em PostgreSQL isolado.
2. API, filtros/autorização, relatórios e testes Flask.
3. Firmware, persistência/sincronização e testes/compilação.
4. UI de máquinas/operadores/histórico e verificação visual.
5. Integração, revisão independente, documentação e entrega.

## Verificação

Base: 56 testes passam. Cobrir isolamento por fazenda, IDs manipulados, paginação >500, trocas/reinício offline, deduplicação, fila cheia, migração duas vezes, RPC sem token, credencial de outra máquina, cache antigo e horários ausentes. Não executar migração nem deploy em produção durante desenvolvimento.
