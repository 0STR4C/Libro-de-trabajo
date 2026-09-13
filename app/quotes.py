"""Validación y redondeo comunes del cotizador."""

import math
import re
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP


QUOTE_RULE_EXTRA_COLUMNS = {
    "gavilan_insured_base": 2140, "gavilan_uninsured_base": 2140,
    "transfer_insured_base": 2550, "transfer_uninsured_base": 2850,
    "transfer_special_insured_base": 4050, "transfer_special_uninsured_base": 4470,
    "locksmith_mvd_insured_base": 1785, "locksmith_mvd_uninsured_base": 1930,
    "locksmith_coast_insured_base": 2720, "locksmith_coast_uninsured_base": 2950,
    "locksmith_mvd_after22_insured_base": 0, "locksmith_mvd_after22_uninsured_base": 0,
    "locksmith_coast_after22_insured_base": 0, "locksmith_coast_after22_uninsured_base": 0,
    "extra_km_insured_rate": 120, "extra_km_uninsured_rate": 90,
    "special_extra_km_insured_rate": 120, "special_extra_km_uninsured_rate": 110,
    "toll_insured": 416, "toll_uninsured": 416,
    "waiting_hour_insured": 820, "waiting_hour_uninsured": 820,
    "rescue_hour_insured": 900, "rescue_hour_uninsured": 900,
}
QUOTE_RULE_LEGACY_COPIES = {
    "gavilan_insured_base": "gavilan_base", "gavilan_uninsured_base": "gavilan_base",
    "extra_km_insured_rate": "extra_km_rate", "special_extra_km_insured_rate": "special_extra_km_rate",
}


def validate_manual_distances(trip_km, mobile_km=0, include_mobile=False):
    try:
        trip = float(trip_km or 0)
        mobile = float(mobile_km or 0)
    except (TypeError, ValueError):
        raise ValueError("Las distancias manuales deben ser numéricas") from None
    if not math.isfinite(trip) or not math.isfinite(mobile):
        raise ValueError("Las distancias manuales deben ser finitas")
    if trip <= 0 or trip > 1_000_000 or mobile < 0 or mobile > 1_000_000:
        raise ValueError("La distancia manual debe estar entre 0 y 1.000.000 km")
    if include_mobile and mobile <= 0:
        raise ValueError("Ingrese los kilómetros desde la salida del móvil hasta el origen")
    return trip, mobile


def validate_manual_toll_count(value, include_tolls=False):
    if not include_tolls:
        return 0
    if isinstance(value, bool) or not re.fullmatch(r"\d+", str(value or "")):
        raise ValueError("Ingrese una cantidad válida de peajes")
    count = int(value)
    if not 1 <= count <= 100:
        raise ValueError("Ingrese una cantidad válida de peajes")
    return count


def round_distance(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            raise InvalidOperation
        return float(number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("La distancia calculada no es válida") from None


def round_currency(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            raise InvalidOperation
        return float(number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("El importe calculado no es válido") from None


def calculate_extra_km(total_km, included_km):
    try:
        difference = Decimal(str(total_km)) - Decimal(str(included_km))
        return max(0, int(difference.to_integral_value(rounding=ROUND_CEILING)))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("No se pudieron calcular los kilómetros excedentes") from None


def validate_quote_rule_values(fields, values):
    for field, value in zip(fields, values):
        maximum = 1_000_000 if field == "included_km" or field.endswith("_rate") else 1_000_000_000
        if not math.isfinite(value) or value < 0 or value > maximum:
            raise ValueError("Las tarifas y kilómetros deben ser finitos y estar dentro del rango permitido")
