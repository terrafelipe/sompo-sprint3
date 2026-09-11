# Prepara o ambiente de compilacao do firmware SEM instalar nada global.
#
#     .\firmware\tools\instalar-arduino-cli.ps1
#
# O que faz:
#   1. baixa o arduino-cli.exe portatil para firmware\tools\ (gitignorado, ~30 MB)
#   2. gera o firmware\arduino-cli.yaml com os caminhos DESTA maquina
#   3. instala o core esp32 (~250 MB de download) em %LOCALAPPDATA%\Arduino15
#
# O core fica FORA do repo de proposito: sao ~1,5 GB em disco, que nao tem por
# que morar dentro do entregavel.
#
# Seguro para rodar de novo: nao rebaixa o que ja existe.
# Use -Regenerar para so reescrever o YAML (ex.: ao clonar o repo noutra maquina).

param(
    [switch]$Regenerar,
    [switch]$Forcar      # rebaixa o arduino-cli.exe mesmo se ja existir
)

$ErrorActionPreference = 'Stop'

$tools     = $PSScriptRoot
$firmware  = Split-Path $tools -Parent
$exe       = Join-Path $tools 'arduino-cli.exe'
$config    = Join-Path $firmware 'arduino-cli.yaml'

$dataDir   = Join-Path $env:LOCALAPPDATA 'Arduino15'
$sketchDir = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Arduino'
$indiceEsp32 = 'https://espressif.github.io/arduino-esp32/package_esp32_index.json'

Write-Host "== SOMPO :: ambiente de compilacao do firmware ==" -ForegroundColor Cyan

# --- 1. Sketchbook (onde ficam as bibliotecas ja instaladas) -----------------
# MyDocuments segue o redirecionamento do OneDrive, que e onde as libs estao.
if (-not (Test-Path (Join-Path $sketchDir 'libraries'))) {
    Write-Host "[aviso] nao achei bibliotecas em $sketchDir\libraries" -ForegroundColor Yellow
    Write-Host "        se as suas estiverem noutro lugar, ajuste 'directories.user' no arduino-cli.yaml"
} else {
    $n = (Get-ChildItem (Join-Path $sketchDir 'libraries') -Directory).Count
    Write-Host "[ok]  sketchbook: $sketchDir ($n bibliotecas)" -ForegroundColor Green
}

# --- 2. Binario portatil ------------------------------------------------------
if ((Test-Path $exe) -and -not $Forcar) {
    Write-Host "[ok]  arduino-cli.exe ja existe (use -Forcar para rebaixar)" -ForegroundColor Green
} elseif (-not $Regenerar) {
    $url = 'https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_Windows_64bit.zip'
    $zip = Join-Path $env:TEMP 'arduino-cli.zip'
    $tmp = Join-Path $env:TEMP 'arduino-cli-extract'

    Write-Host "[..]  baixando o arduino-cli portatil (~30 MB)"
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing

    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    Copy-Item (Join-Path $tmp 'arduino-cli.exe') $exe -Force
    Remove-Item $zip, $tmp -Recurse -Force

    Write-Host "[novo] $exe" -ForegroundColor Yellow
}

# --- 3. Config apontando para os caminhos desta maquina ----------------------
# O arduino-cli NAO expande variaveis de ambiente no YAML, entao o arquivo e
# gerado com os caminhos ja resolvidos. Por isso ele e versionado mas descartavel:
# noutra maquina, rode com -Regenerar.
@"
# GERADO por firmware/tools/instalar-arduino-cli.ps1 - nao edite a mao.
# Noutra maquina: .\firmware\tools\instalar-arduino-cli.ps1 -Regenerar
#
# Os caminhos sao absolutos porque o arduino-cli nao expande %VARIAVEIS%.
board_manager:
  additional_urls:
    - $indiceEsp32
directories:
  # Core ESP32 + toolchain (~1,5 GB). Fica FORA do repo de proposito.
  data: $dataDir
  downloads: $dataDir\staging
  # Sketchbook: onde estao as bibliotecas ja instaladas (Adafruit, MFRC522, ...).
  # Sem isto o compile falha com "Adafruit_MPU6050.h: No such file".
  user: $sketchDir
logging:
  level: warn
"@ | Set-Content $config -Encoding UTF8

Write-Host "[ok]  $config" -ForegroundColor Green

# --- 4. Core ESP32 ------------------------------------------------------------
# Sem o binario ainda (rodou so -Regenerar antes de baixar) nao da para seguir.
if (-not (Test-Path $exe)) {
    Write-Host "[aviso] arduino-cli.exe ainda nao existe - rode sem -Regenerar para baixar." -ForegroundColor Yellow
    exit 0
}

$jaTem = & $exe --config-file $config core list 2>$null | Select-String 'esp32:esp32'
if ($jaTem) {
    Write-Host "[ok]  core esp32 ja instalado" -ForegroundColor Green
} else {
    Write-Host "[..]  atualizando o indice de placas"
    & $exe --config-file $config core update-index
    Write-Host "[..]  instalando o core esp32 (~250 MB - demora)"
    & $exe --config-file $config core install esp32:esp32
    Write-Host "[novo] core esp32 instalado" -ForegroundColor Yellow
}

# --- 5. IntelliSense (c_cpp_properties.json) ---------------------------------
# Gerado aqui porque os caminhos dependem da VERSAO do core instalado, que muda
# a cada atualizacao. O que a extensao cria sozinha vem com 'arduino:avr:uno' e
# includePath vazio - dai o sublinhado vermelho em todo #include.
$coreDir = Get-ChildItem (Join-Path $dataDir 'packages\esp32\hardware\esp32') -Directory -ErrorAction SilentlyContinue |
           Sort-Object Name -Descending | Select-Object -First 1
$gpp = Get-ChildItem (Join-Path $dataDir 'packages\esp32\tools') -Recurse -Filter 'xtensa-esp32-elf-g++.exe' -ErrorAction SilentlyContinue |
       Select-Object -First 1

if ($coreDir -and $gpp) {
    $vscode = Join-Path $firmware 'sompo_hardware_final\.vscode'
    New-Item -ItemType Directory -Force $vscode | Out-Null
    $inc = @(
        "$($coreDir.FullName)\cores\esp32",
        "$($coreDir.FullName)\variants\esp32",
        "$($coreDir.FullName)\libraries\**",
        "$sketchDir\libraries\**",
        '${workspaceFolder}\**'
    ) | ForEach-Object { '        "' + ($_ -replace '\\','/') + '"' }

    @"
{
    "//": "GERADO por firmware/tools/instalar-arduino-cli.ps1 - nao edite a mao.",
    "configurations": [
        {
            "name": "ESP32",
            "includePath": [
$($inc -join ",`n")
            ],
            "defines": [ "ARDUINO=10819", "ESP32=1", "ARDUINO_ARCH_ESP32=1", "F_CPU=240000000L" ],
            "compilerPath": "$($gpp.FullName -replace '\\','/')",
            "cStandard": "c11",
            "cppStandard": "c++17",
            "intelliSenseMode": "gcc-x64"
        }
    ],
    "version": 4
}
"@ | Set-Content (Join-Path $vscode 'c_cpp_properties.json') -Encoding UTF8
    Write-Host "[ok]  IntelliSense configurado (core $($coreDir.Name))" -ForegroundColor Green
} else {
    Write-Host "[aviso] core esp32 nao encontrado - IntelliSense nao configurado" -ForegroundColor Yellow
}

# --- 6. Conferencia -----------------------------------------------------------
Write-Host ""
Write-Host "== Conferindo ==" -ForegroundColor Cyan
& $exe --config-file $config version
& $exe --config-file $config core list

Write-Host ""
Write-Host "Compilar o firmware:" -ForegroundColor Cyan
Write-Host "  .\firmware\tools\arduino-cli.exe --config-file firmware\arduino-cli.yaml compile --fqbn esp32:esp32:esp32 firmware\sompo_hardware_final"
Write-Host "No VS Code: a extensao Arduino ja esta apontada para este binario (.vscode\settings.json)." -ForegroundColor Cyan
