# Instalar Libro de Trabajo en un servidor

Este paquete contiene código fuente, bundle frontend y herramientas. No contiene
credenciales, bases de datos, respaldos, imágenes Docker ni dependencias instaladas.
Una instalación nueva crea una base vacía y el administrador inicial configurado.
El manifiesto identifica la revisión base y el hash de cada archivo incluido.

## 1. Requisitos

- Docker Engine o Docker Desktop ejecutando contenedores Linux y Docker Compose v2.
- Acceso desde el servidor a los registros de imágenes Docker, npm y PyPI para
  la primera construcción. Las dependencias Node y Python se instalan en la imagen;
  no hace falta instalarlas en el host.
- Nombre DNS y proxy inverso con certificado HTTPS válido. El proxy en el mismo
  servidor debe enviar las peticiones a `http://127.0.0.1:PUERTO_ELEGIDO`.

Descomprimir en una carpeta permanente y ejecutar los comandos desde esa carpeta.
No mezclar este paquete con una instalación existente sin planificar sus datos.

## 2. Configuración

Linux:

```sh
cp .env.example .env
chmod 600 .env
mkdir -p postgres-backups
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
New-Item -ItemType Directory -Path postgres-backups -Force
```

Editar `.env` localmente con un editor seguro:

- Completar `POSTGRES_PASSWORD` con una contraseña aleatoria hexadecimal larga;
  `APP_SECRET` con un secreto aleatorio de al menos 32 caracteres;
  `ADMIN_PASSWORD` con una contraseña única de al menos 12 caracteres.
- Cambiar `PUBLIC_BASE_URL`, `ALLOWED_HOSTS` y `ALLOWED_ORIGINS` al dominio real.
- Conservar `APP_IMAGE=librodetrabajo-app:server` y `APP_BIND_ADDRESS=127.0.0.1`
  para el procedimiento indicado.
- No compartir `.env` ni pegar su contenido en la consola o en chats.

La configuración de producción exige HTTPS. El endpoint `/health` puede
consultarse por loopback, pero los usuarios ingresan por el dominio HTTPS.
Si el proxy se ejecuta en otro contenedor o equipo, hay que adaptar su conexión;
`127.0.0.1` siempre corresponde al entorno desde el cual se hace la petición.

## 3. Construir e iniciar

```sh
docker compose --env-file .env -f compose.yaml -f compose.production.yaml config --quiet
docker build -t librodetrabajo-app:server .
docker compose --env-file .env -f compose.yaml -f compose.production.yaml up -d --no-build --wait --wait-timeout 240
docker compose --env-file .env -f compose.yaml -f compose.production.yaml ps
```

Continuar solo si cada comando termina correctamente. `app`, `db` y `backup`
deben aparecer saludables. El Dockerfile ejecuta Vite durante la construcción.
La carpeta vacía `data/wfm` incluida satisface el COPY de precargas opcionales;
no contiene horarios ni usuarios importados.

Para verificar salud en Linux: `curl --fail http://127.0.0.1:PUERTO_ELEGIDO/health`.
En PowerShell: `Invoke-WebRequest http://127.0.0.1:PUERTO_ELEGIDO/health`.
Abrir luego el dominio HTTPS y usar `ADMIN_USER` / `ADMIN_PASSWORD` definidos
para inicializar la base. Las cuentas existentes en una base restaurada conservan
sus propias credenciales; `ADMIN_PASSWORD` no las reemplaza.

## 4. Si se necesitan los datos actuales

Este ZIP no transfiere la operación local. Para conservar avisos, horarios,
tarifas, usuarios y demás registros se necesita un respaldo PostgreSQL con su
checksum, transferido de forma autorizada y restaurado antes de habilitar usuarios.
Seguir `ARCHITECTURE.md` y los manuales de `tools/postgres_restore_test/`.
No ejecutar la migración SQLite sobre una base PostgreSQL ya operativa.

Los datos PostgreSQL quedan en un volumen Docker; los dumps automáticos quedan
en `postgres-backups/`. No ejecutar `docker compose down -v`: elimina volúmenes.
Configurar además el destino de copias externas conforme a la política del servidor.

## Contrato de despliegue de Sistemas · 25/09/2026

Estos ajustes se conservarán en todas las entregas, tomando como referencia
`Libro-de-trabajo-produccion-revisado-20260925.zip`:

- `APP_PORT` define el puerto publicado del host; el contenedor sigue usando 8000.
  Elegir un puerto libre y sustituir `PUERTO_ELEGIDO` en esta guía por ese número.
  La dirección loopback se conserva cuando el proxy corre en el mismo servidor.
- La plantilla propone `COMPOSE_PROJECT_NAME=libro-trabajo`. En una instalación
  existente, conservar EXACTAMENTE el nombre que Sistemas ya está usando, aunque
  sea diferente: cambiarlo crearía otros volúmenes y parecería perder los datos.
- Usar una carpeta permanente y siempre ambos archivos Compose. `compose.yaml`
  solo mantiene valores de desarrollo. El ZIP no configura DNS, certificados,
  proxy, firewall ni asigna puertos en el servidor.
- El proxy HTTPS debe preservar Host con el dominio público; configurar el
  dominio real en URL, hosts y orígenes. No habilitar cookies de producción por HTTP.
- El proxy debe reenviar la ruta original completa, incluidos accesos directos
  como `/programados` y `/configuracion/tiempos-estandar`, al mismo backend que
  recibe `/api`, `/static` y `/health`. La aplicación resuelve esas rutas; no
  configurar un fallback del proxy que convierta API o archivos faltantes en HTML.
  Véase `docs/NAVEGACION_URL.md`.
- Producción limita los logs a tres archivos de 10 MB por servicio. App usa
  proceso init, `no-new-privileges` y un margen inicial de healthcheck de 60 s.
  El arranque concede hasta 240 s para esperar salud de los servicios.
- `BACKUP_MAX_AGE_SECONDS=5400` define la antigüedad máxima permitida por el
  healthcheck del backup. No es una política de retención. Los dumps siguen
  requiriendo monitoreo de espacio, copia externa y restauraciones de prueba.
- Un contenedor unhealthy no se reinicia automáticamente solo por ese estado.
  La salud del backup verifica frescura/checksum, no una restauración completa.
- Usar contraseñas aleatorias; la contraseña PostgreSQL hexadecimal evita
  caracteres reservados de URL. Valores con `$` deben citarse adecuadamente en
  `.env`. No imprimir `compose config` con credenciales reales; usar `--quiet`.

### Actualizar una instalación existente

Conservar `.env`, `COMPOSE_PROJECT_NAME`, `APP_PORT`, la carpeta de respaldos y
los volúmenes existentes. No reemplazar `.env` por `.env.example`. Guardar la imagen
anterior y un respaldo verificado antes de reconstruir y arrancar la nueva versión.
La plantilla del ZIP es únicamente para altas nuevas; no migra los datos actuales.
Revertir una imagen no revierte cambios de esquema de la base de datos.

Antes de habilitar usuarios, Sistemas debe verificar en el servidor: salud de
app/db/backup, HTTPS, login, lectura/escritura, persistencia tras reinicio y
restauración aislada. La revisión del ZIP recibido fue estática y declaraba que
no se había arrancado Docker; no debe interpretarse como certificación del host.
