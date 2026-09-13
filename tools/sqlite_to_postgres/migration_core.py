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
    "transfer_events",
    "work_schedules",
    "quotes",
    "toll_catalog",
    "audit_events",
    "wfm_revisions",
    "wfm_published_plans",
    "wfm_published_shifts",
    "wfm_weekly_requirements",
    "wfm_settings",
    "wfm_requests",
)
OPTIONAL_TABLES = {
    "transfer_events",
    "work_schedules",
    "toll_catalog",
    "wfm_revisions",
    "wfm_published_plans",
    "wfm_published_shifts",
    "wfm_weekly_requirements",
    "wfm_settings",
    "wfm_requests",
}
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
            if table == "scheduled_transfers":
                if "updated_at" not in columns:
                    columns.append("updated_at")
                    for record in records:record["updated_at"] = record.get("created_at")
                legacy = {"PENDIENTE": "SIN_ASIGNAR", "CONFIRMADO": "ASIGNADO", "COMPLETADO": "FINALIZADO"}
                for record in records:record["status"] = legacy.get(record.get("status"), record.get("status"))
            for record in records:
                for column in BOOLEAN_COLUMNS.get(table, set()):
                    record[column] = bool(record[column])
            result[table] = {"columns": columns, "rows": records}
        return result
    finally:
        database.close()


def counts(dataset):
    return {table: len(dataset[table]["rows"]) for table in TABLES}
