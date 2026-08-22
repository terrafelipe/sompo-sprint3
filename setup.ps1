# setup.ps1 - Prepara o projeto SOMPO de uma vez (API + firmware).
# Rode na raiz:  .\setup.ps1
# Seguro para rodar de novo: nao sobrescreve .env nem segredos.h ja preenchidos.

$ErrorActionPreference = 'Stop'
$raiz = $PSScriptRoot
$api  = Join-Path $raiz 'api'
$fw   = Join-Path $raiz 'firmware\src'

Write-Host "== SOMPO :: setup ==" -ForegroundColor Cyan

# --- 1. Ambiente virtual da API ---
$venvPy = Join-Path $api 'venv\Scripts\python.exe'
if (Test-Path $venvPy) {
    Write-Host "[ok]  venv ja existe (api\venv)" -ForegroundColor Green
} else {
    Write-Host "[..]  criando venv em api\venv"
    python -m venv (Join-Path $api 'venv')
    Write-Host "[ok]  venv criado" -ForegroundColor Green
}

# --- 2. Dependencias ---
Write-Host "[..]  instalando dependencias (requirements.txt)"
& $venvPy -m pip install -r (Join-Path $api 'requirements.txt') -q
Write-Host "[ok]  dependencias instaladas" -ForegroundColor Green

# --- 3. .env da API ---
$env_ = Join-Path $api '.env'
if (Test-Path $env_) {
    Write-Host "[ok]  api\.env ja existe (nao mexi)" -ForegroundColor Green
} else {
    Copy-Item (Join-Path $api '.env.example') $env_
    Write-Host "[novo] api\.env criado a partir do exemplo - PREENCHA as chaves" -ForegroundColor Yellow
}

# --- 4. segredos.h do firmware ---
$seg = Join-Path $fw 'segredos.h'
if (Test-Path $seg) {
    Write-Host "[ok]  firmware\src\segredos.h ja existe (nao mexi)" -ForegroundColor Green
} else {
    Copy-Item (Join-Path $fw 'segredos.exemplo.h') $seg
    Write-Host "[novo] firmware\src\segredos.h criado a partir do exemplo - PREENCHA as chaves" -ForegroundColor Yellow
}

# --- Resumo do que falta ---
Write-Host ""
Write-Host "== Falta preencher (uma vez) ==" -ForegroundColor Cyan
Write-Host "  api\.env"
Write-Host "    SUPABASE_URL          -> Project URL (Settings -> API), ex: https://xxxx.supabase.co"
Write-Host "    SUPABASE_SECRET_KEY   -> service_role / secret key (fica so na API)"
Write-Host "  firmware\src\segredos.h"
Write-Host "    WIFI_SSID_CFG/PASSWORD -> hotspot do celular (2.4 GHz) p/ ESP32 fisico; Wokwi usa Wokwi-GUEST"
Write-Host "    SUPABASE_URL_CFG       -> mesma Project URL"
Write-Host "    SUPABASE_CHAVE_CFG     -> anon / publishable key (sb_publishable_...)"
Write-Host ""
Write-Host "Testar a API (offline):  cd api ; .\venv\Scripts\python.exe -m pytest" -ForegroundColor Cyan
Write-Host "Setup concluido." -ForegroundColor Green
