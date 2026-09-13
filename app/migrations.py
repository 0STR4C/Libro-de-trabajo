"""Registro verificable para migraciones incrementales."""

from __future__ import annotations

import hashlib
from typing import Mapping


def migration_checksum(definition: str) -> str:
    return hashlib.sha256(definition.encode("utf-8")).hexdigest()


def ensure_sqlite_migration_registry(database) -> None:
    columns = {row[1] for row in database.execute("PRAGMA table_info(schema_migrations)").fetchall()}
    if "checksum" not in columns:
        database.execute("ALTER TABLE schema_migrations ADD COLUMN checksum TEXT")


def reconcile_migration_checksums(database, contracts: Mapping[str, str], placeholder: str = "?") -> None:
    """Completa checksums históricos y rechaza definiciones ya aplicadas que cambiaron."""
    for key, definition in contracts.items():
        record = database.execute(
            f"SELECT checksum FROM schema_migrations WHERE key={placeholder}",
            (key,),
        ).fetchone()
        if not record:
            continue
        recorded = record["checksum"] if hasattr(record, "keys") else record[0]
        expected = migration_checksum(definition)
        if recorded and recorded != expected:
            raise RuntimeError(f"La migración aplicada {key} no coincide con su definición versionada.")
        if not recorded:
            database.execute(
                f"UPDATE schema_migrations SET checksum={placeholder} WHERE key={placeholder}",
                (expected, key),
            )
