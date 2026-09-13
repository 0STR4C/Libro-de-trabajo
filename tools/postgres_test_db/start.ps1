$ErrorActionPreference = "Stop"

$toolDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$composeFile = Join-Path $toolDirectory "compose.yaml"

docker compose -p librodetrabajo-tests -f $composeFile up -d --wait test-db
if ($LASTEXITCODE -ne 0) { throw "La base PostgreSQL de pruebas no inició correctamente." }

Write-Host "PostgreSQL de pruebas disponible en 127.0.0.1:54329/test_operativa"
