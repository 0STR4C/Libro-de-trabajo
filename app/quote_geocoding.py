"""Búsqueda de direcciones del Cotizador mediante un servicio Photon configurable."""

import json
import math
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen


COUNTRIES = {"UY": "Uruguay", "AR": "Argentina", "BR": "Brasil"}


class GeocodingUnavailable(Exception):
    pass


def normalize_photon_results(payload, country=None):
    results = []
    for feature in payload.get("features", [])[:12]:
        properties = feature.get("properties") or {}
        code = str(properties.get("countrycode") or "").upper()
        coordinates = (feature.get("geometry") or {}).get("coordinates") or []
        if code not in COUNTRIES or (country and code != country) or len(coordinates) < 2:
            continue
        lon, lat = coordinates[:2]
        if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in (lat, lon)):
            continue
        street = " ".join(str(properties.get(key) or "").strip() for key in ("street", "housenumber")).strip()
        name = str(properties.get("name") or "").strip()
        locality = next((str(properties.get(key)).strip() for key in ("city", "town", "village", "locality", "district") if properties.get(key)), "")
        state = str(properties.get("state") or "").strip()
        primary = street or name or locality
        label = ", ".join(dict.fromkeys(part for part in (primary, locality, state, COUNTRIES[code]) if part))
        if not label:
            continue
        results.append({"label": label, "latitude": lat, "longitude": lon, "country_code": code})
    return results


def search_address(query, country=None):
    text = str(query or "").strip()
    if len(text) < 4 or len(text) > 120 or any(ord(char) < 32 for char in text):
        raise ValueError("Escribí entre 4 y 120 caracteres para buscar una dirección.")
    if country and country not in COUNTRIES:
        raise ValueError("Elegí Uruguay, Argentina o Brasil para buscar la dirección.")
    configured = os.environ.get("GEOCODER_URL", "").strip()
    base = configured or ("https://photon.komoot.io" if os.environ.get("APP_ENV", "development") != "production" else "")
    if not base:
        raise GeocodingUnavailable("La búsqueda de direcciones requiere configurar GEOCODER_URL; podés ingresar coordenadas mientras tanto.")
    parameters = urlencode([("q", text), ("limit", "12"), *[("countrycode", code) for code in ([country] if country else COUNTRIES)]])
    request = Request(f"{base.rstrip('/')}/api?{parameters}", headers={"User-Agent": "LibroDeTrabajo/1.0 (cotizador geocoding)", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=5) as response:
            raw = response.read(262145)
        if len(raw) > 262144:
            raise ValueError("respuesta demasiado extensa")
        return normalize_photon_results(json.loads(raw), country)
    except Exception as error:
        raise GeocodingUnavailable("La búsqueda de direcciones no respondió. Podés ingresar coordenadas o un enlace de Maps.") from error
