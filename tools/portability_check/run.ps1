[CmdletBinding()]
param(
    [ValidateSet('ProjectOnly', 'SQLite', 'PostgreSQL')]
    [string]$DataMode = 'ProjectOnly',
    [string]$ImageName = 'librodetrabajo-app:1.30.0',
    [switch]$RequireImage
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path

$required = @(
    'README.md', 'CHANGELOG.md', 'ARCHITECTURE.md', 'DEVELOPMENT.md',
    'DATA_MANIFEST.md', 'SECURITY.md', 'compose.yaml', 'compose.production.yaml',
    'Dockerfile', '.env.example', 'app\application.py', 'app\local_server.py',
    'app\postgres_server.py', 'tools\test_all\run.ps1',
    'tools\postgres_test_db\run.ps1'
)
$missing = @($required | Where-Object { -not (Test-Path -LiteralPath (Join-Path $root $_) -PathType Leaf) })
if ($missing.Count) { throw "Faltan archivos versionados necesarios: $($missing -join ', ')" }

$versionText = Get-Content -LiteralPath (Join-Path $root 'app\application.py') -Raw
$versionMatch = [regex]::Match($versionText, 'APP_VERSION\s*=\s*"(?<version>\d+\.\d+\.\d+)"')
if (-not $versionMatch.Success) { throw 'No se pudo determinar APP_VERSION.' }

$wfmSources = @(
    'data\wfm\telefonistas-horarios-semanales.json',
    'data\wfm\telefonistas-horarios-2026-W37.json'
)
$missingWfm = @($wfmSources | Where-Object { -not (Test-Path -LiteralPath (Join-Path $root $_) -PathType Leaf) })

if ($DataMode -eq 'SQLite' -and -not (Test-Path -LiteralPath (Join-Path $root 'centro_operativo.db') -PathType Leaf)) {
    throw 'Falta centro_operativo.db para el traslado SQLite.'
}
if ($DataMode -eq 'PostgreSQL') {
    $backupDirectory = Join-Path $root 'postgres-backups'
    $dump = Get-ChildItem -LiteralPath $backupDirectory -Filter '*.dump' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    if ($null -eq $dump -or -not (Test-Path -LiteralPath ($dump.FullName + '.sha256') -PathType Leaf)) {
        throw 'Falta un respaldo PostgreSQL acompañado por su archivo .sha256.'
    }
}

if ($RequireImage) {
    & docker image inspect $ImageName *> $null
    if ($LASTEXITCODE -ne 0) { throw "No está disponible la imagen local requerida: $ImageName" }
}

[pscustomobject]@{
    Status = 'OK'
    Version = $versionMatch.Groups['version'].Value
    DataMode = $DataMode
    MissingOptionalWfmSources = $missingWfm.Count
    ImageChecked = [bool]$RequireImage
}
