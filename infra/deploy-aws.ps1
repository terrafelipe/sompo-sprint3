# Deploy do painel SOMPO na AWS Lambda (imagem Docker + Function URL), pensado para o
# AWS Academy Learner Lab: usa a LabRole pronta (o lab nao deixa criar roles) e as
# credenciais temporarias da sessao (colar "AWS Details" em ~/.aws/credentials).
#
# Uso (na raiz do repo, com Docker disponivel):
#   Windows:          powershell -ExecutionPolicy Bypass -File infra\deploy-aws.ps1
#   AWS CloudShell:   pwsh infra/deploy-aws.ps1   (ja tem Docker, aws CLI e credenciais)
#
# Idempotente: a 1a execucao cria ECR, funcao, Function URL e permissoes; as seguintes
# so publicam a imagem nova e atualizam as variaveis de ambiente.
param(
    [string]$Regiao = 'us-east-1',
    [string]$Funcao = 'sompo-painel',
    [string]$Repositorio = 'sompo-painel'
)

# 'Continue' de proposito: no PowerShell 5.1, stderr de executavel nativo com 'Stop'
# vira erro fatal mesmo com exit code 0. Os erros sao checados por $LASTEXITCODE.
$ErrorActionPreference = 'Continue'
$raiz = Split-Path -Parent $PSScriptRoot
$utf8SemBom = New-Object System.Text.UTF8Encoding($false)

function Invoke-Aws {
    # Roda o aws CLI e aborta o script se falhar.
    $saida = & aws @args --region $Regiao --output json
    if ($LASTEXITCODE -ne 0) { throw "Falhou: aws $($args -join ' ')" }
    # Junta as linhas: o ConvertFrom-Json do PS 5.1 nao aceita JSON quebrado em varias.
    return ($saida -join "`n")
}

function Test-Aws {
    # Tentativa nao fatal (ex.: reservar concorrencia): so diz se deu certo.
    & aws @args --region $Regiao --output json 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Test-Existe {
    # O recurso existe? So 'NotFound' significa "nao existe"; qualquer outro erro
    # (credencial do lab expirada, AccessDenied, throttling) aborta com a causa real,
    # em vez de o script cair no ramo de criacao e falhar com erro enganoso.
    $saida = & aws @args --region $Regiao --output json 2>&1
    if ($LASTEXITCODE -eq 0) { return $true }
    $erro = ($saida | Out-String)
    if ($erro -match 'NotFound') { return $false }
    throw "Falhou: aws $($args -join ' ')`n$erro"
}

function Wait-Funcao([string]$Estado) {
    & aws lambda wait $Estado --function-name $Funcao --region $Regiao
    if ($LASTEXITCODE -ne 0) { throw "A funcao nao chegou ao estado $Estado" }
}

# --- 1. Variaveis de ambiente da Lambda (infra/.env.aws) ---------------------------
$arquivoEnv = Join-Path $PSScriptRoot '.env.aws'
if (-not (Test-Path $arquivoEnv)) { throw "Crie $arquivoEnv a partir de infra/.env.aws.example" }
$variaveis = [ordered]@{}
foreach ($linha in Get-Content $arquivoEnv -Encoding UTF8) {
    $linha = $linha.Trim()
    if ($linha -eq '' -or $linha.StartsWith('#') -or -not $linha.Contains('=')) { continue }
    $partes = $linha.Split('=', 2)
    $valor = $partes[1].Trim()
    # Mesma leitura do python-dotenv (api/.env): aspas envolventes saem; sem aspas,
    # ' #' inicia comentario. Assim da para colar os valores do api/.env como estao.
    if ($valor.Length -ge 2 -and ($valor[0] -eq '"' -or $valor[0] -eq "'") -and $valor[-1] -eq $valor[0]) {
        $valor = $valor.Substring(1, $valor.Length - 2)
    } elseif ($valor -match '^(.*?)\s+#') {
        $valor = $Matches[1]
    }
    $variaveis[$partes[0].Trim()] = $valor
}
foreach ($obrigatoria in 'SUPABASE_URL', 'SUPABASE_SECRET_KEY', 'PAINEL_SENHA', 'SECRET_KEY') {
    if (-not $variaveis[$obrigatoria]) { throw "$obrigatoria vazia em infra/.env.aws" }
}
if ($variaveis['SOMPO_API_KEY']) { throw 'SOMPO_API_KEY deve ficar VAZIA (senao o painel recebe 401)' }
# Fixas do ambiente Lambda: porta do waitress/adapter, readiness sem login e cookie HTTPS.
$variaveis['PORT'] = '8080'
$variaveis['AWS_LWA_READINESS_CHECK_PATH'] = '/login'
# Eventos que nao sao HTTP (o ping do EventBridge) chegam ao Flask como POST neste caminho.
$variaveis['AWS_LWA_PASS_THROUGH_PATH'] = '/events'
$variaveis['COOKIE_SEGURO'] = 'true'

# --- 2. Conta, role e repositorio ECR ---------------------------------------------
$conta = (Invoke-Aws sts get-caller-identity | ConvertFrom-Json).Account
$roleArn = "arn:aws:iam::${conta}:role/LabRole"
$registro = "$conta.dkr.ecr.$Regiao.amazonaws.com"
Write-Host "Conta $conta, regiao $Regiao"

if (-not (Test-Existe ecr describe-repositories --repository-names $Repositorio)) {
    Write-Host "Criando repositorio ECR $Repositorio..."
    Invoke-Aws ecr create-repository --repository-name $Repositorio | Out-Null
}

# --- 3. Build + push da imagem ----------------------------------------------------
$tag = (Get-Date -Format 'yyyyMMdd-HHmmss')
$commit = (& git -C $raiz rev-parse --short HEAD 2>$null)
if ($commit) { $tag = "$tag-$commit" }
$imagem = "$registro/${Repositorio}:$tag"

(& aws ecr get-login-password --region $Regiao) | docker login --username AWS --password-stdin $registro
if ($LASTEXITCODE -ne 0) { throw 'docker login no ECR falhou' }
# Com buildx, --provenance=false evita o manifest multi-plataforma que a Lambda rejeita.
# Sem buildx (builder classico, ex.: CloudShell) a imagem ja sai no formato aceito.
docker buildx version 2>$null | Out-Null
$flagsBuild = @('--platform', 'linux/amd64')
if ($LASTEXITCODE -eq 0) { $flagsBuild += '--provenance=false' }
docker build @flagsBuild -t $imagem (Join-Path $raiz 'api')
if ($LASTEXITCODE -ne 0) { throw 'docker build falhou' }
docker push $imagem
if ($LASTEXITCODE -ne 0) { throw 'docker push falhou' }

# --- 4. Cria ou atualiza a funcao -------------------------------------------------
# O JSON com os segredos so existe durante este passo e e apagado mesmo se algo falhar.
$envJson = Join-Path ([IO.Path]::GetTempPath()) 'sompo-lambda-env.json'
try {
    [IO.File]::WriteAllText($envJson, (@{ Variables = $variaveis } | ConvertTo-Json -Depth 3), $utf8SemBom)
    if (Test-Existe lambda get-function --function-name $Funcao) {
        # Variaveis antes do codigo: var nova e ignorada pela imagem antiga, mas imagem
        # nova com var velha pode quebrar (ex.: PORT do adapter).
        Write-Host 'Atualizando variaveis da funcao...'
        Invoke-Aws lambda update-function-configuration --function-name $Funcao `
            --environment "file://$envJson" --memory-size 1024 --timeout 60 | Out-Null
        Wait-Funcao 'function-updated-v2'
        Write-Host 'Atualizando codigo da funcao...'
        Invoke-Aws lambda update-function-code --function-name $Funcao --image-uri $imagem | Out-Null
        Wait-Funcao 'function-updated-v2'
    } else {
        Write-Host 'Criando funcao...'
        Invoke-Aws lambda create-function --function-name $Funcao --package-type Image `
            --code "ImageUri=$imagem" --role $roleArn --architectures x86_64 `
            --memory-size 1024 --timeout 60 --environment "file://$envJson" | Out-Null
        Wait-Funcao 'function-active-v2'
    }
} finally {
    Remove-Item $envJson -Force -ErrorAction SilentlyContinue
}

# O painel faz varias requisicoes em paralelo; um teto baixo gera 429.
# A pausa automatica do painel contem o custo quando nao esta em uso.
Test-Aws lambda delete-function-concurrency --function-name $Funcao | Out-Null

# --- 5. Function URL publica (o login do Flask protege o site) ---------------------
if (-not (Test-Existe lambda get-function-url-config --function-name $Funcao)) {
    Write-Host 'Criando Function URL...'
    Invoke-Aws lambda create-function-url-config --function-name $Funcao --auth-type NONE | Out-Null
}
# Desde out/2025 a URL publica exige as DUAS permissoes. Checadas uma a uma para o
# script se recuperar de uma execucao interrompida no meio.
# '--principal=*' grudado: no pwsh do Linux um '*' solto vira glob (lista de arquivos).
$politica = ''
if (Test-Existe lambda get-policy --function-name $Funcao) {
    $politica = Invoke-Aws lambda get-policy --function-name $Funcao
}
if ($politica -notmatch 'FunctionURLAllowPublicAccess') {
    Invoke-Aws lambda add-permission --function-name $Funcao `
        --statement-id FunctionURLAllowPublicAccess --action lambda:InvokeFunctionUrl `
        '--principal=*' --function-url-auth-type NONE | Out-Null
}
if ($politica -notmatch 'FunctionURLInvokeAllowPublicAccess') {
    Invoke-Aws lambda add-permission --function-name $Funcao `
        --statement-id FunctionURLInvokeAllowPublicAccess --action lambda:InvokeFunction `
        '--principal=*' --invoked-via-function-url | Out-Null
}
$url = (Invoke-Aws lambda get-function-url-config --function-name $Funcao | ConvertFrom-Json).FunctionUrl

# --- 6. Logs com retencao curta (nao acumular custo) ------------------------------
$grupo = "/aws/lambda/$Funcao"
Test-Aws logs create-log-group --log-group-name $grupo | Out-Null
if (-not (Test-Aws logs put-retention-policy --log-group-name $grupo --retention-in-days 7)) {
    Write-Warning 'Nao foi possivel definir a retencao dos logs.'
}

# --- 7. Aquecimento: EventBridge chama a Lambda a cada 5 min -----------------------
# Evita o cold start (5 a 7 s) de quem abre o painel depois de um tempo sem uso. Tres alvos
# ao mesmo tempo mantem ate tres instancias quentes (o painel faz requisicoes em paralelo).
# Custo desprezivel (~26 mil invocacoes curtas por mes). Nao fatal: se a conta do lab nao
# permitir EventBridge, o site funciona igual, so sem o ping.
$regra = "$Funcao-aquecer"
$arnFuncao = (Invoke-Aws lambda get-function --function-name $Funcao | ConvertFrom-Json).Configuration.FunctionArn
if (Test-Aws events put-rule --name $regra --schedule-expression 'rate(5 minutes)' --state ENABLED) {
    $arnRegra = (Invoke-Aws events describe-rule --name $regra | ConvertFrom-Json).Arn
    if ($politica -notmatch 'AquecerEventBridge') {
        Test-Aws lambda add-permission --function-name $Funcao --statement-id AquecerEventBridge `
            --action lambda:InvokeFunction --principal events.amazonaws.com --source-arn $arnRegra | Out-Null
    }
    $alvos = 1..3 | ForEach-Object { "Id=aquecer$_,Arn=$arnFuncao" }
    if (Test-Aws events put-targets --rule $regra --targets @alvos) {
        Write-Host 'Aquecimento ligado: EventBridge a cada 5 min.'
    } else {
        Write-Warning 'Nao foi possivel ligar o aquecimento (EventBridge); seguindo sem ele.'
    }
} else {
    Write-Warning 'Nao foi possivel criar a regra de aquecimento (EventBridge); seguindo sem ele.'
}

Write-Host ''
Write-Host "Deploy ok: $imagem"
Write-Host "Function URL: $url"
Write-Host 'Se a URL mudou, atualize LAMBDA_URL_PADRAO em infra/pages/_worker.js e publique no Pages.'
