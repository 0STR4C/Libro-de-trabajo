"""Puebla demoras sintéticas para verificar la interfaz operativa local."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.delays import DELAY_SERVICES, clean_delay
from app.geography import ALL_DEPARTMENT, URUGUAY_ZONES


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEED_PREFIX = "Prueba demoras [seed-v1:"
SEED_COUNT = 72
INSERT_FIELDS = (
    "service", "department", "zone", "zone_id", "message", "minutes", "status",
    "agent", "created_at", "normalized_at", "normalized_by", "resolution_note",
    "last_verified_at", "expires_at", "next_review_at", "duration_minutes", "last_verified_by",
)


def build_seed_rows(current_time: datetime | None = None) -> list[dict]:
    """36 vigentes, 20 a revisar y 16 normalizadas, sin azar ni zonas libres."""
    now = (current_time or datetime.now(timezone.utc)).astimezone(timezone.utc)
    departments = tuple(URUGUAY_ZONES)
    result = []
    for index in range(SEED_COUNT):
        department = departments[index % len(departments)]
        zones = (ALL_DEPARTMENT, *URUGUAY_ZONES[department])
        zone = zones[((index // len(departments)) + (index % 4)) % len(zones)]
        service = DELAY_SERVICES[index % len(DELAY_SERVICES)]
        message = ("Margen de", "A confirmar", "No confirmar tiempos")[index % 3]
        minutes = (30, 45, 60, 90)[index % 4] if message == "Margen de" else None
        duration = (30, 60, 120, 240)[index % 4] if index >= 36 else None
        clean_delay({
            "service": service, "department": department, "zone": zone,
            "message": message, "minutes": minutes, "status": "VIGENTE",
            "duration_minutes": duration, "catalog_zone": True,
        })
        created = now - timedelta(hours=index + 4)
        normalized = None
        if index < 36:
            # La duración queda sin definir: esta ventana amplia mantiene
            # casos vigentes disponibles para la revisión visual de mañana.
            verified = now - timedelta(minutes=15 + index)
            deadline = now + timedelta(hours=48 + index % 8)
            status = "VIGENTE"
        elif index < 56:
            deadline = now - timedelta(minutes=15 + (index - 36) * 12)
            verified = deadline - timedelta(minutes=duration)
            status = "VIGENTE"
        else:
            normalized = now - timedelta(hours=index - 54)
            deadline = normalized - timedelta(hours=1)
            verified = deadline - timedelta(minutes=duration)
            status = "NORMALIZADO"
        result.append({
            "service": service, "department": department, "zone": zone,
            "message": message, "minutes": minutes, "status": status,
            "agent": f"{SEED_PREFIX}{index + 1:03d}]",
            "created_at": created, "normalized_at": normalized,
            "normalized_by": "Prueba visual" if normalized else None,
            "resolution_note": "Servicio normalizado para prueba visual" if normalized else None,
            "last_verified_at": verified, "expires_at": deadline,
            "next_review_at": deadline, "duration_minutes": duration,
            "last_verified_by": "Prueba visual",
        })
    return result


def seed_postgres(items: list[dict], apply: bool) -> int:
    from app.postgres_server import connect, ensure_operational_zone

    if not apply:
        return 0
    inserted = 0
    with connect() as database:
        existing = {row["agent"] for row in database.execute(
            "SELECT agent FROM delay_zones WHERE agent LIKE %s", (f"{SEED_PREFIX}%",)
        ).fetchall()}
        for item in items:
            if item["agent"] in existing:
                continue
            zone_id = ensure_operational_zone(database, item["department"], item["zone"])
            values = {**item, "zone_id": zone_id}
            placeholders = ",".join(["%s"] * len(INSERT_FIELDS))
            delay_id = database.execute(
                f"INSERT INTO delay_zones ({','.join(INSERT_FIELDS)}) VALUES ({placeholders}) RETURNING id",
                tuple(values[field] for field in INSERT_FIELDS),
            ).fetchone()["id"]
            database.execute(
                "INSERT INTO delay_events(delay_id,event_type,actor,note,review_due_at,created_at) VALUES(%s,%s,%s,%s,%s,%s)",
                (delay_id, "CREADO", item["agent"], "Registro sintético para prueba visual", item["next_review_at"], item["created_at"]),
            )
            if item["normalized_at"]:
                database.execute(
                    "INSERT INTO delay_events(delay_id,event_type,actor,note,created_at) VALUES(%s,%s,%s,%s,%s)",
                    (delay_id, "NORMALIZADO", "Prueba visual", item["resolution_note"], item["normalized_at"]),
                )
            inserted += 1
    return inserted


def seed_sqlite(items: list[dict], path: Path, apply: bool) -> int:
    from app import local_server

    destination = path.resolve()
    if not destination.is_relative_to(PROJECT_ROOT):
        raise ValueError("La base SQLite debe estar dentro del proyecto activo")
    if not apply:
        return 0
    local_server.DB_PATH = destination
    local_server.initialize()
    inserted = 0
    with sqlite3.connect(destination) as database:
        database.row_factory = sqlite3.Row
        existing = {row["agent"] for row in database.execute(
            "SELECT agent FROM delay_zones WHERE agent LIKE ?", (f"{SEED_PREFIX}%",)
        ).fetchall()}
        for item in items:
            if item["agent"] in existing:
                continue
            zone_id = local_server.ensure_operational_zone(database, item["department"], item["zone"])
            values = {**item, "zone_id": zone_id}
            placeholders = ",".join(["?"] * len(INSERT_FIELDS))
            cursor = database.execute(
                f"INSERT INTO delay_zones ({','.join(INSERT_FIELDS)}) VALUES ({placeholders})",
                tuple(value.isoformat() if isinstance(value, datetime) else value for value in (values[field] for field in INSERT_FIELDS)),
            )
            database.execute(
                "INSERT INTO delay_events(delay_id,event_type,actor,note,review_due_at,created_at) VALUES(?,?,?,?,?,?)",
                (cursor.lastrowid, "CREADO", item["agent"], "Registro sintético para prueba visual", item["next_review_at"].isoformat(), item["created_at"].isoformat()),
            )
            if item["normalized_at"]:
                database.execute(
                    "INSERT INTO delay_events(delay_id,event_type,actor,note,created_at) VALUES(?,?,?,?,?)",
                    (cursor.lastrowid, "NORMALIZADO", "Prueba visual", item["resolution_note"], item["normalized_at"].isoformat()),
                )
            inserted += 1
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepara 72 demoras sintéticas para pruebas visuales locales")
    parser.add_argument("--backend", choices=("postgres", "sqlite"), default="postgres")
    parser.add_argument("--sqlite-path", type=Path, help="Ruta SQLite dentro del proyecto, obligatoria para ese backend")
    parser.add_argument("--apply", action="store_true", help="Inserta los registros; sin este flag solo muestra el plan")
    args = parser.parse_args()
    if args.backend == "sqlite" and not args.sqlite_path:
        parser.error("--sqlite-path es obligatorio con --backend sqlite")
    items = build_seed_rows()
    if args.backend == "postgres":
        inserted = seed_postgres(items, args.apply)
    else:
        inserted = seed_sqlite(items, args.sqlite_path, args.apply)
    counts = {"vigentes": 36, "requieren_revision": 20, "normalizadas": 16}
    print(f"Plan: {len(items)} demoras sintéticas {counts}. Nuevas filas insertadas: {inserted}.")
    if not args.apply:
        print("Vista previa: la base no fue modificada. Usá --apply para insertar.")


if __name__ == "__main__":
    main()
