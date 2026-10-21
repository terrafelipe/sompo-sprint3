# Plano: modo ao vivo e pendências do painel SOMPO

Atualizado em 2026-10-18 · `main` mesclado e enviado ao GitHub (topo: `dcd5c32`) · Issue [#2](https://github.com/terrafelipe/sompo-sprint3/issues/2)

## Em uma frase

O modo ao vivo (telemetria a cada 2 s na demo da FIAP Next) está **pronto, testado e revisado**, mas
**já está no `main` (GitHub)**, mas **não no site no ar**: falta rodar um SQL no Supabase, publicar e regravar a placa.

## Situação em 30 segundos

| Frente | Estado |
|---|---|
| Código do modo ao vivo (SQL, API, firmware, painel) | Pronto e revisado pelo Codex |
| Correções de código das pendências antigas | Feitas |
| Mesclar no `main` e enviar ao GitHub | **Falta (você decide)** |
| Rodar `ao_vivo.sql` no Supabase | **Falta (você)** |
| Publicar na AWS (`sompo-deploy`) | **Falta (você)** |
| Regravar a placa e testar na bancada | **Falta (você)** |
| Medir desempenho em produção | Falta (só depois do deploy) |

Nada foi enviado ao GitHub, mesclado no `main` nem publicado.

---

## 1. O que foi feito

Todas as revisões do Codex usaram `gpt-6.1-sol` com esforço `medium`.

### 1.1 Modo ao vivo (Issue #2)

A branch `ao-vivo` (06/10) já tinha o trabalho, mas não estava na ficha do projeto. Foi trazida para a
`ao-vivo-integracao`, validada e corrigida.

O que o modo faz:

- Botão **"Ao vivo"** na seção *Telemetria atual* do Painel da máquina.
- `equipamentos.ao_vivo_ate`: o `registrar_dispositivo` responde `telemetria_ms` = 2000 (ao vivo) ou 10000 (normal).
- O firmware usa o intervalo recebido (**é preciso regravar a placa**).
- `POST /equipamentos/<id>/ao-vivo` liga/desliga; `GET /ao-vivo?equipamento=&desde=` entrega o que chegou.
- Terminal com "✓ gravado · chegou em X s", faixa de alerta, tela cheia, e desliga sozinho em 2 h.

Correções feitas depois da revisão do Codex:

| Problema encontrado | Correção | Commit |
|---|---|---|
| O cursor do `/ao-vivo` saltava até a linha mais nova e perdia uma linha confirmada depois | O cursor recua sempre 5 s; o painel já deduplica por `registro_id` | `c6a792e` |
| Aba escondida por mais de 10 min: o cursor velho dava erro 400 para sempre | Em HTTP 400 o painel zera o cursor e recomeça | `c6a792e` |
| Uma carga de 5 s atrasada, com leitura antiga, desfazia a leitura ao vivo (gráfico, status e risco) | As leituras ao vivo mais novas ficam no cache e valem para o risco | `a7c9a15` |
| `ao_vivo.sql` não estava na ordem das migrações | Entrou em `docs/ATIVAR_FROTA.md`, `contexto.md` e no cabeçalho do SQL | `a7c9a15` |

### 1.2 Pendências antigas da ficha

| Pendência | Resultado | Commit |
|---|---|---|
| Status de comunicação ignora a troca do ID do ESP32 (revisão T9, achado 5) | Só a leitura da placa **vinculada agora** conta como "recente"; a da placa antiga vira "atrasada" | `b9f5647` |
| Acentuar o texto do template de risco, conferindo o PDF | Texto sem IA todo acentuado na tela e no PDF; teste varre todos os tipos de evento | `a5eb94e` |
| Barras de "De onde vem o score" redesenhadas a cada 5 s | **Já estava resolvido no código** (a ficha estava desatualizada). Entrou só um teste que protege | `e38453e`, `4c6c8d7` |
| Pílula do risco dizia "MEDIO" e o texto dizia "MÉDIO" | Pílula e selos mostram "MÉDIO"; a chave sem acento segue na lógica, nas cores e na API | `2690fee` |
| Busca por "medio" deixaria de achar "MÉDIO" (achado do Codex) | Buscas das listas e do Histórico ignoram acento e caixa | `3c26b78` |
| KPI de risco e tooltip da linha do tempo mostravam `ATENCAO`/`CRITICO` crus | Mostram "ATENÇÃO" e "CRÍTICO" | `3c26b78` |

### 1.3 Firmware

Compilado com o `arduino-cli` do Arduino IDE (placa `esp32:esp32:esp32`), usando o `segredos.h` de exemplo:
**1.135.679 bytes, 86% da flash**, igual ao firmware anterior. Ainda **não foi gravado nem testado na placa**.

### 1.4 Testes

| Suíte | Resultado |
|---|---|
| Backend (Flask, sem navegador) | 356 passaram |
| Navegador (Chrome real, em blocos por causa da RAM) | 276 passaram (72 + 90 + 58 + 56, nos 4 blocos) |
| SQL no PGlite (6 blocos, inclui `ao_vivo.sql`) | Todos passaram |

### 1.5 O que o Codex errou ou eu não fiz de propósito

- **Errado:** o Codex disse que o `esp32_por_maquina.sql` também redefine o `registrar_dispositivo`. Só o `frota.sql` faz isso (conferido no SQL). A doc ficou com o que é verdade.
- **Não implementado:** avisar uma aba já aberta quando outra pessoa liga o modo ao vivo. Custaria uma requisição extra a cada 5 s por visitante, contra a economia de crédito do Learner Lab, e a spec só pede abrir ligado ao abrir/trocar de máquina. Fica como limitação conhecida (ver seção 4).

---

## 2. O que falta fazer (em ordem)

Os passos 1 a 4 são o caminho até a demo. Os passos 5 e 6 podem esperar.

### Passo 1 · Mesclar no `main` e enviar ao GitHub — você decide

O repositório é **público**; o push não publica o site. Pelo clone do OneDrive:

```powershell
cd "C:\Users\USUARIO\OneDrive - Fiap-Faculdade de Informática e Administração Paulista\FIAP\SOMPO\sompo-sprint3"
git status                      # só o .vscode/c_cpp_properties.json deve aparecer; ele NÃO vai junto
git checkout main
git merge --ff-only ao-vivo-integracao
git push origin main            # o commit final leva "Closes #2"
```

### Passo 2 · Rodar `ao_vivo.sql` no Supabase — você

SQL Editor do projeto `ljkfuwvkmczpmjupxnxw` → colar o conteúdo de `firmware/sql/ao_vivo.sql` → Run.
É idempotente. **Rode antes do deploy**: sem ele o botão "Ao vivo" falha (o resto do painel segue normal).

> Se alguém rodar o `frota.sql` de novo, ele reinstala o `registrar_dispositivo` sem `telemetria_ms`.
> Reaplique `esp32_por_maquina.sql` e, **por último**, `ao_vivo.sql`.

### Passo 3 · Publicar na AWS — você

Learner Lab → Start Lab → console (N. Virginia) → CloudShell → `sompo-deploy`.
Confira no "Deploy ok" o hash do topo do `main` (hoje `dcd5c32`). Este deploy também leva a correção do mapa (Passo 3b), o cache de 20 s (site mais rápido) e o firmware dividido em arquivos `.h` (abra a pasta toda no Arduino IDE). Depois, quem estava logado entra de novo uma vez.

### Passo 3b · Conferir o mapa depois do deploy — você

O mapa (carteira, fazenda e camada "ruas") dava 403 "Access blocked" do OpenStreetMap porque o
`Referrer-Policy: same-origin` (`123b243`) tirava o Referer dos tiles. Corrigido em `8e057c6`
(`strict-origin-when-cross-origin`). **Depois do deploy, abra o mapa e confira que os tiles carregam.**
Se ainda der 403, a causa é outra (ex.: bloqueio por volume de uso do OSM): avisar o Claude.

### Passo 4 · Regravar a placa e testar na bancada — você

1. Arduino IDE → abrir `firmware/sompo_hardware_final`, placa **ESP32 Dev Module**.
2. Criar o `segredos.h` real a partir de `segredos.exemplo.h` (**nunca commitar**).
3. Gravar. Esperado: 86% da flash.
4. No painel: máquina → *Telemetria atual* → **Ao vivo**. Esperado:
   - o terminal mostra uma linha a cada ~2 s com "✓ gravado · chegou em X s";
   - um alerta de furto ou incêndio acende a faixa de alerta e uma linha destacada no terminal;
   - **Desligar** devolve a placa ao ritmo de 10 s;
   - sozinho, desliga em 2 h (contador no canto).
5. No mesmo ensaio, testar também o que está pendente da rodada anterior:
   - troca do ID do ESP32 (a placa descarta da fila o que tem o ID velho, `baea1e9`);
   - fim da sessão quando o crachá muda de dono (`0336f9e`).

### Passo 5 · Pendências de produção — você

- [ ] **(recomendado, não esquecer) Copiar o `PROXY_SEGREDO` para o Cloudflare Pages.** Serve para o limite de tentativas do login usar o IP real de cada visitante (sem isso, um visitante pode travar o login de outro por 15 min). Passo a passo:
  1. CloudShell: `tail -n 3 ~/sompo-sprint3/infra/.env.aws` e copiar o valor depois de `PROXY_SEGREDO=` (**não colar no chat nem no git**).
  2. Cloudflare → projeto Pages `sompo-painel` → Settings → Variables and Secrets → Add: nome `PROXY_SEGREDO`, tipo **Secret**, valor copiado.
  3. Republicar o `infra/pages` (Deployments → Retry/redeploy, ou o upload da pasta como da última vez). Detalhes em `docs/DEPLOY.md` (linha do `PROXY_SEGREDO`).
- [ ] (opcional) Trocar a `PAINEL_SENHA` do `.env.aws` por valor aleatório (ela só liga o login).
- [ ] Decidir: senha inicial "temporária" (obrigar troca no primeiro login)? Oferecido em 2026-09-25, sem resposta.
- [ ] Informar a localização das fazendas (Fazendas → detalhe → "Buscar pela cidade").
- [ ] Ajustes visuais pequenos no painel: aguardando a sua lista.

### Passo 6 · Depois da demo

- [ ] Medir de novo o Início (antes: 4,9 s a quente, 10,7 s a frio) e o Painel da máquina (2,8 s). Só dá em produção.
- [ ] Automação do deploy: testar CodeBuild com a `LabRole`; senão, GitHub Actions com as chaves temporárias.
- [ ] **Plano de continuidade antes do fim do curso**: o Learner Lab é apagado e o site cai junto (plano B: `render.yaml`, hoje suspenso).
- [ ] (opcional) Groq para o texto da IA; consultas do Painel em paralelo; `/saude` a cada 30 s.
- [ ] Futuro: o firmware enviar o GPS e calcular a cerca de verdade (o alerta `furto_cerca` já existe).

---

## 3. Riscos e pontos de atenção

- **Ordem importa:** SQL no Supabase **antes** do deploy. Publicar a API antes do `ao_vivo.sql` deixa o botão quebrado.
- **Regravar a placa é obrigatório** para a telemetria acelerar: sem o firmware novo o botão liga, mas a placa segue em 10 s.
- **Learner Lab:** credenciais só funcionam com o lab ligado. Ligue-o antes do deploy.
- **Segredos:** `segredos.h` e `infra/.env.aws` nunca entram no git.
- **Gemini gratuito** pode levar 30–60 s ou dar 503; os scores não dependem dele (`?ia=0`).

## 4. Limitações conhecidas

- Quem **já está** com a máquina aberta não vê outra pessoa ligar o ao vivo; só vê ao abrir/trocar de máquina ou recarregar.
  Reavaliar se a demo tiver 2 pessoas na mesma máquina.
- Uma linha do banco que demore mais de 5 s para ser confirmada pode não aparecer no terminal (a janela do cursor é de 5 s).
- O ao vivo só funciona com o Painel da máquina aberto, com a aba visível e com atividade nos últimos 15 min (a pausa automática continua valendo).

## 5. Referências

- Spec: `docs/superpowers/specs/2026-10-06-ao-vivo-design.md` (mockup ao lado) · plano de implementação: `docs/superpowers/plans/2026-10-06-ao-vivo.md`
- Ordem das migrações SQL: `docs/ATIVAR_FROTA.md`
- Deploy: `docs/DEPLOY.md` · testes: `docs/COMO_TESTAR.md`
- Estado do projeto: ficha `projetos/sompo-sprint3.md` no AIOS
