"""Reglas compartidas del circuito de traslados programados."""
from __future__ import annotations

from datetime import date, time
import re
import unicodedata


TRANSFER_TYPES = (
    "Traslado Largo",
    "Traslado Depósito",
    "Traslado Directo",
    "Mercosur",
)
TRANSFER_STATUSES = (
    "SIN_ASIGNAR",
    "ASIGNADO",
    "EN_CURSO",
    "FINALIZADO",
    "CANCELADO",
)
LEGACY_TRANSFER_STATUSES = {
    "PENDIENTE": "SIN_ASIGNAR",
    "CONFIRMADO": "ASIGNADO",
    "COMPLETADO": "FINALIZADO",
}
TRANSFER_TRANSITIONS = {
    "SIN_ASIGNAR": {"ASIGNADO", "CANCELADO"},
    "ASIGNADO": {"SIN_ASIGNAR", "EN_CURSO", "CANCELADO"},
    "EN_CURSO": {"ASIGNADO", "FINALIZADO", "CANCELADO"},
    "FINALIZADO": set(),
    "CANCELADO": set(),
}


def compact_text(value, *, name: str, minimum: int = 0, maximum: int) -> str:
    result = " ".join(str(value or "").split())
    if len(result) < minimum:
        raise ValueError(f"{name} es obligatorio")
    if len(result) > maximum:
        raise ValueError(f"{name} supera el máximo de {maximum} caracteres")
    return result


def optional_text(value, *, name: str, maximum: int) -> str | None:
    if value in (None, ""):
        return None
    result = compact_text(value, name=name, maximum=maximum)
    return result or None


def normalized_key(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.casefold().split())


def normalized_status(value) -> str:
    status = str(value or "SIN_ASIGNAR").strip().upper()
    return LEGACY_TRANSFER_STATUSES.get(status, status)


def clean_transfer(data: dict) -> dict:
    """Normaliza los campos editables y aplica el mismo contrato en ambos servidores."""
    transfer_type = compact_text(data.get("transfer_type"), name="El tipo de traslado", minimum=2, maximum=80)
    if transfer_type not in TRANSFER_TYPES:
        raise ValueError("El tipo de traslado no pertenece al catálogo permitido")
    try:
        scheduled_date = data.get("scheduled_date")
        scheduled_date = scheduled_date if isinstance(scheduled_date, date) else date.fromisoformat(str(scheduled_date))
    except (TypeError, ValueError):
        raise ValueError("La fecha programada no es válida") from None
    scheduled_time = data.get("scheduled_time")
    if scheduled_time in (None, ""):
        scheduled_time = None
    elif isinstance(scheduled_time, time):
        scheduled_time = scheduled_time.replace(second=0, microsecond=0)
    else:
        value = str(scheduled_time).strip()
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?", value):
            raise ValueError("La hora programada no es válida")
        scheduled_time = time.fromisoformat(value).replace(second=0, microsecond=0)
    origin = compact_text(data.get("origin"), name="El origen", minimum=2, maximum=500)
    destination = compact_text(data.get("destination"), name="El destino", minimum=2, maximum=500)
    if normalized_key(origin) == normalized_key(destination):
        raise ValueError("El origen y el destino deben ser diferentes")
    return {
        "task_number": compact_text(data.get("task_number"), name="El número de tarea", minimum=1, maximum=120),
        "transfer_type": transfer_type,
        "scheduled_date": scheduled_date,
        "scheduled_time": scheduled_time,
        "origin": origin,
        "destination": destination,
        "provider": optional_text(data.get("provider"), name="El prestador", maximum=200),
        "responsible": optional_text(data.get("responsible"), name="El responsable", maximum=120),
        "comments": optional_text(data.get("comments"), name="Los comentarios", maximum=4000),
        "allow_duplicate": bool(data.get("allow_duplicate", False)),
    }


def validate_transition(current: dict, data: dict) -> dict:
    """Valida una transición y devuelve sus campos operativos normalizados."""
    previous = normalized_status(current.get("status"))
    target = normalized_status(data.get("status"))
    if previous not in TRANSFER_STATUSES or target not in TRANSFER_STATUSES:
        raise ValueError("Estado de traslado inválido")
    if target == previous:
        raise ValueError("El traslado ya se encuentra en ese estado")
    if target not in TRANSFER_TRANSITIONS[previous]:
        raise ValueError(f"No se puede pasar de {previous} a {target}")
    provider = optional_text(data.get("provider", current.get("provider")), name="El prestador", maximum=200)
    responsible = optional_text(data.get("responsible", current.get("responsible")), name="El responsable", maximum=120)
    note = optional_text(data.get("note"), name="La observación", maximum=1000)
    if target in {"ASIGNADO", "EN_CURSO", "FINALIZADO"} and (not provider or not responsible):
        raise ValueError("Para asignar o avanzar el traslado se requieren prestador y responsable")
    if target == "FINALIZADO" and (not note or len(note) < 2):
        raise ValueError("Indique el resultado del traslado para finalizarlo")
    if target == "CANCELADO" and (not note or len(note) < 2):
        raise ValueError("Indique el motivo de la cancelación")
    return {
        "previous_status": previous,
        "status": target,
        "provider": provider,
        "responsible": responsible,
        "note": note,
    }
