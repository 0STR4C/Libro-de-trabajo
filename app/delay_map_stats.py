"""Agregación PostgreSQL para un futuro mapa de demoras."""

from __future__ import annotations

from datetime import datetime, timezone

from .delays import DELAY_REVIEW_DEADLINE_SQL, normalized_key, zone_matches
from .geography import ALL_DEPARTMENT, URUGUAY_ZONES


def _overlap(first: dict, second: dict) -> bool:
    """Un alcance general también coincide con las excepciones específicas."""
    services = (normalized_key(first["service"]), normalized_key(second["service"]))
    if services[0] != services[1] and normalized_key("TODAS") not in services:
        return False
    zones = (first["zone"], second["zone"])
    return (normalized_key(ALL_DEPARTMENT) in {normalized_key(zone) for zone in zones}
            or zone_matches(zones[0], zones[1]) or zone_matches(zones[1], zones[0]))


def map_delay_stats(database, as_of: datetime | None = None) -> dict:
    """Una consulta agrupada; nunca transfiere el historial de demoras al cliente."""
    instant = as_of or datetime.now(timezone.utc)
    grouped = database.execute(
        f"""SELECT upper(btrim(department)) AS department,
                  count(*)::integer AS active_count,
                  count(*) FILTER (WHERE {DELAY_REVIEW_DEADLINE_SQL} <= %s)::integer AS review_due_count,
                  jsonb_agg(DISTINCT jsonb_build_object(
                      'service', btrim(service), 'zone', btrim(zone))) AS affected,
                  jsonb_agg(jsonb_build_object(
                      'id', id,
                      'service', btrim(service),
                      'zone', btrim(zone),
                      'status', status,
                      'message', message,
                      'minutes', minutes,
                      'minutes_min', minutes_min,
                      'minutes_max', minutes_max,
                      'instruction_text', instruction_text,
                      'last_verified_at', last_verified_at,
                      'review_due_at', {DELAY_REVIEW_DEADLINE_SQL},
                      'needs_review', {DELAY_REVIEW_DEADLINE_SQL} <= %s
                  )) AS delays
           FROM delay_zones
           WHERE status = 'VIGENTE'
           GROUP BY upper(btrim(department))""",
        (instant, instant),
    ).fetchall()
    by_department = {row["department"]: row for row in grouped}

    def payload(row: dict, department: str) -> dict:
        affected = sorted(row["affected"] or [], key=lambda item: (item["service"].casefold(), item["zone"].casefold())) if row else []
        delays = sorted(row["delays"] or [], key=lambda item: (item["zone"].casefold(), item["service"].casefold(), item["id"])) if row else []
        for item in delays:
            item["overlap_ids"] = [other["id"] for other in delays
                                   if other["id"] != item["id"] and _overlap(item, other)]
            # El catálogo guarda minutos de arribo total; "Margen de" no define
            # si sus minutos se suman o reemplazan ese valor.
            item["minutes_meaning"] = "margin_unspecified" if item["message"] == "Margen de" else None
        active_count = int(row["active_count"]) if row else 0
        review_due_count = int(row["review_due_count"]) if row else 0
        return {
            "department": department,
            "active_count": active_count,
            "verified_count": active_count - review_due_count,
            "review_due_count": review_due_count,
            "services": sorted({item["service"] for item in affected}, key=str.casefold),
            "zones": sorted({item["zone"] for item in affected}, key=str.casefold),
            "affected": affected,
            "delays": delays,
        }

    return {
        "as_of": instant.isoformat(),
        "departments": [payload(by_department.get(name), name) for name in URUGUAY_ZONES],
        "unmapped": [payload(row, name) for name, row in sorted(by_department.items()) if name not in URUGUAY_ZONES],
    }
