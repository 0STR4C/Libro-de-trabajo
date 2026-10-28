import json
import threading
import unittest
from http.cookiejar import CookieJar
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from app import local_server


class TransferApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_db_path = local_server.DB_PATH
        cls.test_directory = TemporaryDirectory(prefix="libro-trabajo-transfers-")
        local_server.DB_PATH = Path(cls.test_directory.name) / "transfers.db"
        local_server.SESSIONS.clear()
        local_server.initialize()
        cls.server = local_server.ThreadingHTTPServer(("127.0.0.1", 0), local_server.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.cookies = CookieJar()
        cls.opener = build_opener(HTTPCookieProcessor(cls.cookies))
        status, _ = cls.request("/api/auth/login", "POST", {"username": "admin", "password": "admin1234"})
        if status != 200:raise AssertionError("No se pudo iniciar la sesión local de prueba")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=2)
        local_server.SESSIONS.clear();local_server.DB_PATH = cls.previous_db_path
        cls.test_directory.cleanup()

    @classmethod
    def request(cls, path, method="GET", body=None):
        headers = {"Content-Type": "application/json"}
        if method in {"POST", "PUT", "PATCH", "DELETE"} and path != "/api/auth/login":
            headers["X-CSRF-Token"] = next((cookie.value for cookie in cls.cookies if cookie.name == "centro_csrf"), "")
        request = Request(cls.base_url + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers=headers)
        try:
            with cls.opener.open(request, timeout=5) as response:return response.status, json.loads(response.read() or b"{}")
        except HTTPError as error:return error.code, json.loads(error.read() or b"{}")

    def setUp(self):
        with local_server.connect() as database:database.execute("DELETE FROM scheduled_transfers")

    def payload(self, **changes):
        result = {"task_number": "LOCAL-1", "transfer_type": "Traslado Directo", "scheduled_date": "2026-12-20", "scheduled_time": "10:30", "origin": "Pando", "destination": "Montevideo", "comments": "Prueba local"}
        result.update(changes);return result

    def test_full_workflow_and_history(self):
        status, created = self.request("/api/transfers", "POST", self.payload())
        self.assertEqual(status, 201);transfer_id = created["id"]
        self.assertEqual(self.request("/api/transfers", "POST", self.payload())[0], 409)
        self.assertEqual(self.request("/api/transfers", "POST", self.payload(allow_duplicate=True))[0], 201)
        self.assertEqual(self.request(f"/api/transfers/{transfer_id}/status", "PATCH", {"status": "ASIGNADO", "provider": "Auxilio Uno", "expected_revision": created["revision"]})[0], 400)
        assigned = self.request(f"/api/transfers/{transfer_id}/status", "PATCH", {"status": "ASIGNADO", "provider": "Auxilio Uno", "responsible": "Administrador", "expected_revision": created["revision"]})
        self.assertEqual(assigned[0], 200)
        self.assertEqual(self.request(f"/api/transfers/{transfer_id}/status", "PATCH", {"status": "EN_CURSO", "expected_revision": created["revision"]})[0], 409)
        self.assertEqual(self.request(f"/api/transfers/{transfer_id}/status", "PATCH", {"status": "EN_CURSO", "expected_revision": assigned[1]["revision"]})[0], 200)
        self.assertEqual(self.request(f"/api/transfers/{transfer_id}/status", "PATCH", {"status": "FINALIZADO", "expected_revision": assigned[1]["revision"]+1})[0], 400)
        status, finalized = self.request(f"/api/transfers/{transfer_id}/status", "PATCH", {"status": "FINALIZADO", "note": "Servicio cumplido", "expected_revision": assigned[1]["revision"]+1})
        self.assertEqual(status, 200);self.assertEqual(finalized["completion_note"], "Servicio cumplido")
        self.assertEqual(self.request(f"/api/transfers/{transfer_id}", "DELETE")[0], 405)
        self.assertEqual(len(self.request(f"/api/transfers/{transfer_id}/events")[1]), 4)
        self.assertEqual(len(self.request("/api/transfers?status=FINALIZADO&responsible=Admin")[1]), 1)

    def test_invalid_route_and_edit_are_rejected(self):
        self.assertEqual(self.request("/api/transfers", "POST", self.payload(destination=" pÁnDo "))[0], 422)
        transfer_id = self.request("/api/transfers", "POST", self.payload())[1]["id"]
        self.assertEqual(self.request(f"/api/transfers/{transfer_id}", "PATCH", self.payload(origin="", destination="Montevideo"))[0], 422)

    def test_notice_comment_conflict_keeps_current_state_and_audit(self):
        status, created = self.request("/api/notices", "POST", {
            "task_number": "LOCAL-NOTICE-REVISION", "notice_type": "Consulta",
            "detail": "Prueba de edición simultánea", "allow_duplicate": True,
        })
        self.assertEqual(status, 201)
        item_id = created["id"]
        status, updated = self.request(f"/api/notices/{item_id}/status", "PATCH", {
            "expected_revision": created["revision"], "comments": "Seguimiento nuevo",
        })
        self.assertEqual(status, 200)
        self.assertEqual(updated["revision"], created["revision"] + 1)
        self.assertEqual(self.request(f"/api/notices/{item_id}")[1]["revision"],updated["revision"])
        with local_server.connect() as database:
            before = database.execute("SELECT count(*) FROM audit_events WHERE entity='notice' AND entity_id=?", (item_id,)).fetchone()[0]
        status, _ = self.request(f"/api/notices/{item_id}/status", "PATCH", {
            "expected_revision": created["revision"], "status": "RESUELTO",
            "comments": "Cierre obsoleto",
        })
        self.assertEqual(status, 409)
        with local_server.connect() as database:
            current = database.execute("SELECT status,comments,revision FROM notices WHERE id=?", (item_id,)).fetchone()
            after = database.execute("SELECT count(*) FROM audit_events WHERE entity='notice' AND entity_id=?", (item_id,)).fetchone()[0]
        self.assertEqual((current["status"], current["comments"], current["revision"]),
                         ("PENDIENTE", "Seguimiento nuevo", updated["revision"]))
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
