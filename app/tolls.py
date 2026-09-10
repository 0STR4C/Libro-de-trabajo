"""Catálogo local y detección de peajes sobre geometrías GeoJSON [longitud, latitud]."""
from math import cos, hypot, pi

# Un peaje puede estar ubicado en la calzada opuesta, una colectora o una
# coordenada de referencia de la estación. 300 m tolera esas variantes sin
# convertir rutas que solo pasan "cerca" de una autopista en cobros erróneos.
DEFAULT_TOLL_RADIUS_METERS = 300


def point_segment_distance_meters(latitude, longitude, start, end):
    """Distancia local aproximada, precisa a escala de un peaje y su calzada."""
    reference_lat = latitude * pi / 180
    scale_x = 111_320 * cos(reference_lat)
    scale_y = 110_540
    px, py = longitude * scale_x, latitude * scale_y
    ax, ay = float(start[0]) * scale_x, float(start[1]) * scale_y
    bx, by = float(end[0]) * scale_x, float(end[1]) * scale_y
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return hypot(px - ax, py - ay)
    factor = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return hypot(px - (ax + factor * dx), py - (ay + factor * dy))


def segment_crosses_toll(coordinates, toll, radius_meters=DEFAULT_TOLL_RADIUS_METERS):
    if len(coordinates) < 2:
        return False
    return any(point_segment_distance_meters(toll['latitude'], toll['longitude'], start, end) <= radius_meters
               for start, end in zip(coordinates, coordinates[1:]))


def detect_toll_passes(route_segments, tolls, default_price):
    """Una estación se cobra una vez por cada tramo del servicio que la cruza.

    Así, si el móvil y luego el traslado pasan la misma estación, son dos
    pasadas reales. Se conserva el precio efectivo para el historial.
    """
    passes = []
    for segment in route_segments:
        for toll in tolls:
            if not toll.get('active', True):
                continue
            if segment_crosses_toll(segment.get('coordinates') or [], toll):
                price = float(toll['price']) if toll.get('price') is not None else float(default_price)
                passes.append({
                    'toll_id': int(toll['id']), 'name': toll['name'],
                    'segment': segment['label'], 'price': round(price, 2),
                    'latitude': float(toll['latitude']), 'longitude': float(toll['longitude']),
                })
    return passes
