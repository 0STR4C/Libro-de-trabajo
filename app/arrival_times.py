"""Validación del catálogo de tiempos base de arribo."""

from __future__ import annotations

from .delays import STANDARD_SERVICES, normalized_key
from .geography import ALL_DEPARTMENT, URUGUAY_ZONES


def _choice(value: str, choices, label: str) -> str:
    key = normalized_key(value)
    selected = next((item for item in choices if normalized_key(item) == key), None)
    if selected is None:
        raise ValueError(f"{label} inválido")
    return selected


def clean_arrival_location(service, department, zone) -> tuple[str, str, str]:
    """Canoniza la clave del catálogo, incluida la zona departamental."""
    selected_service = _choice(service, STANDARD_SERVICES, "Servicio")
    selected_department = _choice(department, URUGUAY_ZONES, "Departamento")
    selected_zone = _choice(zone, (ALL_DEPARTMENT, *URUGUAY_ZONES[selected_department]), "Zona")
    return selected_service, selected_department, selected_zone


def clean_arrival_time(data: dict) -> dict:
    """Canoniza servicio, departamento y zona; no acepta zonas libres."""
    service, department, zone = clean_arrival_location(
        data.get("service"), data.get("department"), data.get("zone")
    )
    minutes = data.get("base_estimated_minutes")
    if type(minutes) is not int or not 1 <= minutes <= 1440:
        raise ValueError("El tiempo base debe estar entre 1 y 1.440 minutos")
    active = data.get("is_active", True)
    if type(active) is not bool:
        raise ValueError("El estado activo debe ser verdadero o falso")
    return {
        "service": service,
        "department": department,
        "zone": zone,
        "base_estimated_minutes": minutes,
        "is_active": active,
    }


def arrival_catalog() -> dict:
    return {
        "services": list(STANDARD_SERVICES),
        "departments": {name: [ALL_DEPARTMENT, *zones] for name, zones in URUGUAY_ZONES.items()},
    }
