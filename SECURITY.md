# Seguridad de Centro Operativo

## Estado y alcance

La aplicación contiene información operativa. El diseño previsto es: Docker en el servidor, PostgreSQL sin puerto publicado y acceso web limitado a la red local autorizada. No se debe publicar PostgreSQL en la red ni modificar automáticamente el Firewall de Windows como parte de este proyecto.

La base `centro_operativo.db` es un origen histórico protegido. No se usa para la operación PostgreSQL, no se sobrescribe y no se elimina.

## Modelo de amenazas

Se consideran amenazas principales:

- exposición accidental del puerto web o de PostgreSQL en la red local o Internet;
- filtración de credenciales de Compose, sesiones o contraseñas;
- robo de una computadora que tenga una sesión abierta;
- intentos automatizados de ingreso y enumeración de usuarios;
- solicitudes modificadoras enviadas desde otro origen mediante una sesión del navegador;
- pérdida o corrupción del disco que contiene PostgreSQL y sus copias;
- permisos excesivos en usuarios, roles, tarifas y exportaciones.

La protección no sustituye copias fuera del mismo disco, control de acceso al sistema operativo ni actualizaciones de Docker.

## Desarrollo y producción

`APP_ENV=development` permite valores locales de conveniencia y HTTP sobre localhost. No debe usarse para un servidor compartido.

`APP_ENV=production` debe rechazar el arranque si `APP_SECRET`, `POSTGRES_PASSWORD` o `ADMIN_PASSWORD` faltan, son marcadores/predeterminados o no alcanzan la longitud mínima. En producción:

- la sesión usa cookie HttpOnly, Secure y SameSite=Strict;
- `/docs`, `/redoc` y OpenAPI permanecen deshabilitados salvo habilitación explícita;
- los hosts y orígenes de la red local deben declararse de forma explícita;
- PostgreSQL continúa sin puerto publicado por Compose.

La variable `ADMIN_PASSWORD` solo sirve para inicializar una base sin usuarios. La aplicación no cambia automáticamente la contraseña de un administrador ya existente. En una base restaurada, cambiar la contraseña del administrador desde Configuración antes de habilitar el acceso remoto.

## Generación segura de configuración

Ejecutar el procedimiento desde PowerShell ubicado en la carpeta del proyecto. No escribir secretos literalmente en la línea de comandos ni imprimir el contenido de `.env`:

```powershell
$envFile = Join-Path (Get-Location) '.env'
$appBytes = [byte[]]::new(32)
[System.Security.Cryptography.RandomNumberGenerator]::Fill($appBytes)
$appSecret = [Convert]::ToHexString($appBytes).ToLowerInvariant()
$dbBytes = [byte[]]::new(32)
[System.Security.Cryptography.RandomNumberGenerator]::Fill($dbBytes)
$postgresPassword = [Convert]::ToHexString($dbBytes).ToLowerInvariant()
$adminSecure = Read-Host 'Contraseña inicial del administrador (12 caracteres o más)' -AsSecureString
$adminPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($adminSecure)
try { $adminPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($adminPtr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($adminPtr) }
@"
APP_ENV=production
POSTGRES_DB=operativa
POSTGRES_USER=operativa
POSTGRES_PASSWORD=$postgresPassword
DATABASE_URL=postgresql://operativa:$postgresPassword@db:5432/operativa
APP_SECRET=$appSecret
SESSION_SECONDS=43200
SESSION_IDLE_SECONDS=1800
ALLOWED_HOSTS=localhost,127.0.0.1,NOMBRE_O_IP_LAN_DEL_SERVIDOR
ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000,http://NOMBRE_O_IP_LAN_DEL_SERVIDOR:8000
MAX_BODY_BYTES=1048576
ENABLE_API_DOCS=false
ADMIN_USER=admin
ADMIN_PASSWORD=$adminPassword
BACKUP_INTERVAL_SECONDS=900
"@ | Set-Content -LiteralPath $envFile -Encoding utf8
Remove-Variable adminPassword,appSecret,postgresPassword,appBytes,dbBytes,adminSecure -ErrorAction SilentlyContinue
```

El archivo `.env` está excluido por `.gitignore`, pero debe recibir permisos de lectura únicamente para la cuenta que administra Docker. No se debe pegar su contenido en chats, tickets ni logs.

En una instalación existente, `POSTGRES_PASSWORD` no cambia la contraseña del rol PostgreSQL ya creado. La rotación de esa contraseña debe coordinarse como una operación separada: respaldo verificado, cambio del rol y reinicio coordinado de `app` y `backup`. No se debe ejecutar sobre la base activa sin una ventana de mantenimiento.

## Sesiones y revocación

Las sesiones se guardan en PostgreSQL como hashes. El navegador no recibe un Bearer token ni lo guarda en Web Storage. Las operaciones modificadoras requieren CSRF ligado a la sesión. Las sesiones tienen vencimiento absoluto y por inactividad; cambiar una contraseña o desactivar un usuario revoca sus sesiones.

Si se pierde una computadora:

1. Desactivar inmediatamente sus usuarios desde Configuración.
2. Cambiar las contraseñas afectadas.
3. Rotar `APP_SECRET` en una ventana coordinada para invalidar cualquier sesión restante.
4. Revisar el Log del sistema y los respaldos.
5. Si también se expuso la credencial de PostgreSQL, rotar el rol y reiniciar los servicios.

## Respaldos y restauración

Los respaldos horarios del servicio `backup` no deben ser servidos por FastAPI ni considerarse protección suficiente si permanecen en el mismo disco. No se carga ninguna copia a una nube desde la aplicación.

Toda restauración de prueba debe usar una base separada, un volumen temporal y un nombre de proyecto Compose distinto. Nunca se debe restaurar un dump de prueba sobre `librodetrabajo_postgres_data`.
