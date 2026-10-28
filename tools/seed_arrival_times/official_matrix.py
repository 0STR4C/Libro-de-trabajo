"""Publica la matriz operativa aprobada sin convertir celdas sin valor numérico.

Ejecutar desde la raíz: python -m tools.seed_arrival_times.official_matrix [--apply]
Antes de --apply, conservar un respaldo de arrival_times de la instalación destino.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from app.arrival_times import clean_arrival_time
from app.delays import STANDARD_SERVICES
from app.geography import ALL_DEPARTMENT, URUGUAY_ZONES

SOURCE = "official-matrix-20261027"
ACTOR = "Matriz operativa oficial"

# Localidades legibles en la matriz recibida. No son un polígono ni se extienden
# automáticamente a localidades que la referencia no menciona.
CANELONES_INTERIOR = (
    "Canelones", "Pando", "Barros Blancos", "Empalme Olmos", "Las Piedras",
    "La Paz", "Progreso", "Joaquín Suárez", "Neptunia", "Pinamar", "Salinas",
    "Marindia", "Fortín de Santa Rosa", "Villa Argentina", "Atlántida",
    "Las Toscas", "Parque del Plata", "La Floresta", "Costa Azul",
    "Bello Horizonte", "San Luis", "La Tuna", "Santa Lucía del Este",
    "Cuchilla Alta", "Santa Ana", "Jaureguiberry", "San Jacinto",
)
MONTEVIDEO_FRANJAS = (
    ("Centro", "Parque Rodó", "Pocitos", "Punta Carretas", "Tres Cruces", "Mercado Modelo", "Buceo", "Punta Gorda"),
    ("Maroñas", "Malvín"),
    ("Nuevo París", "Cerro", "Colón", "Casavalle", "Peñarol", "La Teja", "Manga"),
)
INTERIOR_CABECERAS = {
    "ARTIGAS": ("Artigas",),
    "CERRO LARGO": ("Melo",),
    "COLONIA": ("Colonia del Sacramento", "Juan Lacaze"),
    "DURAZNO": ("Durazno",),
    "FLORIDA": ("Florida",),
    "LAVALLEJA": ("Minas",),
    "RÍO NEGRO": ("Young", "Fray Bentos"),
    "RIVERA": ("Rivera",),
    "ROCHA": ("Rocha", "Chuy"),
    "PAYSANDÚ": ("Paysandú",),
    "SAN JOSÉ": ("San José de Mayo", "Libertad"),
    "SALTO": ("Salto",),
    "SORIANO": ("Mercedes",),
    "TACUAREMBÓ": ("Tacuarembó",),
    "TREINTA Y TRES": ("Treinta y Tres",),
}


def build_rows() -> list[dict]:
    rows = []

    def add(scope: str, service: str, department: str, zones: tuple[str, ...] | None,
            kind: str, minimum: int | None = None, maximum: int | None = None):
        item = clean_arrival_time({
            "service": service, "department": department,
            "zone": ", ".join(zones) if zones else ALL_DEPARTMENT,
            "indication_type": kind, "minutes_min": minimum, "minutes_max": maximum,
            "is_active": True,
        })
        if len(item["zone"]) > 500:
            raise ValueError(f"Agrupación demasiado larga: {scope}")
        rows.append({**item, "source_key": f"{SOURCE}:{department}:{scope}:{service}"})

    for number, zones in enumerate(MONTEVIDEO_FRANJAS, 1):
        add(f"montevideo-franja-{number}", "ML", "MONTEVIDEO", zones, "MAXIMUM", maximum=45 if number == 3 else 30)
        add(f"montevideo-franja-{number}", "GRÚA", "MONTEVIDEO", zones, "MAXIMUM", maximum=45)
    add("ciudad-costa", "ML", "CANELONES", ("Ciudad de la Costa",), "MAXIMUM", maximum=45)
    add("ciudad-costa", "GRÚA", "CANELONES", ("Ciudad de la Costa",), "MAXIMUM", maximum=45)
    add("municipios-interbalnearia-solis", "ML", "CANELONES", CANELONES_INTERIOR, "MAXIMUM", maximum=45)
    add("municipios-interbalnearia-solis", "GRÚA", "CANELONES", CANELONES_INTERIOR, "MAXIMUM", maximum=60)
    add("maldonado-piriapolis", "ML", "MALDONADO", ("Maldonado", "Piriápolis"), "INTERVAL", 30, 45)
    add("maldonado-piriapolis", "GRÚA", "MALDONADO", ("Maldonado", "Piriápolis"), "MAXIMUM", maximum=60)
    for department, zones in INTERIOR_CABECERAS.items():
        for service in ("ML", "GRÚA"):
            add("cabeceras", service, department, zones, "MAXIMUM", maximum=60)
    # Montevideo es la única excepción del respaldo: las referencias de
    # Siniestros metropolitanos no se deducen de celdas vacías de la planilla.
    for department in URUGUAY_ZONES:
        if department != "MONTEVIDEO":
            for service in STANDARD_SERVICES:
                add("interior-no-listado", service, department, None, "TO_CONFIRM")
    return rows


def apply_rows(database, rows: list[dict], backup_to: Path | None = None) -> dict:
    database.execute("SELECT pg_advisory_xact_lock(%s)", (20261027,))
    source_keys = [row["source_key"] for row in rows]
    if len(source_keys) != len(set(source_keys)):
        raise ValueError("Claves de matriz duplicadas")
    synthetic = database.execute("SELECT * FROM arrival_times WHERE seed_key IS NOT NULL FOR UPDATE").fetchall()
    if backup_to is not None:
        if backup_to.exists():
            raise FileExistsError(f"El respaldo ya existe: {backup_to}")
        backup_to.parent.mkdir(parents=True, exist_ok=True)
        backup_to.write_text(json.dumps([dict(item) for item in synthetic], default=str, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in rows:
        existing = database.execute("SELECT * FROM arrival_times WHERE source_key=%s FOR UPDATE", (item["source_key"],)).fetchone()
        if existing:
            if any(existing[name] != item[name] for name in (
                "service", "department", "zone", "zone_members", "indication_type",
                "base_estimated_minutes", "minutes_min", "minutes_max", "is_active",
            )):
                raise ValueError("Una fila de la matriz cambió manualmente; operación cancelada")
            continue
        conflict = database.execute(
            """SELECT id FROM arrival_times WHERE seed_key IS NULL AND is_active=TRUE
               AND service=%s AND department=%s AND
               (zone=%s OR (cardinality(%s::text[])>0 AND zone_members && %s::text[])) LIMIT 1""",
            (item["service"], item["department"], item["zone"], item["zone_members"], item["zone_members"]),
        ).fetchone()
        if conflict:
            raise ValueError("Ya existe una referencia operativa superpuesta; operación cancelada")
    removed = database.execute("DELETE FROM arrival_times WHERE seed_key IS NOT NULL RETURNING id").fetchall()
    if len(removed) != len(synthetic):
        raise RuntimeError("Cambió el conjunto sintético; operación cancelada")
    from app.postgres_server import audit

    inserted = 0
    stamp = datetime.now(timezone.utc)
    for item in rows:
        if database.execute("SELECT 1 FROM arrival_times WHERE source_key=%s", (item["source_key"],)).fetchone():
            continue
        created = database.execute(
            """INSERT INTO arrival_times(service,department,zone,zone_members,indication_type,
                   base_estimated_minutes,minutes_min,minutes_max,is_active,created_by,updated_by,
                   created_at,updated_at,source_key)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s,%s,%s,%s,%s) RETURNING id""",
            (item["service"], item["department"], item["zone"], item["zone_members"],
             item["indication_type"], item["base_estimated_minutes"], item["minutes_min"],
             item["minutes_max"], ACTOR, ACTOR, stamp, stamp, item["source_key"]),
        ).fetchone()
        audit(database, "arrival_time", created["id"], "IMPORTADO", ACTOR,
              item["source_key"], after={**item, "id": created["id"]}, source="official_matrix")
        inserted += 1
    return {"synthetic_removed": len(removed), "official_inserted": inserted, "official_total": len(rows)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Publica en PostgreSQL; por defecto solo muestra el plan")
    parser.add_argument("--backup-to", type=Path, help="Copia JSON de filas sintéticas antes de retirarlas")
    args = parser.parse_args()
    rows = build_rows()
    if not args.apply:
        print({"official_total": len(rows), "departments": len({row['department'] for row in rows}),
               "services": sorted({row['service'] for row in rows})})
        return
    from app.postgres_server import connect
    with connect() as database:
        result = apply_rows(database, rows, args.backup_to)
    print(result)


if __name__ == "__main__":
    main()
