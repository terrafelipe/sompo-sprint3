# Modo ao vivo — telemetria em tempo real no Painel da máquina

- **Issue:** #2 · **Data:** 2026-10-06 · **Status:** aprovado em conversa (visual e desenho técnico)
- **Mockup aprovado (referência visual obrigatória):** [`2026-10-06-ao-vivo-mockup.html`](2026-10-06-ao-vivo-mockup.html) — abrir no navegador.

## Objetivo

Na apresentação da FIAP Next, mostrar ao público que o sistema funciona de verdade: mexer na placa
(isqueiro no sensor de chama, abrir capô/tanque, ligar motor sem crachá, passar crachá) e ver, em
1–3 s, os números mudando, o alerta aparecendo e a prova de que o registro foi gravado no banco —
com a sensação do Monitor Serial do Arduino IDE, mas dentro do painel.

**Sucesso:** do evento na placa até a linha no painel em ≤ 3 s (típico); números atualizando a cada
2 s; nenhum dado de outra fazenda acessível; nada muda no painel para quem não liga o modo.

**Fora do escopo:** Supabase Realtime/WebSocket/SSE; colisão, distância, clima (escopo é só furto e
incêndio); GPS/cerca; mudar a sincronização de 60 s; histórico do próprio "ao vivo".

## Situação atual (medida no código)

| Etapa | Hoje |
|---|---|
| Eventos (chama, capô, crachá…) | fila durável no firmware, enviados assim que ocorrem (~1 s) |
| Telemetria | a cada 10 s (`INTERVALO_TELEMETRIA_MS`), caixa que sobrescreve (`xQueueOverwrite`) |
| Envio | ESP32 → `rpc/registrar_dispositivo` no Supabase direto (não passa pela Lambda) |
| Painel | `carregarTudo()` a cada 5 s (`INTERVALO_MS`, `index.html`) |

Pior caso hoje: ~15 s entre o sensor e a tela.

## Desenho

### 1. Banco — `firmware/sql/ao_vivo.sql` (aplicar uma vez, depois de `esp32_por_maquina.sql`)

- `alter table public.equipamentos add column if not exists ao_vivo_ate timestamptz;`
  `null` ou passado = desligado; futuro = ligado até esse instante.
- `create or replace function public.registrar_dispositivo(...)`: **mesma lógica** da versão em
  `frota.sql`, mudando só os dois `return` para incluir
  `'telemetria_ms', case when v_e.ao_vivo_ate > v_now then 2000 else 10000 end`
  (também no caminho `duplicado`). Assinatura, grants e validações idênticos.
- A expiração das 2 h é implícita (comparação com `now()`), sem tarefa agendada.
- Atualizar `ao_vivo_ate` **não** incrementa `config_versao` (nenhum gatilho de versão olha essa
  coluna) e passa pelos gatilhos `cadastro_serializar`/`cadastro_validar` normalmente.
- Firmware antigo ignora a chave nova → compatível antes de regravar a placa.

### 2. Firmware — `firmware/sompo_hardware_final/sompo_hardware_final.ino`

- `Rede::postarRpc`: em 2xx, ler o corpo e extrair `"telemetria_ms"`; guardar numa variável
  `volatile uint32_t intervaloTelemetria` (padrão `INTERVALO_TELEMETRIA_MS` = 10000).
- Aceitar **somente** 2000 ou 10000; qualquer outro valor/ausência mantém 10000 (servidor não
  consegue derrubar a placa com valor absurdo).
- `loop()`: trocar `INTERVALO_TELEMETRIA_MS` por `intervaloTelemetria` na checagem de telemetria.
- Ao passar de 10000 para 2000, a próxima telemetria sai no próximo ciclo (sem esperar os 10 s).
- Log no Serial quando o intervalo muda: `[REDE] telemetria a cada 2 s (ao vivo)`.
- Nada mais muda (eventos, fila durável, sincronização de 60 s).

### 3. API (Flask)

**`POST /equipamentos/<id>/ao-vivo`** (blueprint `frota`), corpo `{"ligar": true|false}`:
- Autorização: `frota.equipamento(id)` (Sompo ou gestor da fazenda dona; excluído → 404).
- Máquina sem `dispositivo_id` → 409 `equipamento_sem_dispositivo`.
- `ligar` não booleano → 400 `ligar_invalido`.
- Liga: `ao_vivo_ate = agora + 2 h` (UTC). Desliga: `ao_vivo_ate = null`.
- Resposta: `{"ok": true, "ao_vivo_ate": <iso|null>}`.

**`GET /ao-vivo?equipamento=<id>&desde=<iso>`**:
- Autorização: `frota.resolver_equipamento()` (mesmo caminho das rotas de telemetria; exige
  `equipamento`).
- `desde`: ISO 8601 com fuso, no máximo 10 min no passado e não no futuro (+5 s de tolerância);
  ausente → últimos 30 s; inválido → 400 `desde_invalido`.
- Devolve, ordenados por `recebido_em` crescente, no máximo 30 de cada:
  - `telemetria` com `recebido_em > desde` (colunas do quadro + `ocorrido_em`, `recebido_em`);
  - `eventos` com `recebido_em > desde` (`tipo`, `severidade`, `ocorrido_em`, `recebido_em`);
  - `operacoes` (`registros_operacao`, início/fim de sessão de crachá) com `recebido_em > desde`,
    com `operador_nome` via `frota.identificar_registros`.
- Mais `ao_vivo_ate` da máquina e `agora` (relógio do servidor, para o cursor do próximo `desde`).
- Sem cache (`Cache-Control: no-store`). Erros pelo `_erro()` padrão (detalhe só no log).

### 4. Painel — `api/static/index.html` (+ CSS em `api/static/painel.css`)

Seção **"Telemetria atual"** (`#secTelemetria`) ganha, no cabeçalho, como no mockup:
- botão **Ao vivo** (desligado) / **Desligar** (ligado); pílula **AO VIVO** pulsante;
  "desliga em h:mm:ss"; "aguardando a placa acelerar…" até chegar a 1ª leitura com intervalo ≤ 3 s;
  botão **Tela cheia** (Fullscreen API na seção; Esc sai).
- Ligado (classe `.ao-vivo` na seção): visual escuro do mockup; os 10 quadradinhos atuais
  (mesma função de render que já existe) ficam maiores e piscam ao mudar; vermelho para
  chama, escape ≥ 450 °C (`TEMP_ESCAPE_ATENCAO` do firmware) e risco crítico, azul para capô/tanque/motor sem crachá/risco alto;
  **faixa de alerta** (6 s) quando chega evento; **terminal** (máx. 9 linhas visíveis) com
  `hh:mm:ss · resumo da leitura · ✓ gravado · chegou em X,X s` (`recebido_em − ocorrido_em`);
  eventos e crachá em linhas coloridas; gráfico do escape recebe os pontos novos.
- Consulta `GET /ao-vivo` a cada 2 s **só** enquanto ligado e a view for o Painel da máquina;
  `renderizarStatusAgora()` também é atualizado. O resto do painel segue nos 5 s atuais.
- Ao abrir/trocar de máquina: se `ao_vivo_ate` estiver no futuro, a seção já abre ligada
  (quem estiver olhando a mesma máquina também vê ao vivo). Chegou a `ao_vivo_ate` → desliga.
- A pausa por inatividade (15 min) também pausa o ao vivo.
- Animações seguem o mockup: entrada de linha 0,35 s `cubic-bezier(.2,.8,.2,1)`, transição de
  tema 0,45–0,5 s; respeitar `prefers-reduced-motion`. Sem script externo novo (CSP).
- Classes novas do Tailwind → rebuild do CSS (`docs/COMO_TESTAR.md` §8); preferir CSS próprio em
  `painel.css` para o visual escuro.

## Erros e casos de borda

- Placa desligada/sem rede: fica "aguardando a placa acelerar…" e a "Última comunicação" do Status
  agora mostra a idade real; nada trava.
- `GET /ao-vivo` falhou: mantém a tela, tenta de novo no próximo ciclo; após 3 falhas seguidas,
  aviso discreto "sem conexão com o servidor".
- Relógios: o cursor `desde` usa `agora` do servidor, nunca o relógio do navegador.
- Duas abas/pessoas ligando/desligando: último comando vence (estado único no banco).
- Custo: 2 h a 2 s ≈ 3,6 mil linhas de telemetria (+ recibos) — aceitável no plano gratuito.

## Testes

- **SQL (PGlite, `firmware/sql/tests/ao_vivo.sql` + `run.mjs`):** `telemetria_ms` = 10000 sem
  `ao_vivo_ate`, 2000 com futuro, 10000 com passado; caminho `duplicado` também responde;
  validações antigas continuam (credencial inválida, alheio à credencial).
- **pytest:** `POST /equipamentos/<id>/ao-vivo` (liga/desliga, gestor de outra fazenda 403,
  excluído 404, sem dispositivo 409, `ligar` inválido 400); `GET /ao-vivo` (escopo/IDOR, `desde`
  inválido/futuro/antigo demais, limites de 30, ordenação, `no-store`); contrato firmware
  (`test_contrato_firmware.py`) aceita `telemetria_ms`.
- **Playwright:** liga → pílula e terminal aparecem; chega leitura simulada → linha com
  "✓ gravado"; evento → faixa; desliga → seção volta ao normal; máquina já ao vivo abre ligada.
- **Firmware:** compila (arduino-cli, ESP32); teste real na placa no ensaio.

## Entrega até a Next

1. Publicar o `9542f48` (pendente). 2. Rodar `ao_vivo.sql` no Supabase. 3. `sompo-deploy`.
4. Regravar a placa. 5. Ensaio com o roteador do celular como Wi-Fi reserva (2.4 GHz, sem portal).
