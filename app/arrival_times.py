"""Validación del catálogo de tiempos base de arribo."""

from __future__ import annotations

from .delays import STANDARD_SERVICES, normalized_key, split_zones
from .geography import ALL_DEPARTMENT, URUGUAY_ZONES


def _choice(value: str, choices, label: str) -> str:
    key = normalized_key(value)
    selected = next((item for item in choices if normalized_key(item) == key), None)
    if selected is None:
        raise ValueError(f"{label} inválido")
    return selected


INDICATION_TYPES = ("TIME", "MAXIMUM", "INTERVAL", "TO_CONFIRM")

# Nombres legibles en las capturas de la planilla. Solo amplían el selector de
# ubicaciones; no asignan minutos ni publican referencias operativas.
ARRIVAL_EXTRA_ZONES = {
    "MONTEVIDEO": ("Mercado Modelo", "Nuevo París"),
    "CANELONES": (
        "Empalme Olmos", "Joaquín Suárez", "Neptunia", "Pinamar", "Marindia",
        "Fortín de Santa Rosa", "Villa Argentina", "Las Toscas", "Costa Azul",
        "Bello Horizonte", "San Luis", "La Tuna", "Santa Lucía del Este",
        "Cuchilla Alta", "Santa Ana", "Jaureguiberry",
    ),
}
ARRIVAL_ZONES = {
    department: (*zones, *ARRIVAL_EXTRA_ZONES.get(department, ()))
    for department, zones in URUGUAY_ZONES.items()
}


def clean_arrival_location(service, department, zone, *, allow_group=False) -> tuple[str, str, str]:
    """Canoniza la ubicación; las agrupaciones se admiten solo para guardar o comparar."""
    selected_service = _choice(service, STANDARD_SERVICES, "Servicio")
    selected_department = _choice(department, ARRIVAL_ZONES, "Departamento")
    choices = (ALL_DEPARTMENT, *ARRIVAL_ZONES[selected_department])
    parts = split_zones(zone) if allow_group else [zone]
    if not parts:
        raise ValueError("Zona inválida")
    selected_parts = [_choice(part, choices, "Zona") for part in parts]
    if ALL_DEPARTMENT in selected_parts and len(selected_parts) > 1:
        raise ValueError("Todo el departamento no puede combinarse con otras zonas")
    selected_zone = ", ".join(sorted(selected_parts, key=lambda part: choices.index(part)))
    return selected_service, selected_department, selected_zone


def arrival_members(zone: str) -> list[str]:
    return [] if zone == ALL_DEPARTMENT else split_zones(zone)


def indication_text(item: dict) -> str:
    kind = item.get("indication_type") or "TIME"
    if kind == "MAXIMUM":
        return f"Máximo de {item['minutes_max']} min"
    if kind == "INTERVAL":
        return f"Entre {item['minutes_min']} y {item['minutes_max']} min"
    if kind == "TO_CONFIRM":
        return "A confirmar"
    return f"{item['base_estimated_minutes']} min habituales"


def clean_arrival_time(data: dict) -> dict:
    """Canoniza servicio, departamento y zona; no acepta zonas libres."""
    service, department, zone = clean_arrival_location(
        data.get("service"), data.get("department"), data.get("zone"), allow_group=True
    )
    kind = data.get("indication_type") or "TIME"
    if kind not in INDICATION_TYPES:
        raise ValueError("Tipo de indicación inválido")
    minutes, minimum, maximum = (data.get(name) for name in ("base_estimated_minutes", "minutes_min", "minutes_max"))
    for value in (minutes, minimum, maximum):
        if value is not None and (type(value) is not int or not 1 <= value <= 1440):
            raise ValueError("Los minutos deben estar entre 1 y 1.440")
    if kind == "TIME" and (minutes is None or minimum is not None or maximum is not None):
        raise ValueError("El tiempo habitual requiere un único valor en minutos")
    if kind == "MAXIMUM" and (maximum is None or minutes is not None or minimum is not None):
        raise ValueError("El máximo requiere solo el límite superior")
    if kind == "INTERVAL" and (minimum is None or maximum is None or minimum > maximum or minutes is not None):
        raise ValueError("El intervalo requiere mínimo y máximo ordenados")
    if kind == "TO_CONFIRM" and any(value is not None for value in (minutes, minimum, maximum)):
        raise ValueError("A confirmar no admite minutos")
    active = data.get("is_active", True)
    if type(active) is not bool:
        raise ValueError("El estado activo debe ser verdadero o falso")
    return {
        "service": service,
        "department": department,
        "zone": zone,
        "base_estimated_minutes": minutes,
        "indication_type": kind,
        "minutes_min": minimum,
        "minutes_max": maximum,
        "zone_members": arrival_members(zone),
        "is_active": active,
    }


def arrival_catalog() -> dict:
    return {
        "services": list(STANDARD_SERVICES),
        "departments": {name: [ALL_DEPARTMENT, *zones] for name, zones in ARRIVAL_ZONES.items()},
    }
