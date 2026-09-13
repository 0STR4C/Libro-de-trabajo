[CmdletBinding()]
param(
    [string]$DumpPath = '',
    [string]$ImageName = 'librodetrabajo-app:latest',
    [string]$DockerPath = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-Docker {
    param([string]$Requested)
    if ($Requested) { return (Resolve-Path -LiteralPath $Requested -ErrorAction Stop).Path }
    $command = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $command) { throw 'No se encontró docker.exe.' }
    return $command.Source
}

$docker = Resolve-Docker $DockerPath
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$backupDirectory = Join-Path $projectRoot 'postgres-backups'
if (-not $DumpPath) {
    $DumpPath = (Get-ChildItem -LiteralPath $backupDirectory -Filter '*.dump' -File |
        Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1).FullName
}
if (-not $DumpPath -or -not (Test-Path -LiteralPath $DumpPath -PathType Leaf)) {
    throw 'Indique un dump existente mediante -DumpPath.'
}
$dump = Get-Item -LiteralPath $DumpPath
$backupDirectory = $dump.Directory.FullName
$sidecar = "$($dump.FullName).sha256"
if (-not (Test-Path -LiteralPath $sidecar -PathType Leaf)) { throw "Falta el checksum: $sidecar" }

& $docker image inspect $ImageName *> $null
if ($LASTEXITCODE -ne 0) { throw "No existe la imagen $ImageName." }

$container = "centro-restore-test-$PID-$(Get-Random -Minimum 1000 -Maximum 9999)"
$dbName = 'restore_test'
$dbUser = 'restore_test_user'
$dbPassword = 'ephemeral-restore-only'
$started = $false
function Invoke-RestorePsql {
    param([string]$Sql)
    $result = @(& $docker exec $container psql -U $dbUser -d $dbName -AtF '|' -c $Sql)
    if ($LASTEXITCODE -ne 0) { throw "Falló la consulta de validación: $Sql" }
    return $result
}

try {
    & $docker run --detach --rm --name $container --network none --tmpfs '/var/lib/postgresql/data:rw,size=512m' `
        --mount "type=bind,source=$backupDirectory,target=/backups,readonly" `
        --env "POSTGRES_DB=$dbName" --env "POSTGRES_USER=$dbUser" --env "POSTGRES_PASSWORD=$dbPassword" `
        postgres:16-alpine | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo iniciar PostgreSQL temporal.' }
    $started = $true

    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        & $docker exec $container pg_isready -U $dbUser -d $dbName *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Milliseconds 250
    }
    if (-not $ready) { throw 'PostgreSQL temporal no quedó disponible.' }

    & $docker exec $container sha256sum -c "/backups/$($dump.Name).sha256" *> $null
    if ($LASTEXITCODE -ne 0) { throw 'El checksum del dump no coincide.' }
    & $docker exec $container pg_restore -U $dbUser -d $dbName --exit-on-error --no-owner "/backups/$($dump.Name)" *> $null
    if ($LASTEXITCODE -ne 0) { throw 'pg_restore falló.' }

    $tables = @(Invoke-RestorePsql "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
    $totalRows = 0L
    foreach ($table in $tables) {
        if ($table -notmatch '^[a-z_][a-z0-9_]*$') { throw "Nombre de tabla inesperado: $table" }
        $rowCount = @(Invoke-RestorePsql "SELECT count(*) FROM `"$table`"")
        $totalRows += [long]$rowCount[0]
    }
    $invalidRows = @(Invoke-RestorePsql "SELECT count(*) FROM pg_constraint WHERE connamespace='public'::regnamespace AND NOT convalidated")
    $invalidConstraints = [int]$invalidRows[0]
    $orphanRows = @(Invoke-RestorePsql "SELECT (SELECT count(*) FROM wfm_published_shifts s LEFT JOIN users u ON u.id=s.user_id WHERE u.id IS NULL) + (SELECT count(*) FROM wfm_requests r LEFT JOIN users u ON u.id=r.user_id WHERE u.id IS NULL)")
    $orphanWfm = [int]$orphanRows[0]
    $serials = @(Invoke-RestorePsql "SELECT table_name,column_name,pg_get_serial_sequence(format('%I.%I',table_schema,table_name),column_name) FROM information_schema.columns WHERE table_schema='public' AND column_default LIKE 'nextval(%'")
    $sequenceProblems = 0
    foreach ($serial in $serials) {
        $parts = $serial.Split('|', 3)
        $table = $parts[0]; $column = $parts[1]; $sequence = $parts[2]
        if ($table -notmatch '^[a-z_][a-z0-9_]*$' -or $column -notmatch '^[a-z_][a-z0-9_]*$' -or $sequence -notmatch '^public\.[a-z_][a-z0-9_]*$') { throw "Secuencia inesperada: $serial" }
        $maxRows = @(Invoke-RestorePsql "SELECT coalesce(max(`"$column`"),0) FROM `"$table`"")
        $maxId = [long]$maxRows[0]
        $stateRows = @(Invoke-RestorePsql "SELECT last_value,is_called FROM $sequence")
        $state = $stateRows[0].Split('|', 2)
        $next = if ($state[1] -eq 't') { [long]$state[0] + 1 } else { [long]$state[0] }
        if ($next -le $maxId) { $sequenceProblems++ }
    }

    & $docker run --rm --pull=never --network "container:$container" `
        --env "DATABASE_URL=postgresql://${dbUser}:${dbPassword}@127.0.0.1:5432/${dbName}" `
        --env 'APP_ENV=development' --env 'APP_SECRET=ephemeral-restore-test-secret' `
        --env 'POSTGRES_PASSWORD=ephemeral-restore-only' --env 'ADMIN_PASSWORD=ephemeral-admin-password' `
        $ImageName python -B -c "from app.postgres_server import initialize; initialize(); print('SCHEMA_INIT_OK')" *> $null
    if ($LASTEXITCODE -ne 0) { throw 'La aplicación no pudo inicializar el esquema restaurado.' }

    [pscustomobject]@{
        Status = 'OK'
        Dump = $dump.Name
        Bytes = $dump.Length
        PublicTables = $tables.Count
        TotalRows = $totalRows
        InvalidConstraints = $invalidConstraints
        WfmOrphanUserReferences = $orphanWfm
        SerialColumnsChecked = $serials.Count
        SequenceProblems = $sequenceProblems
        SchemaInitialization = 'OK'
    }
}
finally {
    if ($started) { & $docker stop --time 5 $container *> $null }
}
