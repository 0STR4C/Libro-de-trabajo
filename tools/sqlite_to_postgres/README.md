# Migración SQLite → PostgreSQL

Migra los registros de Centro Operativo desde `centro_operativo.db` hacia una base PostgreSQL vacía. La base SQLite se abre explícitamente en modo de solo lectura y no se modifica.

## Requisitos

- Python 3.12.
- Dependencias de `requirements.txt` del proyecto.
- PostgreSQL accesible mediante `DATABASE_URL`.
- Destino vacío. Si alguna tabla ya contiene filas, la herramienta aborta sin importar datos.

## Uso recomendado con Docker

Ejecute la migración antes del primer inicio de la aplicación:

```powershell
docker compose --profile migration run --rm migrate
docker compose up -d app
```

La configuración monta `centro_operativo.db` como `/data/centro_operativo.db` con permiso de solo lectura. Las tablas incorporadas después de la primera versión (`work_schedules`, `toll_catalog` y las tablas `wfm_*`) son opcionales en fuentes históricas: si no existen, se migran como tablas vacías sin bloquear el traslado. Si existen, sus filas se trasladan y se incluyen en el resumen de recuentos.

## Uso directo

```powershell
python -m tools.sqlite_to_postgres.migrate centro_operativo.db --database-url "postgresql://usuario:clave@servidor/base"
```

Entradas: archivo SQLite y URL de una base PostgreSQL vacía. Salida: filas importadas conservando sus identificadores. Modifica únicamente la base PostgreSQL indicada; nunca modifica el archivo SQLite.

La herramienta valida `PRAGMA integrity_check` antes de leer el origen y muestra
los recuentos de todas las tablas, incluidas las opcionales modernas. Si alguna
tabla de destino ya contiene filas, aborta antes de importar.

## Prueba mínima

```powershell
python -m unittest tests.test_migration -v
```
