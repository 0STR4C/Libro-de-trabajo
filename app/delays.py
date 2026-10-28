"""Reglas compartidas para demoras y referencias habituales de arribo."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import unicodedata


DEPARTMENTS = (
    "ARTIGAS", "CANELONES", "CERRO LARGO", "COLONIA", "DURAZNO", "FLORES",
    "FLORIDA", "LAVALLEJA", "MALDONADO", "MONTEVIDEO", "PAYSANDÚ",
    "RÍO NEGRO", "RIVERA", "ROCHA", "SALTO", "SAN JOSÉ", "SORIANO",
    "TACUAREMBÓ", "TREINTA Y TRES",
)
DELAY_SERVICES = ("TODAS", "GRÚA", "ML", "SINIESTROS")
STANDARD_SERVICES = ("GRÚA", "ML", "SINIESTROS")
STANDARD_DEPARTMENTS = DEPARTMENTS + ("INTERIOR",)
DELAY_MESSAGES = ("No confirmar tiempos", "A confirmar", "Margen de", "Máximo de", "Intervalo estimado", "Otra indicación", "No generar servicio")
STANDARD_STATUSES = ("CONFIRMADO", "PROVISIONAL", "SIN_REFERENCIA")
DEFAULT_DELAY_REVIEW_MINUTES = 120
DELAY_REVIEW_DEADLINE_SQL = (
    "COALESCE(next_review_at,expires_at,"
    f"last_verified_at + interval '{DEFAULT_DELAY_REVIEW_MINUTES} minutes',"
    f"created_at + interval '{DEFAULT_DELAY_REVIEW_MINUTES} minutes')"
)
try:
    from .geography import ALL_DEPARTMENT, URUGUAY_ZONES
except ImportError:
    from geography import ALL_DEPARTMENT, URUGUAY_ZONES


def normalized_key(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(text.casefold().split())


def _canonical(value, choices, label):
    key = normalized_key(value)
    match = next((choice for choice in choices if normalized_key(choice) == key), None)
    if match is None:
        raise ValueError(f"{label} inválido")
    return match


def clean_delay(data: dict) -> dict:
    result = dict(data)
    result["service"] = _canonical(result.get("service"), DELAY_SERVICES, "Prestación")
    result["department"] = _canonical(result.get("department"), DEPARTMENTS, "Departamento")
    result["message"] = _canonical(result.get("message"), DELAY_MESSAGES, "Mensaje al cliente")
    result["zone"] = " ".join(str(result.get("zone") or "").split())
    if len(result["zone"]) < 2:
        raise ValueError("La zona debe tener al menos dos caracteres")
    # Los registros históricos pueden tener zonas libres; las altas nuevas que
    # envían el catálogo se validan contra el departamento seleccionado.
    if result.get("catalog_zone"):
        choices = (ALL_DEPARTMENT, *URUGUAY_ZONES[result["department"]])
        zones = [_canonical(zone, choices, "Zona") for zone in split_zones(result["zone"])]
        if ALL_DEPARTMENT in zones and len(zones) > 1:
            raise ValueError("Todo el departamento no puede combinarse con zonas concretas")
        result["zone"] = ", ".join(zones)
    if result.get("status", "VIGENTE") != "VIGENTE":
        raise ValueError("Una demora nueva debe comenzar vigente")
    minutes = result.get("minutes")
    minimum, maximum = result.get("minutes_min"), result.get("minutes_max")
    instruction = " ".join(str(result.get("instruction_text") or "").split()) or None
    if result["message"] in {"Margen de", "Máximo de"}:
        if type(minutes) is not int or not 1 <= minutes <= 1440:
            label = "margen" if result["message"] == "Margen de" else "máximo"
            raise ValueError(f"Ingresá un {label} entre 1 y 1.440 minutos")
    elif minutes is not None:
        raise ValueError("Los minutos solo corresponden a un margen o máximo")
    if result["message"] == "Intervalo estimado":
        if any(type(value) is not int or not 1 <= value <= 1440 for value in (minimum, maximum)) or minimum > maximum:
            raise ValueError("Ingresá un intervalo válido entre 1 y 1.440 minutos")
    elif minimum is not None or maximum is not None:
        raise ValueError("Los extremos solo corresponden a un intervalo estimado")
    if result["message"] == "Otra indicación":
        if not instruction or not 2 <= len(instruction) <= 500:
            raise ValueError("Escribí una indicación operativa de 2 a 500 caracteres")
    elif instruction:
        raise ValueError("El texto libre solo corresponde a otra indicación")
    result["instruction_text"] = instruction
    result["status"] = "VIGENTE"
    duration = result.get("duration_minutes")
    if duration is not None and (type(duration) is not int or duration not in {30, 60, 120, 240}):
        raise ValueError("Elegí una duración de 30 minutos, 1, 2 o 4 horas, o sin definir")
    result["duration_minutes"] = duration
    review_minutes = result.get("review_minutes", DEFAULT_DELAY_REVIEW_MINUTES)
    if duration is not None:
        review_minutes = duration
    if isinstance(review_minutes, str) and review_minutes.isdigit():
        review_minutes = int(review_minutes)
    if type(review_minutes) is not int or not 15 <= review_minutes <= 1440:
        raise ValueError("La próxima revisión debe estar entre 15 minutos y 24 horas")
    result["review_minutes"] = review_minutes
    return result


def clean_standard(data: dict) -> dict:
    result = dict(data)
    result["department"] = _canonical(result.get("department"), STANDARD_DEPARTMENTS, "Departamento")
    result["service"] = _canonical(result.get("service"), STANDARD_SERVICES, "Prestación")
    result["status"] = _canonical(result.get("status"), STANDARD_STATUSES, "Estado de referencia")
    result["zone"] = " ".join(str(result.get("zone") or "").split())
    result["note"] = " ".join(str(result.get("note") or "").split()) or None
    result["source"] = " ".join(str(result.get("source") or "").split()) or None
    result["owner"] = " ".join(str(result.get("owner") or "Supervisión").split())
    interval = result.get("review_interval_days", 90)
    if isinstance(interval, str) and interval.isdigit():
        interval = int(interval)
    if type(interval) is not int or not 1 <= interval <= 365:
        raise ValueError("La frecuencia de revisión debe estar entre 1 y 365 días")
    result["review_interval_days"] = interval
    if len(result["owner"]) < 2:
        raise ValueError("Indique un responsable de revisión")
    if len(result["zone"]) < 2:
        raise ValueError("La zona debe tener al menos dos caracteres")
    minimum, maximum = result.get("minutes_min"), result.get("minutes_max")
    result["minutes_min"] = minimum
    result["minutes_max"] = maximum
    for value in (minimum, maximum):
        if value is not None and (type(value) is not int or not 1 <= value <= 1440):
            raise ValueError("Los tiempos deben estar entre 1 y 1.440 minutos")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError("El tiempo mínimo no puede superar el máximo")
    if result["status"] == "CONFIRMADO" and minimum is None and maximum is None:
        raise ValueError("Una referencia confirmada debe informar un tiempo")
    if result["status"] == "CONFIRMADO" and not result["source"]:
        raise ValueError("Una referencia confirmada debe indicar su fuente")
    if result["status"] == "SIN_REFERENCIA":
        if minimum is not None or maximum is not None:
            raise ValueError("Una zona sin referencia no puede informar minutos")
        result["note"] = result["note"] or "A confirmar"
    effective = result.get("effective_from")
    review_due = result.get("review_due_at")
    if isinstance(effective, str):
        effective = date.fromisoformat(effective)
        result["effective_from"] = effective
    if isinstance(review_due, str):
        review_due = date.fromisoformat(review_due)
        result["review_due_at"] = review_due
    if not review_due:
        review_due = (effective or date.today()) + timedelta(days=interval)
    result["effective_from"] = effective
    result["review_due_at"] = review_due
    if effective and review_due and review_due < effective:
        raise ValueError("La próxima revisión no puede ser anterior a la vigencia")
    return result


def zone_matches(candidate, requested) -> bool:
    """Coincidencia conservadora para zonas históricas todavía guardadas como texto."""
    requested_key = normalized_key(requested)
    if not requested_key:
        return True
    candidate_key = normalized_key(candidate)
    if candidate_key == normalized_key(ALL_DEPARTMENT):
        return True
    parts = {" ".join(part.split()) for part in candidate_key.split(",") if part.strip()}
    return requested_key == candidate_key or requested_key in parts


def split_zones(value) -> list[str]:
    result=[];seen=set()
    for part in str(value or "").split(","):
        name=" ".join(part.split())
        key=normalized_key(name)
        if key and key not in seen:
            seen.add(key);result.append(name)
    return result


def _utc_datetime(value):
    if value is None or value == "":
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def delay_review_deadline(item: dict):
    explicit = _utc_datetime(item.get("next_review_at") or item.get("expires_at"))
    if explicit:
        return explicit
    verified = _utc_datetime(item.get("last_verified_at") or item.get("created_at"))
    return verified + timedelta(minutes=DEFAULT_DELAY_REVIEW_MINUTES) if verified else None


def enrich_delay(item: dict, current_time=None) -> dict:
    result = dict(item)
    deadline = delay_review_deadline(result)
    current = _utc_datetime(current_time) or datetime.now(timezone.utc)
    needs_review = result.get("status") == "VIGENTE" and bool(deadline and deadline <= current)
    result["review_due_at"] = deadline.isoformat() if deadline else None
    result["next_review_at"] = deadline.isoformat() if deadline else None
    result["needs_review"] = needs_review
    result["is_current"] = result.get("status") == "VIGENTE" and not needs_review
    result["expires_in_minutes"] = max(0, int((deadline-current).total_seconds()//60)) if deadline and result["is_current"] else 0
    result["expiring_soon"] = result["is_current"] and result["expires_in_minutes"] <= 30
    return result


def standard_availability(item: dict, today=None) -> str:
    current_day = today or date.today()
    effective = item.get("effective_from")
    due = item.get("review_due_at")
    if isinstance(effective, str) and effective:
        effective = date.fromisoformat(effective[:10])
    if isinstance(due, str) and due:
        due = date.fromisoformat(due[:10])
    if not item.get("active", True):
        return "INACTIVE"
    if effective and effective > current_day:
        return "FUTURE"
    if due and due < current_day:
        return "REVIEW_DUE"
    if item.get("status") == "SIN_REFERENCIA":
        return "NO_REFERENCE"
    if item.get("status") != "CONFIRMADO":
        return "PROVISIONAL"
    return "CURRENT"
