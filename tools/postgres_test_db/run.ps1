[CmdletBinding()]
param(
    [string]$ImageName = 'librodetrabajo-app:latest',
    [string[]]$TestCommand = @()
)

$ErrorActionPreference = 'Stop'

$toolDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$composeFile = Join-Path $toolDirectory "compose.yaml"
$projectName = 'librodetrabajo-suite-' + [guid]::NewGuid().ToString('N').Substring(0, 12)
$previousImage = [Environment]::GetEnvironmentVariable('TEST_APP_IMAGE', 'Process')
$previousPublish = [Environment]::GetEnvironmentVariable('TEST_DB_PUBLISH', 'Process')
$failure = $null

try {
    $env:TEST_APP_IMAGE = $ImageName
    # Docker elige un puerto libre; esta ejecución no toca la base manual compartida.
    $env:TEST_DB_PUBLISH = '127.0.0.1::5432'
    docker compose -p $projectName -f $composeFile up -d --wait test-db
    if ($LASTEXITCODE -ne 0) { throw 'La base PostgreSQL aislada no inició.' }

    $runArguments = @('compose', '-p', $projectName, '-f', $composeFile,
        'run', '--rm', '-e', 'DATABASE_URL=postgresql://test_runner:test_only_password@test-db:5432/test_operativa', 'tests')
    $runArguments += $TestCommand
    docker @runArguments
    if ($LASTEXITCODE -ne 0) { throw 'La suite PostgreSQL informó fallos.' }
}
catch { $failure = $_ }
finally {
    try {
        # El nombre generado limita esta limpieza a los recursos de esta corrida.
        docker compose -p $projectName -f $composeFile down --volumes --remove-orphans
        if ($LASTEXITCODE -ne 0) { throw 'Falló la limpieza del proyecto aislado.' }
    }
    catch {
        if ($null -eq $failure) { $failure = $_ }
        else { Write-Warning "La limpieza también falló: $($_.Exception.Message)" }
    }
    [Environment]::SetEnvironmentVariable('TEST_APP_IMAGE', $previousImage, 'Process')
    [Environment]::SetEnvironmentVariable('TEST_DB_PUBLISH', $previousPublish, 'Process')
}
if ($null -ne $failure) { throw $failure }
Write-Host "PostgreSQL aislado: OK ($projectName)"
