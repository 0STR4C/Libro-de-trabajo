[CmdletBinding()]
param(
    [string]$ImageName = 'librodetrabajo-app:latest',
    [string]$PytestImageName = 'librodetrabajo-delays-pytest:local',
    [string]$FrontendImageName = 'librodetrabajo-frontend-check:latest',
    [switch]$SkipUiSmoke,
    [switch]$Coverage
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$results = [ordered]@{}
if ($ImageName -ne 'librodetrabajo-app:latest' -and
    $PytestImageName -eq 'librodetrabajo-delays-pytest:local') {
    throw 'Para validar otra imagen, indicá también -PytestImageName construido desde esa imagen.'
}

function Invoke-Stage([string]$Name, [scriptblock]$Action) {
    try {
        & $Action
        if ($LASTEXITCODE -ne 0) { throw "Código de salida $LASTEXITCODE" }
        $results[$Name] = 'APROBADA'
    }
    catch {
        $results[$Name] = "FALLIDA: $($_.Exception.Message)"
    }
}

function Test-ImageAvailable([string]$Name) {
    & docker image inspect $Name --format '{{.Id}}' 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
}
$appReady = Test-ImageAvailable $ImageName
$pytestReady = Test-ImageAvailable $PytestImageName
$frontendReady = Test-ImageAvailable $FrontendImageName
$nodeReady = Test-ImageAvailable 'node:22-alpine'
$results['Imagen de aplicación disponible'] = if ($appReady) { 'APROBADA' } else { "BLOQUEADA: falta $ImageName" }

$legacy = @(
    'tests/test_accessible_layout.py', 'tests/test_contextual_workflows.py',
    'tests/test_dashboard_visual_hierarchy.py', 'tests/test_delay_layout.py',
    'tests/test_login_layout.py', 'tests/test_notice_layout.py',
    'tests/test_quote_layout.py', 'tests/test_settings_news.py'
)
$postgres = @(
    'tests/test_arrival_times_pytest.py', 'tests/test_delay_api_pytest.py',
    'tests/test_notice_page.py', 'tests/test_operational_pages.py',
    'tests/test_postgres_security.py'
)
$excluded = @($legacy + $postgres | ForEach-Object { "--ignore=$_" })

if ($pytestReady) { Invoke-Stage 'Pruebas de dominio sin PostgreSQL' {
    $args = @('run', '--rm', '--pull=never', '--network', 'none', '--read-only',
        '--tmpfs', '/tmp:rw,size=512m', '--mount', "type=bind,source=$root,target=/work,readonly",
        '--workdir', '/work', $PytestImageName, 'python', '-B', '-m', 'pytest',
        'tests', '-q', '-p', 'no:cacheprovider', '--disable-warnings', '--tb=short') + $excluded
    & docker @args
} } else { $results['Pruebas de dominio sin PostgreSQL'] = "BLOQUEADA: falta $PytestImageName" }

if ($nodeReady) { Invoke-Stage 'Sintaxis JavaScript en Docker' {
    & docker run --rm --pull=never --network none `
        --mount "type=bind,source=$root,target=/project,readonly" --workdir /project `
        node:22-alpine sh -ec 'node --check frontend/date-format.js && node --check app/static/branding.js'
} } else { $results['Sintaxis JavaScript en Docker'] = 'BLOQUEADA: falta node:22-alpine' }

if ($frontendReady) { Invoke-Stage 'Vite en Docker' {
    & docker run --rm --pull=never --network none `
        --mount "type=bind,source=$root/frontend,target=/build/frontend,readonly" `
        --mount "type=bind,source=$root/tailwind.config.js,target=/build/tailwind.config.js,readonly" `
        --mount "type=bind,source=$root/postcss.config.js,target=/build/postcss.config.js,readonly" `
        --mount "type=bind,source=$root/vite.config.js,target=/build/vite.config.js,readonly" `
        $FrontendImageName npm run build:frontend
} } else { $results['Vite en Docker'] = "BLOQUEADA: falta $FrontendImageName" }

if ($pytestReady) { Invoke-Stage 'Pruebas PostgreSQL aisladas' {
    & (Join-Path $root 'tools\postgres_test_db\run.ps1') -ImageName $PytestImageName `
        -TestCommand (@('python', '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                         '--disable-warnings', '--tb=short') + $postgres)
} } else { $results['Pruebas PostgreSQL aisladas'] = "BLOQUEADA: falta $PytestImageName" }

if ($Coverage) { $results['Cobertura opcional'] = 'BLOQUEADA: no hay medidor de cobertura en la imagen de pruebas' }
$results['Navegador React'] = 'OMITIDA: no existe prueba vigente de navegador en este ejecutor'
$results['UI histórica'] = if ($SkipUiSmoke) { 'OMITIDA: solicitada' } else { 'OMITIDA: pruebas conservadas, fuera del contrato React' }
Write-Host 'Resultado por etapa:'
foreach ($name in $results.Keys) { Write-Host "  $name`: $($results[$name])" }
$required = @('Imagen de aplicación disponible', 'Pruebas de dominio sin PostgreSQL',
              'Sintaxis JavaScript en Docker', 'Vite en Docker', 'Pruebas PostgreSQL aisladas')
if (@($required | Where-Object { $results[$_] -ne 'APROBADA' }).Count -gt 0) {
    throw 'La validación técnica tiene etapas fallidas o bloqueadas.'
}
Write-Host 'Validación técnica aprobada; límites de cobertura indicados arriba.'
