"""The browser fallback must never disguise a missing API or asset."""

import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from fastapi import HTTPException

from app import local_server, postgres_server


class BrowserFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = local_server.ThreadingHTTPServer(("127.0.0.1", 0), local_server.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def fetch(self, path):
        try:
            with urlopen(self.base + path, timeout=3) as response:
                return response.status, response.headers.get_content_type(), response.read()
        except HTTPError as error:
            return error.code, error.headers.get_content_type(), error.read()

    def test_local_direct_navigation_and_missing_resources(self):
        for path in ("/", "/avisos", "/programados", "/configuracion/tiempos-estandar", "/sin-ruta"):
            status, content_type, body = self.fetch(path)
            self.assertEqual((status, content_type), (200, "text/html"), path)
            self.assertIn(b'id="root"', body)
        for path in ("/api/ruta-inexistente", "/static/recurso-inexistente.js", "/recurso-inexistente.js"):
            status, _, body = self.fetch(path)
            self.assertEqual(status, 404, path)
            self.assertNotIn(b'id="root"', body)
        self.assertEqual(self.fetch("/health")[0], 200)

    def test_postgres_fallback_is_scoped_to_navigation(self):
        response = postgres_server.react_navigation("supervision/planificacion")
        self.assertEqual(Path(response.path).name, "index.html")
        for path in ("api/ruta-inexistente", "static/recurso-inexistente.js", "recurso-inexistente.js"):
            with self.assertRaises(HTTPException) as failure:
                postgres_server.react_navigation(path)
            self.assertEqual(failure.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
