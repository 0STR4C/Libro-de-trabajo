$ErrorActionPreference = "Stop"

$toolDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$composeFile = Join-Path $toolDirectory "compose.yaml"

docker compose -p librodetrabajo-tests -f $composeFile stop test-db
if ($LASTEXITCODE -ne 0) { throw "No se pudo detener PostgreSQL de pruebas." }

Write-Host "PostgreSQL de pruebas detenido. Sus datos permanecen en el volumen Docker."
