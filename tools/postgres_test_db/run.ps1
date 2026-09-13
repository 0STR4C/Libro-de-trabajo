$ErrorActionPreference = "Stop"

$toolDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$composeFile = Join-Path $toolDirectory "compose.yaml"
$projectName = "librodetrabajo-tests"
$suiteDatabase = "suite_" + ([guid]::NewGuid().ToString("N"))
$suiteUrl = "postgresql://test_runner:test_only_password@test-db:5432/$suiteDatabase"

try {
    docker compose -p $projectName -f $composeFile up -d --wait test-db
    if ($LASTEXITCODE -ne 0) { throw "La base PostgreSQL temporal no inició correctamente." }

    docker compose -p $projectName -f $composeFile exec -T test-db createdb -U test_runner $suiteDatabase
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear la base aislada de esta ejecución." }

    docker compose -p $projectName -f $composeFile run --rm `
        -e "SECURITY_TEST_DATABASE_URL=$suiteUrl" `
        tests
    if ($LASTEXITCODE -ne 0) { throw "La suite PostgreSQL informó fallos." }
}
finally {
    try {
        docker compose -p $projectName -f $composeFile exec -T test-db `
            dropdb -U test_runner --if-exists $suiteDatabase
    }
    finally {
        docker compose -p $projectName -f $composeFile stop test-db
    }
}
