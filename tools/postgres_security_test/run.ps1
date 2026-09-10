[CmdletBinding()]
param(
    [string]$DockerPath = "",
    [string]$ImageName = "librodetrabajo-app:latest"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-DockerExecutable {
    param([string]$RequestedPath)
    if ($RequestedPath) {
        if (-not (Test-Path -LiteralPath $RequestedPath -PathType Leaf)) {
            throw "No se encontró Docker en la ruta indicada: $RequestedPath"
        }
        return (Resolve-Path -LiteralPath $RequestedPath).Path
    }

    $command = Get-Command docker -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\resources\bin\docker.exe"),
        (Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }
    throw "No se encontró docker.exe. Inicie Docker Desktop o indique -DockerPath."
}

$dockerExecutable = Resolve-DockerExecutable $DockerPath
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
$testsPath = Join-Path $projectRoot "tests"
$containerName = "centro-operativo-security-test-$PID-$(Get-Random -Minimum 1000 -Maximum 9999)"
$databaseName = "centro_security_test"
$databaseUser = "centro_test"
$databasePassword = "ephemeral-test-only"
$started = $false

& $dockerExecutable image inspect $imageName *> $null
if ($LASTEXITCODE -ne 0) {
    throw "No existe $imageName. Ejecute primero: docker compose build app"
}

try {
    & $dockerExecutable run --detach --rm --name $containerName `
        --tmpfs "/var/lib/postgresql/data:rw,size=512m" `
        --env "POSTGRES_DB=$databaseName" `
        --env "POSTGRES_USER=$databaseUser" `
        --env "POSTGRES_PASSWORD=$databasePassword" `
        postgres:16-alpine *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo iniciar la PostgreSQL temporal."
    }
    $started = $true

    $ready = $false
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        & $dockerExecutable exec $containerName pg_isready -U $databaseUser -d $databaseName *> $null
        if ($LASTEXITCODE -eq 0) {
            $ready = $true
            break
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) {
        throw "La PostgreSQL temporal no quedó saludable dentro del plazo esperado."
    }

    $databaseUrl = "postgresql://${databaseUser}:${databasePassword}@127.0.0.1:5432/${databaseName}"
    & $dockerExecutable run --rm --network "container:$containerName" `
        --mount "type=bind,source=$testsPath,target=/app/tests,readonly" `
        --env "SECURITY_TEST_DATABASE_URL=$databaseUrl" `
        --env "APP_ENV=development" `
        --env "APP_SECRET=ephemeral-test-secret-1234567890abcdef" `
        --env "ADMIN_PASSWORD=ephemeral-admin-password" `
        $imageName python -B -m unittest discover -s /app/tests -p test_postgres_security.py -v
    if ($LASTEXITCODE -ne 0) {
        throw "La suite de seguridad PostgreSQL falló."
    }
}
finally {
    if ($started) {
        & $dockerExecutable stop --time 5 $containerName *> $null
    }
}

Write-Host "Suite PostgreSQL completada sobre una base efímera sin volumen persistente."
