# Ativar equipamentos, operadores e RFID

Esta evolução é aditiva: preserva telemetria e eventos existentes e mantém registros antigos sem operador identificado. Não execute `preparar_supabase.sql` para atualizar um banco existente, pois esse arquivo prepara uma instalação nova.

## 1. Aplicar a migração

No SQL Editor do Supabase, execute [`firmware/sql/frota.sql`](../firmware/sql/frota.sql). O script é idempotente e pode ser executado novamente. Ele cria as tabelas de operadores, vínculos, credenciais e sessões, acrescenta os campos históricos e instala as RPCs usadas pelos ESP32.

Antes de continuar, publique a API atualizada. As telas **Máquinas**, **Operadores** e **Histórico** devem aparecer no painel.

## 2. Cadastrar e provisionar cada máquina

1. Abra **Máquinas**, selecione a fazenda e cadastre a máquina com um `dispositivo_id` exclusivo.
2. Abra **Operadores**, cadastre nome e UID do crachá. O UID aceita 4, 7 ou 10 bytes em hexadecimal.
3. Em **Máquinas → Crachás autorizados**, selecione os operadores permitidos.
4. Clique em **Gerar credencial do ESP32**. O token é mostrado uma única vez.
5. No `segredos.h` daquela placa, configure:

```cpp
#define DISPOSITIVO_TOKEN_CFG "TOKEN_EXIBIDO_NO_PAINEL"
```

Cada máquina deve ter seu próprio token. Grave novamente o firmware e acompanhe o Monitor Serial em 115200 baud. A mensagem `autorizacoes sincronizadas` confirma que a placa recebeu a configuração.

O firmware sincroniza a cada 60 segundos e mantém o último cache válido no LittleFS. Sem internet, os crachás já sincronizados continuam funcionando. Eventos e transições de operador permanecem em uma fila durável de até 512 KiB; a telemetria mantém apenas a amostra mais recente.

## 3. Encerrar a compatibilidade antiga

Durante a migração, as policies antigas de `INSERT` permanecem ativas para não interromper placas ainda não provisionadas. Depois que **todas** as máquinas com `dispositivo_id` tiverem credencial e `config_sincronizada_em`, execute manualmente:

```sql
select public.concluir_migracao_dispositivos();
```

A função recusa a operação se alguma placa ainda estiver pendente. Depois dela, os registros só entram pela RPC autenticada `registrar_dispositivo`.

## Comportamento do crachá

- Primeiro toque autorizado: inicia uma sessão e identifica o operador.
- Segundo toque do mesmo crachá: encerra a sessão.
- Outro crachá autorizado: encerra a sessão anterior e inicia uma nova.
- Reinício da placa: encerra a sessão anterior como `interrompida` e exige novo crachá.
- Crachá negado: registra uma tentativa, sem liberar a sessão.
- Incêndio continua sendo monitorado com ou sem operador identificado.

O histórico informa presença associada à sessão. Essa identificação, sozinha, não comprova condução contínua nem responsabilidade por um evento.
