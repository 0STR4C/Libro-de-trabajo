# Respaldo periódico de PostgreSQL

Genera un `pg_dump` en formato personalizado, valida que su catálogo pueda leerse con `pg_restore` y guarda un archivo SHA-256. El servicio Docker lo ejecuta cada 15 minutos por defecto, reintenta fallos transitorios y nunca elimina respaldos existentes.

## Entradas

- `POSTGRES_DB`, `POSTGRES_USER` y `POSTGRES_PASSWORD`.
- `BACKUP_INTERVAL_SECONDS`, con valor predeterminado `900` (15 minutos) y mínimo `300`.
- `BACKUP_MAX_AGE_SECONDS`, con valor predeterminado `5400` (90 minutos); define cuándo el servicio pasa a no saludable.
- Volumen de salida montado en `/backups`.

## Salidas y modificaciones

Escribe archivos `centro_operativo_YYYYMMDDTHHMMSSZ.dump` y `.dump.sha256` en `postgres-backups/`. Solo lee PostgreSQL. No modifica `centro_operativo.db` ni elimina copias antiguas.

## Ejecución

El servicio se inicia junto con la aplicación mediante:

```powershell
docker compose up -d app
```

Para una única copia manual:

```powershell
docker compose run --rm -e BACKUP_RUN_ONCE=1 backup
```

## Verificación mínima

```powershell
docker compose run --rm -e BACKUP_RUN_ONCE=1 backup
docker compose exec -T backup sh -c 'latest=$(ls -1t /backups/*.dump | head -n 1); pg_restore --list "$latest" >/dev/null && echo OK'
```

Cada copia también se valida internamente antes de publicarse.

El servicio `backup` tiene un `healthcheck` que exige que exista un dump reciente
y que su SHA-256 siga siendo válido. La aplicación espera a que ese servicio esté
saludable antes de iniciar.

## Monitoreo local de frescura e integridad

`check_backups.ps1` es una comprobación de solo lectura para un programador
local o una supervisión externa. Selecciona el `.dump` más reciente, exige su
archivo `.sha256`, recalcula el hash y falla si la copia supera 90 minutos por
defecto. No elimina ni modifica respaldos.

```powershell
powershell -ExecutionPolicy Bypass -NoProfile -File .\tools\postgres_backup\check_backups.ps1
powershell -ExecutionPolicy Bypass -NoProfile -File .\tools\postgres_backup\check_backups.ps1 -MaxAgeMinutes 120
```

La alerta debe tratarse como incidente de continuidad: conservar los archivos
para análisis, revisar el contenedor `backup` y generar una copia manual si la
base sigue disponible.

Para una comprobación completa y repetible, usar
`tools/postgres_restore_test/run.ps1`, que restaura en un contenedor descartable,
valida las relaciones y secuencias y ejecuta la inicialización de la aplicación.

## Restauración de prueba aislada

La restauración debe ejecutarse sobre una base temporal y separada del volumen
`librodetrabajo_postgres_data`. Antes de hacerlo, comprobar el nombre exacto del
dump y su SHA-256. Un ejemplo usa un proyecto Compose temporal, sin publicar
puertos:

```powershell
$testProject = 'centro-operativo-restore-test'
docker compose -p $testProject -f compose.yaml up -d db
docker compose -p $testProject -f compose.yaml run --rm --no-deps --entrypoint sh backup -ec 'PGPASSWORD="$POSTGRES_PASSWORD" createdb -h db -U "$POSTGRES_USER" restore_test'
docker compose -p $testProject -f compose.yaml run --rm --no-deps --entrypoint sh backup -ec 'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -h db -U "$POSTGRES_USER" -d restore_test --exit-on-error --no-owner /backups/ARCHIVO.dump'
docker compose -p $testProject -f compose.yaml run --rm --no-deps --entrypoint sh backup -ec 'PGPASSWORD="$POSTGRES_PASSWORD" psql -h db -U "$POSTGRES_USER" -d restore_test -c "SELECT count(*) FROM users"'
docker compose -p $testProject -f compose.yaml down -v
```

El ejemplo requiere un `db` temporal del proyecto de prueba y un montaje de
`postgres-backups` de solo lectura. No debe apuntar al servicio `db` activo ni
usar `docker compose down -v` sobre el proyecto operativo. Al finalizar,
eliminar solamente los recursos identificados del proyecto temporal y conservar
el dump y su archivo `.sha256`.
