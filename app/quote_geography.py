"""Límite territorial de la tarifa uruguaya del Cotizador.

El GeoJSON departamental existente cubre Uruguay. Las coordenadas de otros
países pueden identificarse, pero no habilitan una tarifa regional.
"""

import json
from functools import lru_cache
from pathlib import Path


REGIONAL_PRICE_MESSAGE = (
    "El recorrido incluye un punto fuera de Uruguay. No hay tarifa regional "
    "configurada: requiere cálculo manual externo o una tarifa aprobada; "
    "no se guardó un precio automático."
)


@lru_cache(maxsize=1)
def _uruguay_polygons():
    path = Path(__file__).resolve().parent / "static" / "uruguay-departamentos.geojson"
    features = json.loads(path.read_text(encoding="utf-8"))["features"]
    polygons = []
    for feature in features:
        geometry = feature["geometry"]
        groups = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        for rings in groups:
            outer = rings[0]
            xs = [point[0] for point in outer]
            ys = [point[1] for point in outer]
            polygons.append(((min(xs), min(ys), max(xs), max(ys)), rings))
    return polygons


def _in_ring(lon, lat, ring):
    inside = False
    previous = ring[-1]
    for current in ring:
        x1, y1 = previous[:2]
        x2, y2 = current[:2]
        if ((y1 > lat) != (y2 > lat)) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
        previous = current
    return inside


def is_uruguay_point(lat, lon):
    for (left, bottom, right, top), rings in _uruguay_polygons():
        if left <= lon <= right and bottom <= lat <= top and _in_ring(lon, lat, rings[0]):
            if not any(_in_ring(lon, lat, hole) for hole in rings[1:]):
                return True
    return False


def require_uruguay_points(*points, labels=None, nearest=None):
    names = labels or ("origen", "destino", "salida de la grúa")
    for index, (lat, lon) in enumerate(points):
        if is_uruguay_point(lat, lon):
            continue
        name = names[index] if index < len(names) else "punto"
        road = nearest((lat, lon)) if nearest else None
        if road and road["distance"] > 500 and is_uruguay_point(road["location"][1], road["location"][0]):
            raise ValueError(
                f"{name.capitalize()}: ubicación en agua o sin vía cercana (la vía más próxima está a "
                f"{road['distance'] / 1000:.2f} km). Revisá el pin y elegí un punto sobre una calle uruguaya "
                f"cercana; no se guardó la cotización. No hay tarifa regional configurada."
            )
        raise ValueError(f"{name.capitalize()}: punto fuera del territorio tarifado. Elegí un punto sobre una vía uruguaya; no se guardó la cotización. No hay tarifa regional configurada.")


def require_manual_region_points(values, parser):
    if not isinstance(values, list) or len(values) > 3:
        raise ValueError("El contexto geográfico manual no es válido.")
    require_uruguay_points(*(parser(value) for value in values))


def require_uruguay_route(route, label="origen → destino"):
    coordinates = route.get("coordinates") or []
    if not coordinates:
        raise ValueError("El servicio de rutas no devolvió un recorrido verificable; usá la distancia manual.")
    for lon, lat in coordinates:
        if not is_uruguay_point(lat, lon):
            raise ValueError(f"El tramo {label} sale de Uruguay. No hay tarifa regional configurada; no se guardó la cotización.")
    for (lon1, lat1), (lon2, lat2) in zip(coordinates, coordinates[1:]):
        if not is_uruguay_point((lat1 + lat2) / 2, (lon1 + lon2) / 2):
            raise ValueError(f"El tramo {label} sale de Uruguay. No hay tarifa regional configurada; no se guardó la cotización.")


def require_near_road(route, label="origen → destino", max_snap_meters=500):
    for index, waypoint in enumerate(route.get("waypoints") or []):
        distance = waypoint.get("distance")
        point = waypoint.get("location") or []
        if len(point) != 2 or distance is None:
            raise ValueError(f"El motor de rutas no confirmó las vías del tramo {label}; usá distancia manual.")
        if float(distance) > max_snap_meters:
            end = "inicio" if index == 0 else "fin"
            raise ValueError(f"El {end} del tramo {label} está en agua o sin vía cercana: OSRM lo ajustó {float(distance):.0f} m. Elegí un punto sobre una calle; no se guardó la cotización.")
        if not is_uruguay_point(point[1], point[0]):
            raise ValueError(f"El tramo {label} se ajustó a una vía fuera de Uruguay. No hay tarifa regional configurada; no se guardó la cotización.")
