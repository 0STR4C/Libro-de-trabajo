[CmdletBinding()]
param(
    [string]$ImageName = 'librodetrabajo-app:latest',
    [switch]$SkipUiSmoke,
    [switch]$Coverage
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$uiScript = Join-Path $root 'tools\wfm_offline_build\ui_smoke.cjs'
$playwrightModule = Join-Path $root 'tools\wfm_offline_build\node_modules\playwright'
$javascriptFiles = @(
    (Join-Path $root 'app\static\app.js'),
    (Join-Path $root 'app\static\wfm.js'),
    $uiScript
)

Write-Host '1/3 Suite general aislada'
if ($Coverage) {
    & docker run --rm --pull=never --network none --read-only --tmpfs '/tmp:rw,size=512m' `
        --mount "type=bind,source=$root,target=/work,readonly" --workdir /work `
        $ImageName python -B -m trace --count --summary --coverdir=/tmp/coverage `
        --ignore-dir=/usr/local/lib/python3.12:/work/tests --module unittest discover -s tests -q
}
else {
    & docker run --rm --pull=never --network none --read-only --tmpfs '/tmp:rw,size=512m' `
        --mount "type=bind,source=$root,target=/work,readonly" --workdir /work `
        $ImageName python -B -m unittest discover -s tests -q
}
if ($LASTEXITCODE -ne 0) { throw 'La suite general informó fallos.' }

Write-Host '2/3 Sintaxis JavaScript'
$node = Get-Command node -ErrorAction SilentlyContinue
if ($null -eq $node) { throw 'No se encontró Node.js para validar JavaScript.' }
foreach ($file in $javascriptFiles) {
    & $node.Source --check $file
    if ($LASTEXITCODE -ne 0) { throw "La validación JavaScript falló: $file" }
}

if (-not $SkipUiSmoke) {
    if (Test-Path -LiteralPath $playwrightModule -PathType Container) {
        Write-Host 'Prueba UI aislada'
        & $node.Source $uiScript
        if ($LASTEXITCODE -ne 0) { throw 'La prueba UI informó fallos.' }
    }
    else {
        Write-Warning 'Playwright no está instalado localmente; la prueba UI queda omitida. Consulte tools/wfm_offline_build/README.md.'
    }
}

Write-Host '3/3 Suite PostgreSQL aislada'
& (Join-Path $root 'tools\postgres_test_db\run.ps1') -ImageName $ImageName
if ($LASTEXITCODE -ne 0) { throw 'La suite PostgreSQL informó fallos.' }

Write-Host 'Validación completa: OK'
