param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
)

$ErrorActionPreference = 'Stop'
$projectFile = Join-Path $ProjectRoot 'tools\desktop_launcher\CentroOperativoLauncher.csproj'
$sourceFile = Join-Path $ProjectRoot 'tools\desktop_launcher\Program.cs'
if (-not (Test-Path -LiteralPath $projectFile)) { throw "No existe $projectFile" }
if (-not (Test-Path -LiteralPath $sourceFile)) { throw "No existe $sourceFile" }
$source = Get-Content -Raw -LiteralPath $sourceFile
if ($source -match 'down.*-v') { throw 'El lanzador no debe eliminar volúmenes.' }
if ($source -match 'centro_operativo\.db') { throw 'El lanzador no debe operar sobre la base SQLite.' }
if ($source -notmatch 'compose.*up') { throw 'El lanzador debe iniciar Compose.' }
Write-Output 'OK: estructura y guardas del lanzador verificadas.'
