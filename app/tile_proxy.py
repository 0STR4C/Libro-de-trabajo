"""Proxy acotado y cacheado para los mosaicos raster estándar de OpenStreetMap."""

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
MIN_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
MAX_TILE_BYTES = 2 * 1024 * 1024
DEFAULT_CACHE_DIR = Path(os.getenv("OSM_TILE_CACHE_DIR", "/tmp/libro-de-trabajo-osm-tiles"))
DEFAULT_USER_AGENT = os.getenv(
    "OSM_TILE_USER_AGENT",
    f"LibroDeTrabajo/1.0 (+{os.getenv('PUBLIC_BASE_URL', 'http://localhost:8000')})",
).strip()
_write_lock = threading.Lock()


class TileProxyError(RuntimeError):
    """Indica que el mosaico no pudo obtenerse ni recuperarse de la caché."""


@dataclass(frozen=True)
class TilePayload:
    content: bytes
    cache_status: str


def validate_tile_coordinates(z: int, x: int, y: int) -> None:
    if not 0 <= z <= 19:
        raise ValueError("Nivel de zoom fuera de rango")
    coordinate_limit = 1 << z
    if not 0 <= x < coordinate_limit or not 0 <= y < coordinate_limit:
        raise ValueError("Coordenadas de mosaico fuera de rango")


def _safe_referer(value: str) -> str:
    parsed = urlparse(value or "")
    return value[:2048] if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def _cached_tile(path: Path, now: float, ttl_seconds: int) -> bytes | None:
    try:
        if now - path.stat().st_mtime <= ttl_seconds:
            return path.read_bytes()
    except OSError:
        return None
    return None


def fetch_osm_tile(
    z: int,
    x: int,
    y: int,
    *,
    referer: str = "",
    cache_dir: Path | None = None,
    user_agent: str | None = None,
    opener=None,
    now: float | None = None,
) -> TilePayload:
    """Obtiene un mosaico visible y conserva una copia durante al menos siete días."""
    validate_tile_coordinates(z, x, y)
    current_time = time.time() if now is None else now
    cache_root = DEFAULT_CACHE_DIR if cache_dir is None else Path(cache_dir)
    cache_path = cache_root / str(z) / str(x) / f"{y}.png"
    cached = _cached_tile(cache_path, current_time, MIN_CACHE_TTL_SECONDS)
    if cached is not None:
        return TilePayload(cached, "HIT")

    headers = {
        "User-Agent": (user_agent or DEFAULT_USER_AGENT).strip() or "LibroDeTrabajo/1.0",
        "Accept": "image/png,image/*;q=0.8,*/*;q=0.5",
    }
    forwarded_referer = _safe_referer(referer)
    if forwarded_referer:
        headers["Referer"] = forwarded_referer
    request = Request(OSM_TILE_URL.format(z=z, x=x, y=y), headers=headers)
    open_request = urlopen if opener is None else opener
    try:
        with open_request(request, timeout=10) as upstream:
            content_type = upstream.headers.get_content_type()
            content = upstream.read(MAX_TILE_BYTES + 1)
        if content_type != "image/png" or not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise TileProxyError("OpenStreetMap devolvió una respuesta que no es PNG")
        if len(content) > MAX_TILE_BYTES:
            raise TileProxyError("El mosaico recibido supera el tamaño permitido")
        with _write_lock:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = cache_path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
            temporary.write_bytes(content)
            os.replace(temporary, cache_path)
        return TilePayload(content, "MISS")
    except (HTTPError, URLError, TimeoutError, OSError, TileProxyError) as error:
        try:
            stale = cache_path.read_bytes()
        except OSError:
            raise TileProxyError("No se pudo obtener el mosaico de OpenStreetMap") from error
        return TilePayload(stale, "STALE")
