"""Lectura y validación segura de una base SQLite de Centro Operativo."""
import sqlite3
from pathlib import Path

TABLES = (
    "roles",
    "role_permissions",
    "users",
    "app_settings",
    "schema_migrations",
    "quote_rules",
    "arrival_standards",
    "notices",
    "delay_zones",
    "scheduled_transfers",
    "work_schedules",
    "quotes",
    "audit_events",
)
OPTIONAL_TABLES = {"work_schedules"}
BOOLEAN_COLUMNS = {"users": {"active"}, "quotes": {"uninsured", "special", "gavilan"}}


def load_sqlite(source_path):
    """Carga tablas permitidas sin abrir la base con permisos de escritura."""
    source = Path(source_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    database = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    database.row_factory = sqlite3.Row
    try:
        integrity = database.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise sqlite3.DatabaseError(f"La base de origen no es íntegra: {integrity}")
        available = {row[0] for row in database.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = [table for table in TABLES if table not in available and table not in OPTIONAL_TABLES]
        if missing:
            raise sqlite3.DatabaseError("Faltan tablas requeridas: " + ", ".join(missing))
        result = {}
        for table in TABLES:
            if table not in available:
                result[table] = {"columns": [], "rows": []}
                continue
            columns = [row[1] for row in database.execute(f"PRAGMA table_info({table})")]
            records = [dict(row) for row in database.execute(f"SELECT * FROM {table}")]
            for record in records:
                for column in BOOLEAN_COLUMNS.get(table, set()):
                    record[column] = bool(record[column])
            result[table] = {"columns": columns, "rows": records}
        return result
    finally:
        database.close()


def counts(dataset):
    return {table: len(dataset[table]["rows"]) for table in TABLES}
