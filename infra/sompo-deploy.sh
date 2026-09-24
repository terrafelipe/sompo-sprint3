#!/usr/bin/env bash
# Deploy do painel SOMPO num comando so, para rodar no AWS CloudShell (com o lab iniciado).
#
# Instalacao (uma vez):
#   echo "alias sompo-deploy='cd ~/sompo-sprint3 && git fetch -q origin && git checkout -q main && git pull -q --ff-only && bash infra/sompo-deploy.sh'" >> ~/.bashrc && source ~/.bashrc
# Uso:
#   sompo-deploy
#
# O que faz: confere que o clone esta limpo e igual ao origin/main, roda infra/deploy-aws.ps1
# e confirma que a imagem publicada tem o hash do commit atual (o clone do CloudShell ja
# ficou num branch antigo e publicou versao velha sem ninguem perceber).
set -euo pipefail

cd "$(dirname "$0")/.."

ramo=$(git rev-parse --abbrev-ref HEAD)
if [ "$ramo" != "main" ]; then
    echo "ERRO: o clone esta no branch '$ramo'. Rode: git checkout main && git pull" >&2
    exit 1
fi

# Alteracoes locais (fora do .env.aws, que o git ignora) poderiam ir para a imagem sem estar no GitHub.
if [ -n "$(git status --porcelain)" ]; then
    echo "ERRO: ha alteracoes locais no clone. Confira com 'git status' antes de publicar." >&2
    exit 1
fi

git fetch -q origin main
if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
    echo "ERRO: o clone nao esta igual ao origin/main. Rode: git pull --ff-only" >&2
    exit 1
fi

esperado=$(git rev-parse --short HEAD)
echo "Publicando $esperado: $(git log -1 --format=%s)"
echo

log=$(mktemp)
pwsh infra/deploy-aws.ps1 | tee "$log"

linha=$(grep '^Deploy ok:' "$log" || true)
rm -f "$log"
if [[ "$linha" == *"-$esperado" ]]; then
    echo
    echo "OK: a Lambda esta com o commit $esperado. Site: https://sompo-painel.pages.dev"
else
    echo
    echo "ERRO: o deploy nao confirmou o commit $esperado (linha: '${linha:-nenhuma}')." >&2
    exit 1
fi
