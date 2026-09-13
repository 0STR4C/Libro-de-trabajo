[CmdletBinding()]
param(
    [string]$ComposeProject = '',
    [string]$HealthUrl = 'http://127.0.0.1:8000/health',
    [int]$MaxBackupAgeMinutes = 90
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
Push-Location $root
try {
    $composeArgs = @('-f', 'compose.yaml', '-f', 'compose.production.yaml')
    if ($ComposeProject) { $composeArgs = @('-p', $ComposeProject) + $composeArgs }

    # Solo valida la configuración; no inicia, detiene ni recrea servicios.
    & docker compose @composeArgs config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'La configuración Compose de producción no es válida.' }

    $containers = @(docker compose @composeArgs ps --format json | ConvertFrom-Json)
    if ($containers.Count -eq 0) { throw 'No hay servicios de producción ejecutándose.' }
    $app = $containers | Where-Object { $_.Service -eq 'app' } | Select-Object -First 1
    $db = $containers | Where-Object { $_.Service -eq 'db' } | Select-Object -First 1
    if ($null -eq $app -or $app.State -notmatch 'running') { throw 'El servicio app no está ejecutándose.' }
    if ($null -eq $db -or $db.State -notmatch 'running') { throw 'El servicio db no está ejecutándose.' }

    $health = Invoke-WebRequest -Uri $HealthUrl -TimeoutSec 10
    if ($health.StatusCode -ne 200) { throw "Healthcheck devolvió HTTP $($health.StatusCode)." }

    $backupScript = Join-Path $root 'tools\postgres_backup\check_backups.ps1'
    & powershell -NoProfile -ExecutionPolicy Bypass -File $backupScript -MaxAgeMinutes $MaxBackupAgeMinutes | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'La comprobación de respaldos falló.' }

    [pscustomobject]@{
        Status = 'OK'
        App = $app.Name
        Database = $db.Name
        Health = $health.Content
        CheckedAt = (Get-Date).ToUniversalTime().ToString('o')
    }
}
finally {
    Pop-Location
}
