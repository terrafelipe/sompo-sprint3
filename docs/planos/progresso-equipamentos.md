# Execução — docs/planos/equipamentos-operadores.md

Base cfa9eab; branch feat/equipamentos-operadores; trabalho isolado em .worktrees/equipamentos-operadores.

| Tarefas | Interface compartilhada | Verificação prévia |
|---|---|---|
| SQL/API | Campos e RPC no contrato | API faz autorização de sessão; SQL valida invariantes |
| SQL/firmware | sincronizar_dispositivo / registrar_dispositivo | Token por dispositivo, categoria e JSON definidos |
| API/UI | Rotas e formatos no contrato | Escopo por fazenda e seleção explícita |
| Firmware/histórico | UUID, sessão, operador e tempo de origem | Sem recomputar autoria ao receber |
| SQL | Migração e rollback | Aditiva; permissões antigas retiradas só na ativação |
| API | Período completo | Paginação na consulta; compatibilidade de leitura legada |
| Firmware | Durabilidade | Confirmação só após gravação; alarmes independentes |
| UI | Estado selecionado | Evitar resposta de equipamento anterior |

Ruling: não executar DDL nem deploy de produção durante desenvolvimento — o pedido será entregue testado com ativação documentada; não há reversão automática de mudanças no banco vivo.

Task 1: complete — migração idempotente e assertions PGlite.
Task 2: complete — API, autorização por fazenda, período completo e relatórios.
Task 3: complete — credencial por dispositivo, cache RFID, sessões e fila LittleFS; sketch compilado.
Task 4: complete — resumo de máquinas, cadastros, autorizações e histórico; desktop/mobile verificados.
Task 5: complete — integração, documentação de ativação e suíte final.
