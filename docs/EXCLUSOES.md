# Exclusões e detalhes dos usuários

Antes de publicar esta versão da API, execute `firmware/sql/exclusoes.sql` no
Supabase, depois dos scripts `usuarios.sql` e `frota.sql`. O script é aditivo e
pode ser reaplicado: acrescenta `excluido_em`, valida vínculos e cria a operação
transacional de exclusão. Não execute novamente os scripts de seeds para atualizar
uma instalação existente. Se reaplicar `frota.sql`, reaplique `exclusoes.sql` por último.

O perfil Sompo exclui clientes, fazendas, usuários, operadores e máquinas. O gestor
exclui somente máquinas e operadores da própria fazenda. Clientes e fazendas com
cadastros não excluídos vinculados exibem os impedimentos. Cadastros inativos ainda
contam como vínculos: precisam ser excluídos primeiro. Não é permitido excluir a
própria conta nem o último usuário Sompo.

Os botões **Excluir** aparecem nas listas de máquinas, operadores e usuários e
nos detalhes de clientes e fazendas. A confirmação remove o cadastro do uso
operacional, mas preserva seus identificadores, nomes e históricos. Não há
restauração nem reutilização automática de login, UID ou dispositivo excluído.

Excluir um usuário impede novos logins e invalida suas sessões na próxima
requisição. A autenticação passa a depender da consulta ao banco, inclusive para
validar o login de reserva do ambiente; banco indisponível não libera esse acesso.
Excluir uma máquina revoga sua credencial de envio. Excluir um operador remove
suas autorizações na próxima sincronização dos ESP32; equipamentos offline
continuam com o cache anterior até sincronizar. Eventos atrasados de operadores
excluídos ainda são preservados como evidência por máquinas com credencial válida.

As rotas `DELETE /clientes/<id>`, `/fazendas/<id>`, `/usuarios/<id>`,
`/operadores/<id>` e `/equipamentos/<id>` retornam `200 {"ok":true}`, inclusive
na repetição autorizada. Conflitos retornam `409` com `erro` e, quando aplicável,
`dependencias`; falta de permissão retorna `403`, registro inexistente `404`, e
indisponibilidade do banco `502`. A RPC de exclusão só pode ser chamada pelo
backend (`service_role`), não pelo navegador nem pelo ESP32.

`GET /usuarios/<id>` é restrito à Sompo e retorna ID, login, perfil, data de
cadastro, fazenda e dados públicos do cliente. Senhas não são selecionadas.
Consultas históricas continuam aceitando IDs de máquinas/operadores excluídos,
respeitando o escopo de acesso original; listas operacionais os omitem.

## Validação local

```powershell
.venv/Scripts/python -m pytest api/tests -q -p no:cacheprovider
node firmware/sql/tests/run.mjs
```

Instale `api/requirements-test.txt` e o Chromium do Playwright (ou defina
`SOMPO_TEST_BROWSER=msedge`). Os testes de navegador usam respostas HTTP simuladas;
os testes SQL usam PostgreSQL em WebAssembly (`@electric-sql/pglite@0.5.3` instalado
em `firmware/sql/tests/.runtime`). Nenhum desses testes altera o Supabase.

As operações de cadastro usam uma trava transacional curta comum para impedir
exclusões concorrentes com novos vínculos ou com a remoção do último administrador.
Não há chamadas de rede dentro da transação. Depois de aplicar o SQL e publicar a
API, valide listagens, detalhes e exclusão em um cadastro descartável sem vínculos;
verifique os logs da API para respostas `502`. Não remova colunas ao reverter a API:
uma versão antiga não filtra excluídos e não deve ser publicada sobre esses dados.
