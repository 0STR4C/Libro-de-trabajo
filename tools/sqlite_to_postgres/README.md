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

La configuración monta `centro_operativo.db` como `/data/centro_operativo.db` con permiso de solo lectura. La tabla nueva `work_schedules` es opcional en fuentes históricas anteriores a Horarios: si no existe, se migra como una tabla vacía sin bloquear el traslado.

## Uso directo

```powershell
python -m tools.sqlite_to_postgres.migrate centro_operativo.db --database-url "postgresql://usuario:clave@servidor/base"
```

Entradas: archivo SQLite y URL de una base PostgreSQL vacía. Salida: filas importadas conservando sus identificadores. Modifica únicamente la base PostgreSQL indicada; nunca modifica el archivo SQLite.

## Prueba mínima

```powershell
python -m unittest tests.test_migration -v
```
