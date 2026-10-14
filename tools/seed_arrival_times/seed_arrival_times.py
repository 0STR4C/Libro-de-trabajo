"""Carga referencias sintéticas y repetibles de tiempos base de arribo."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from app.arrival_times import clean_arrival_time
from app.delays import STANDARD_SERVICES
from app.geography import ALL_DEPARTMENT, URUGUAY_ZONES


SEED_COUNT = 40
SEED_PREFIX = "arrival-time-seed-v1-"


def build_seed_rows() -> list[dict]:
    departments = tuple(URUGUAY_ZONES)
    rows = []
    for index in range(SEED_COUNT):
        department = departments[index % len(departments)]
        zone = ALL_DEPARTMENT if index < 19 else URUGUAY_ZONES[department][(index // 19 - 1) % len(URUGUAY_ZONES[department])]
        service = STANDARD_SERVICES[(index + index // 19) % len(STANDARD_SERVICES)]
        # Tiempo operativo sintético: capital/área metropolitana más breve,
        # interior y grúa con algo más de margen.
        metropolitan = department in {"MONTEVIDEO", "CANELONES", "MALDONADO"}
        minutes = (30 if metropolitan else 45) + (15 if service == "GRÚA" else 0) + (15 if index >= 19 else 0)
        values = clean_arrival_time({
            "service": service,
            "department": department,
            "zone": zone,
            "base_estimated_minutes": minutes,
            "is_active": index % 9 != 0,
        })
        rows.append({**values, "seed_key": f"{SEED_PREFIX}{index + 1:03d}"})
    return rows


def seed_postgres(database, rows: list[dict], apply: bool = False) -> int:
    if not apply:
        return 0
    stamp = datetime.now(timezone.utc)
    inserted = 0
    for row in rows:
        created = database.execute(
            """INSERT INTO arrival_times(service,department,zone,base_estimated_minutes,
                   is_active,created_by,updated_by,created_at,updated_at,seed_key)
               VALUES(%s,%s,%s,%s,%s,'Seed de pruebas','Seed de pruebas',%s,%s,%s)
               ON CONFLICT DO NOTHING RETURNING id""",
            (row["service"], row["department"], row["zone"], row["base_estimated_minutes"],
             row["is_active"], stamp, stamp, row["seed_key"]),
        ).fetchone()
        if created:
            inserted += 1
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepara 40 tiempos de arribo sintéticos")
    parser.add_argument("--apply", action="store_true", help="Inserta en PostgreSQL; sin este flag solo muestra el plan")
    args = parser.parse_args()
    rows = build_seed_rows()
    inserted = 0
    if args.apply:
        from app.postgres_server import connect

        with connect() as database:
            inserted = seed_postgres(database, rows, apply=True)
    print(f"Plan: {len(rows)} tiempos de arribo; {sum(row['is_active'] for row in rows)} activos, "
          f"{sum(not row['is_active'] for row in rows)} inactivos. Nuevas filas: {inserted}.")
    if not args.apply:
        print("Vista previa: no se modificó la base. Usá --apply para insertar.")


if __name__ == "__main__":
    main()
