[CmdletBinding()]
param(
    [string]$BackupDirectory = (Join-Path (Get-Location) 'postgres-backups'),
    [ValidateRange(1, 10080)]
    [int]$MaxAgeMinutes = 90
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $BackupDirectory -PathType Container)) {
    throw "No existe el directorio de respaldos: $BackupDirectory"
}

$latest = Get-ChildItem -LiteralPath $BackupDirectory -Filter '*.dump' -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if ($null -eq $latest) {
    throw "No hay archivos .dump en $BackupDirectory"
}

$sidecarPath = "$($latest.FullName).sha256"
if (-not (Test-Path -LiteralPath $sidecarPath -PathType Leaf)) {
    throw "Falta el checksum asociado: $sidecarPath"
}

$expected = ((Get-Content -LiteralPath $sidecarPath -Raw) -split '\s+')[0].Trim().ToLowerInvariant()
if ($expected -notmatch '^[0-9a-f]{64}$') {
    throw "El checksum no tiene formato SHA-256: $sidecarPath"
}

$actual = (Get-FileHash -LiteralPath $latest.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) {
    throw "El checksum no coincide para $($latest.Name)"
}

$ageMinutes = ((Get-Date) - $latest.LastWriteTime).TotalMinutes
if ($ageMinutes -gt $MaxAgeMinutes) {
    throw ("El último respaldo tiene {0:N1} minutos; el máximo permitido es {1} minutos" -f $ageMinutes, $MaxAgeMinutes)
}

[pscustomobject]@{
    Status = 'OK'
    Backup = $latest.Name
    Bytes = $latest.Length
    LastWriteTime = $latest.LastWriteTime
    AgeMinutes = [math]::Round($ageMinutes, 1)
    SHA256 = $actual
    MaxAgeMinutes = $MaxAgeMinutes
}
