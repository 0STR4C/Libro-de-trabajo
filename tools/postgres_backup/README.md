# Respaldo periódico de PostgreSQL

Genera un `pg_dump` en formato personalizado, valida que su catálogo pueda leerse con `pg_restore` y guarda un archivo SHA-256. El servicio Docker lo ejecuta cada hora por defecto y nunca elimina respaldos existentes.

## Entradas

- `POSTGRES_DB`, `POSTGRES_USER` y `POSTGRES_PASSWORD`.
- `BACKUP_INTERVAL_SECONDS`, con valor predeterminado `3600` y mínimo `300`.
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

## Restauración de prueba aislada

La restauración debe ejecutarse sobre una base temporal y separada del volumen
`librodetrabajo_postgres_data`. Antes de hacerlo, comprobar el nombre exacto del
dump y su SHA-256. Un ejemplo usa un proyecto Compose temporal, sin publicar
puertos:

```powershell
$testProject = 'centro-operativo-restore-test'
docker compose -p $testProject -f compose.yaml up -d db
docker compose -p $testProject -f compose.yaml run --rm --no-deps --entrypoint sh backup -ec 'PGPASSWORD="$POSTGRES_PASSWORD" createdb -h db -U "$POSTGRES_USER" restore_test'
docker compose -p $testProject -f compose.yaml run --rm --no-deps --entrypoint sh backup -ec 'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -h db -U "$POSTGRES_USER" -d restore_test --exit-on-error /backups/ARCHIVO.dump'
docker compose -p $testProject -f compose.yaml run --rm --no-deps --entrypoint sh backup -ec 'PGPASSWORD="$POSTGRES_PASSWORD" psql -h db -U "$POSTGRES_USER" -d restore_test -c "SELECT count(*) FROM users"'
docker compose -p $testProject -f compose.yaml down -v
```

El ejemplo requiere un `db` temporal del proyecto de prueba y un montaje de
`postgres-backups` de solo lectura. No debe apuntar al servicio `db` activo ni
usar `docker compose down -v` sobre el proyecto operativo. Al finalizar,
eliminar solamente los recursos identificados del proyecto temporal y conservar
el dump y su archivo `.sha256`.
