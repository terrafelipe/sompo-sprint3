# setup.ps1 - Prepara o projeto SOMPO de uma vez (API + firmware).
# Rode na raiz:  .\setup.ps1
# Seguro para rodar de novo: nao sobrescreve .env nem segredos.h ja preenchidos.

$ErrorActionPreference = 'Stop'
$raiz = $PSScriptRoot
$api  = Join-Path $raiz 'api'
$fw   = Join-Path $raiz 'firmware\sompo_hardware_final'

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
# requirements-test.txt inclui o requirements.txt + pytest e playwright (o pytest saiu das
# dependencias de producao da Lambda).
Write-Host "[..]  instalando dependencias (requirements-test.txt)"
& $venvPy -m pip install -r (Join-Path $api 'requirements-test.txt') -q
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
# Consumido pelo .ino quando USAR_WIFI = 1 (Wi-Fi + envio ao Supabase).
$seg = Join-Path $fw 'segredos.h'
if (Test-Path $seg) {
    Write-Host "[ok]  firmware\sompo_hardware_final\segredos.h ja existe (nao mexi)" -ForegroundColor Green
} else {
    Copy-Item (Join-Path $fw 'segredos.exemplo.h') $seg
    Write-Host "[novo] firmware\sompo_hardware_final\segredos.h criado a partir do exemplo" -ForegroundColor Yellow
}

# --- Resumo do que falta ---
Write-Host ""
Write-Host "== Falta preencher (uma vez) ==" -ForegroundColor Cyan
Write-Host "  api\.env"
Write-Host "    SUPABASE_URL          -> Project URL (Settings -> API), ex: https://xxxx.supabase.co"
Write-Host "    SUPABASE_SECRET_KEY   -> service_role / secret key (fica so na API)"
Write-Host "  firmware\sompo_hardware_final\segredos.h"
Write-Host "    WIFI_SSID_CFG/PASSWORD -> hotspot do celular em 2.4 GHz (o ESP32 nao enxerga 5 GHz)"
Write-Host "    SUPABASE_URL_CFG       -> mesma Project URL"
Write-Host "    SUPABASE_CHAVE_CFG     -> anon / publishable key (sb_publishable_...)"
Write-Host ""
Write-Host "Testar a API (offline):  cd api ; .\venv\Scripts\python.exe -m pytest" -ForegroundColor Cyan
Write-Host "Firmware: abrir firmware\sompo_hardware_final\sompo_hardware_final.ino na Arduino IDE" -ForegroundColor Cyan
Write-Host "Setup concluido." -ForegroundColor Green
