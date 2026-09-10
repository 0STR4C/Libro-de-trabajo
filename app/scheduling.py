"""Reglas compartidas de consistencia para los horarios del equipo."""

from datetime import date, datetime, time, timedelta


def _field(record, name):
    """Lee filas dict, sqlite3.Row y objetos similares sin convertirlas."""
    return record[name]


def schedule_date_value(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def schedule_time_value(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        value = value.time()
    if isinstance(value, time):
        return value.replace(tzinfo=None)
    return datetime.strptime(str(value)[:5], "%H:%M").time()


def schedule_time_text(value):
    parsed = schedule_time_value(value)
    return parsed.strftime("%H:%M") if parsed else None


def schedule_interval(schedule_date, start_time, end_time):
    """Devuelve un intervalo real; si termina antes, se considera turno nocturno."""
    start = schedule_time_value(start_time)
    end = schedule_time_value(end_time)
    if start is None or end is None:
        return None
    day = schedule_date_value(schedule_date)
    start_at = datetime.combine(day, start)
    end_at = datetime.combine(day, end)
    if end_at <= start_at:
        end_at += timedelta(days=1)
    return start_at, end_at


def find_schedule_conflict(records, schedule_date, shift_name, start_time, end_time, exclude_id=None):
    """Detecta duplicados exactos y solapamientos, incluso después de medianoche."""
    day = schedule_date_value(schedule_date)
    start_text = schedule_time_text(start_time)
    end_text = schedule_time_text(end_time)
    candidate_interval = schedule_interval(day, start_time, end_time)
    normalized_shift = str(shift_name or "").strip().casefold()

    for record in records:
        if exclude_id is not None and int(_field(record, "id")) == int(exclude_id):
            continue
        record_day = schedule_date_value(_field(record, "schedule_date"))
        record_start = _field(record, "start_time")
        record_end = _field(record, "end_time")
        if (
            record_day == day
            and str(_field(record, "shift_name") or "").strip().casefold() == normalized_shift
            and schedule_time_text(record_start) == start_text
            and schedule_time_text(record_end) == end_text
        ):
            return "duplicate", record

        existing_interval = schedule_interval(record_day, record_start, record_end)
        if candidate_interval and existing_interval:
            if candidate_interval[0] < existing_interval[1] and existing_interval[0] < candidate_interval[1]:
                return "overlap", record
    return None


def schedule_conflict_message(conflict):
    kind, record = conflict
    if kind == "duplicate":
        return "Ya existe ese mismo horario para la persona y la fecha seleccionadas."
    day = schedule_date_value(_field(record, "schedule_date")).strftime("%d/%m/%Y")
    start = schedule_time_text(_field(record, "start_time")) or "sin hora"
    end = schedule_time_text(_field(record, "end_time")) or "sin hora"
    shift = str(_field(record, "shift_name") or "otro turno")
    return f"El horario se superpone con {shift} del {day} ({start}–{end})."
