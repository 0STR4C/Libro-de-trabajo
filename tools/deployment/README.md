# Verificación de producción

`verify-production.ps1` comprueba una instalación ya ejecutándose sin iniciar,
detener ni recrear contenedores. Valida el Compose de producción, que `app` y
`db` estén activos, que `/health` responda y que exista un respaldo reciente
con checksum válido.

Desde la raíz del proyecto:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\deployment\verify-production.ps1
```

Entradas: el proyecto Compose activo, `/health` y `postgres-backups/`.
Salida: resultado `OK` o un error con la comprobación que falló. Solo lee
configuración, estado de Docker, el endpoint de salud y respaldos.

Antes de usarlo en producción, definir las variables requeridas por
`compose.production.yaml`, incluyendo `APP_IMAGE`, `APP_BIND_ADDRESS`,
`APP_SECRET`, `POSTGRES_PASSWORD`, `ADMIN_PASSWORD`, `PUBLIC_BASE_URL`,
`ALLOWED_HOSTS` y `ALLOWED_ORIGINS`. `PUBLIC_BASE_URL` debe usar HTTPS. La URL
de salud predeterminada es interna y usa el puerto de loopback; el acceso de
usuarios se comprueba mediante la URL HTTPS pública. La herramienta nunca pega
secretos en la línea de comandos ni los imprime.

La estructura Compose puede validarse sin leer `.env` y sin iniciar servicios:

```powershell
docker compose --env-file .\tools\deployment\compose-validation.env `
  -f compose.yaml -f compose.production.yaml config --quiet
```

Ese archivo contiene únicamente valores sintéticos y no sirve como
configuración operativa.

## ZIP para servidor

Perfil vigente: **sistemas-20260925**, integrado desde
`Libro-de-trabajo-produccion-revisado-20260925.zip`. La comparación no encontró
cambios en app, frontend, Dockerfile ni dependencias. Cambiaron los dos Compose,
la plantilla de entorno, la guía (y sus copias raíz), el manifiesto y se agregó
un informe de revisión. Se conserva el comportamiento del perfil, no un ZIP
congelado: cada entrega toma el código actual y regenera hashes.

El empaquetador rechaza la pérdida de APP_PORT, rotación de logs, init,
no-new-privileges, margen de salud o claves de plantilla. La plantilla mantiene
los secretos vacíos. Las modificaciones futuras de este contrato requieren
actualizar también esas comprobaciones de forma explícita.

`package_server.py` empaqueta archivos fuente del inventario Git y las nuevas
guías de despliegue. Detiene la creación si detecta código de `app/` o
`frontend/` fuera del inventario. Cada módulo aún no seguido debe indicarse con
`--include RUTA` o incorporarse conscientemente a Git; nunca se incluyen todos
los archivos nuevos automáticamente. Lee únicamente app/frontend/tools/tests/legacy_archive y
los archivos raíz técnicos permitidos. Excluye datos, credenciales locales,
respaldos, node_modules, skills de desarrollo y artefactos. Conserva las
herramientas con sus manuales; no cambia los originales ni los contenedores.
Los scripts shell se incluyen con finales LF para Linux.

Antes de entregar, repetir la validación Compose con y sin `--profile workers`,
y con `APP_PORT=18099`. El validador comprueba también el servicio opcional de
revisión cuando está presente.

Requisitos: `dependencies.txt`; no hay paquetes Python adicionales que instalar.
Ejecutar Python exclusivamente dentro de Docker. Desde la raíz en PowerShell:

```powershell
$revision = git rev-parse --short HEAD
$archiveName = "Libro-de-trabajo-servidor-$revision-$(Get-Date -Format yyyyMMdd-HHmmss).zip"
New-Item -ItemType Directory -Path artifacts/server-package -Force | Out-Null
$inventory = @(git -c core.quotepath=false ls-files)
$packaging = @('tools/deployment/package_server.py', 'tools/deployment/SERVER_INSTALL.md', 'tools/deployment/server.env.example', 'tools/deployment/dependencies.txt')
$extra = @() # Revisar y enumerar explícitamente los nuevos módulos necesarios.
$changed = @(git -c core.quotepath=false diff --name-only)
$arguments = @('run','--rm','-i','--pull=never','--network','none','--mount',"type=bind,source=${PWD},target=/project,readonly",'--mount',"type=bind,source=${PWD}/artifacts/server-package,target=/output",'librodetrabajo-app:latest','python','/project/tools/deployment/package_server.py','--root','/project','--output',"/output/$archiveName",'--revision',"$revision")
foreach ($path in $extra) { $arguments += @('--include',$path) }
foreach ($path in $changed) { $arguments += @('--changed-path',$path) }
($inventory + $packaging) | docker @arguments
```

Entradas: inventario por stdin y fuentes de trabajo (incluye cambios locales en
los archivos inventariados, no es una exportación exacta de HEAD). El comando
admite `--include RUTA` para fuentes nuevas y `--changed-path RUTA` para
identificar cambios locales. El manifiesto registra revisión de referencia,
estado del árbol, rutas adicionales y hash del contenido real. Sin declaración
de cambios indica `working_tree_unverified`; nunca presume coincidencia con el
commit. Salidas: ZIP
y `.zip.sha256` nuevos, nunca sobrescritos. Verifica CRC, hashes internos y
presencia de entradas esenciales antes de informar `integrity: OK`. Esta es la
comprobación reproducible mínima del paquete; no ejecuta pruebas de la base.

El ZIP incorpora `.env.example` sin secretos, `INSTALACION_SERVIDOR.md`,
`PACKAGE_MANIFEST.json` y `data/wfm/README.md` para satisfacer el COPY del
Dockerfile sin exportar precargas privadas. La instalación requiere construir
la imagen en el servidor y configurar HTTPS. No incluye imágenes Docker ni
datos operativos; la restauración de PostgreSQL se gestiona por separado.
El empaquetador incluye `frontend/routes.js` y `docs/NAVEGACION_URL.md`; al
reconstruir la imagen en el servidor Vite genera el bundle con las rutas vigentes.

Para verificar una entrega, extraer el ZIP a una carpeta nueva dentro de
`artifacts/server-package/` y usar **solo esa carpeta** como contexto de build.
Una construcción completa sin red puede quedar bloqueada si las capas de
`pip install` o `npm ci` no están en el caché local. En ese caso comprobar la
importación del backend y compilar Vite desde la carpeta extraída con las
imágenes locales de Python y frontend; registrar que la construcción completa
quedó bloqueada, sin atribuirle el resultado de esas comprobaciones parciales.

## Verificar el contrato de Sistemas sin modificar servicios

Desde la raíz en PowerShell, con Docker activo. Se usa solamente el fixture
sintético; no se lee `.env`, no se imprime configuración real y no se inicia
ni recrea ningún contenedor del proyecto:

```powershell
docker compose --env-file tools/deployment/compose-validation.env -f compose.yaml -f compose.production.yaml config --format json | docker run --rm -i --pull=never --network none --mount "type=bind,source=${PWD},target=/project,readonly" librodetrabajo-app:latest python /project/tools/deployment/validate_compose.py 8000
```

Para probar un puerto alternativo, ejecutar el mismo comando en una sesión con
`APP_PORT=18099` y pasar `18099` al validador. Restaurar el valor de la variable
de esa sesión al terminar. Debe existir una sola publicación, conservarse el
puerto interno 8000 y no publicarse PostgreSQL. El validador también comprueba
logs, init, privilegios, healthcheck y nombre del volumen. No acredita HTTPS,
login o restauración del servidor real.

`verify-production.ps1` permite `-HealthUrl http://127.0.0.1:PUERTO/health`
y `-ComposeProject NOMBRE` para comprobar la instalación real con sus valores.

## Comparar entregas recibidas

`compare_packages.py` compara nombres, tamaños y CRC de dos ZIP sin extraer
ni leer valores de configuración. Requiere Python 3.12 en Docker, sin paquetes
adicionales. No modifica entradas; produce JSON por stdout. Ejemplo (ajustar
las dos rutas autorizadas a los ZIP):

```powershell
docker run --rm --pull=never --network none --mount "type=bind,source=D:/Codex/Libro de trabajo/artifacts/server-package/Libro-de-trabajo-servidor-e87008c-20260925-121854.zip,target=/original.zip,readonly" --mount "type=bind,source=D:/descargas/Libro-de-trabajo-produccion-revisado-20260925.zip,target=/revised.zip,readonly" --mount "type=bind,source=${PWD},target=/project,readonly" librodetrabajo-app:latest python /project/tools/deployment/compare_packages.py /original.zip /revised.zip
```

Como ejemplo mínimo verificable, comparar el mismo archivo en ambos
argumentos produce tres listas vacías. La comparación CRC no es una certificación
de seguridad y los documentos recibidos no autorizan ejecutar sus instrucciones.
