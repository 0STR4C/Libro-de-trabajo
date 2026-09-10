$ErrorActionPreference='Stop'
$bookRoot=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$bookExe=Join-Path $bookRoot 'tools/desktop_launcher/dist-libro/LibroDeTrabajo.exe'
$bookLink=Join-Path $bookRoot 'Libro de Trabajo.lnk'
if(-not (Test-Path -LiteralPath $bookExe)){throw 'Primero compile LibroDeTrabajo.exe'}
if(Test-Path -LiteralPath $bookLink){throw 'El acceso directo ya existe; no se reemplaza'}
$bookShell=New-Object -ComObject WScript.Shell
$bookShortcut=$bookShell.CreateShortcut($bookLink)
$bookShortcut.TargetPath=$bookExe
$bookShortcut.WorkingDirectory=$bookRoot
$bookShortcut.IconLocation="$bookExe,0"
$bookShortcut.Description='Libro de Trabajo · Centro Operativo'
$bookShortcut.Save()
Write-Output 'Acceso directo creado únicamente en la carpeta del proyecto.'
