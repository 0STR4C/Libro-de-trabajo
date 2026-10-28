"""Proyección de consulta del equipo: solo turnos publicados y datos compartibles."""

from datetime import date, timedelta

try:
    from .application import SCHEDULE_ROLES
    from .wfm import _published_schedules
except ImportError:
    from application import SCHEDULE_ROLES
    from wfm import _published_schedules


def public_schedule_row(row):
    """No expone notas, motivos, excepciones privadas ni metadatos de edición."""
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "display_name": row["display_name"],
        "role_name": row["role_name"],
        "schedule_date": row["schedule_date"],
        "source": row["source"],
        "segments": [
            {"start": item["start"], "end": item["end"]}
            for item in row.get("segments", [])
        ],
        "start_slot": row.get("start_slot"),
        "end_slot": row.get("end_slot"),
        "break_slot": row.get("break_slot"),
        "break_duration": row.get("break_duration", 0),
        "overtime_slots": row.get("overtime_slots", 0),
        "published_day": bool(row.get("published_day")),
    }


def team_week_snapshot(query, week, postgres=False):
    """Devuelve siete días completos y turnos que continúan desde el domingo anterior."""
    requested = date.fromisoformat(str(week))
    first = requested - timedelta(days=requested.weekday())
    previous = first - timedelta(days=1)
    weekly = _published_schedules(
        query, {"week": first.isoformat(), "include_free_days": "1"}, postgres
    )
    carry_in = _published_schedules(
        query, {"date_from": previous.isoformat(), "date_to": previous.isoformat()}, postgres
    )
    records = [
        public_schedule_row(row)
        for row in [*weekly, *(row for row in carry_in if (row.get("end_slot") or 0) > 48)]
        if not row.get("draft_day")
    ]
    roles = ",".join("?" for _ in SCHEDULE_ROLES)
    roster = query(
        "SELECT u.id,u.display_name,r.name role_name FROM users u "
        f"JOIN roles r ON r.id=u.role_id WHERE u.active AND r.name IN ({roles}) "
        "ORDER BY u.display_name,u.id",
        SCHEDULE_ROLES,
    ).fetchall()
    people = {row["id"]: {
        "id": row["id"], "display_name": row["display_name"],
        "role_name": row["role_name"],
    } for row in roster}
    for row in records:
        people.setdefault(row["user_id"], {
            "id": row["user_id"], "display_name": row["display_name"],
            "role_name": row["role_name"],
        })
    return {"week": first.isoformat(), "people": list(people.values()), "rows": records}
