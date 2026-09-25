import os
import tempfile
import unittest
from email.message import Message
from pathlib import Path

from app.tile_proxy import MIN_CACHE_TTL_SECONDS, TileProxyError, fetch_osm_tile, validate_tile_coordinates


PNG = b"\x89PNG\r\n\x1a\nsynthetic-tile"


class FakeResponse:
    def __init__(self, content=PNG, content_type="image/png"):
        self.content = content
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return self.content


class TileProxyTests(unittest.TestCase):
    def test_fetch_sets_identity_referer_and_reuses_seven_day_cache(self):
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return FakeResponse()

        with tempfile.TemporaryDirectory() as directory:
            cache_dir = Path(directory)
            first = fetch_osm_tile(3, 4, 5, cache_dir=cache_dir, user_agent="LibroDeTrabajo/Test (+https://example.test)", referer="https://example.test/cotizador", opener=opener, now=1_000_000)
            second = fetch_osm_tile(3, 4, 5, cache_dir=cache_dir, user_agent="LibroDeTrabajo/Test", opener=lambda *_args, **_kwargs: self.fail("No debe consultar el origen con caché vigente"), now=1_000_000 + MIN_CACHE_TTL_SECONDS - 1)

        self.assertEqual(first.cache_status, "MISS")
        self.assertEqual(second.cache_status, "HIT")
        self.assertEqual(second.content, PNG)
        self.assertEqual(len(calls), 1)
        request, timeout = calls[0]
        self.assertEqual(request.full_url, "https://tile.openstreetmap.org/3/4/5.png")
        self.assertEqual(request.get_header("User-agent"), "LibroDeTrabajo/Test (+https://example.test)")
        self.assertEqual(request.get_header("Referer"), "https://example.test/cotizador")
        self.assertEqual(timeout, 10)

    def test_stale_tile_is_served_when_upstream_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "2" / "1" / "1.png"
            cache_path.parent.mkdir(parents=True)
            cache_path.write_bytes(PNG)
            os.utime(cache_path, (1, 1))
            tile = fetch_osm_tile(2, 1, 1, cache_dir=Path(directory), opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()), now=MIN_CACHE_TTL_SECONDS + 2)

        self.assertEqual(tile.cache_status, "STALE")
        self.assertEqual(tile.content, PNG)

    def test_rejects_invalid_coordinates_and_non_png_responses(self):
        with self.assertRaises(ValueError):
            validate_tile_coordinates(20, 0, 0)
        with self.assertRaises(ValueError):
            validate_tile_coordinates(2, 4, 0)
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(TileProxyError):
            fetch_osm_tile(0, 0, 0, cache_dir=Path(directory), opener=lambda *_args, **_kwargs: FakeResponse(b"not-an-image", "text/html"))


if __name__ == "__main__":
    unittest.main()
