import json
import hashlib
import sqlite3
import threading
import unittest
from contextlib import closing
from http.cookiejar import CookieJar
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from app import local_server


class QuoteApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db = Path(__file__).with_name("quote_test.db")
        if cls.test_db.exists():
            cls.test_db.unlink()
        local_server.DB_PATH = cls.test_db
        local_server.SESSIONS.clear()
        local_server.initialize()
        cls.server = local_server.ThreadingHTTPServer(("127.0.0.1", 0), local_server.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.cookie_jar = CookieJar()
        cls.opener = build_opener(HTTPCookieProcessor(cls.cookie_jar))
        login = cls.request("/api/auth/login", "POST", {"username": "admin", "password": "admin1234"})
        if login != {"ok": True}:
            raise AssertionError("El login de prueba no creó la sesión esperada")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        if cls.test_db.exists():
            cls.test_db.unlink()

    @classmethod
    def request(cls, path, method="GET", body=None, authenticated=False):
        headers = {"Content-Type": "application/json"}
        if authenticated and method in {"POST", "PUT", "PATCH", "DELETE"}:
            csrf = next((cookie.value for cookie in cls.cookie_jar if cookie.name == "centro_csrf"), "")
            headers["X-CSRF-Token"] = csrf
        payload = json.dumps(body).encode() if body is not None else None
        request = Request(cls.base_url + path, data=payload, method=method, headers=headers)
        try:
            with cls.opener.open(request, timeout=5) as response:
                cls.last_response_headers = response.headers
                return json.loads(response.read())
        except HTTPError as error:
            detail = json.loads(error.read())
            raise AssertionError(f"HTTP {error.code}: {detail}") from error

    @classmethod
    def request_error(cls, path, method="POST", body=None, authenticated=False):
        headers = {"Content-Type": "application/json"}
        if authenticated and method in {"POST", "PUT", "PATCH", "DELETE"}:
            csrf = next((cookie.value for cookie in cls.cookie_jar if cookie.name == "centro_csrf"), "")
            headers["X-CSRF-Token"] = csrf
        request = Request(cls.base_url + path, data=json.dumps(body or {}).encode(), method=method, headers=headers)
        try:
            cls.opener.open(request, timeout=5)
        except HTTPError as error:
            return error.code, json.loads(error.read())
        raise AssertionError("Se esperaba una respuesta de error")

    def test_manual_insured_quote_uses_included_kilometres(self):
        result = self.request(
            "/api/quotes/calculate",
            "POST",
            {
                "origin": "Origen de prueba",
                "destination": "Destino de prueba",
                "manual_distance": True,
                "manual_trip_km": 27,
                "include_mobile": False,
                "uninsured": False,
                "special": False,
                "gavilan": False,
                "task_number": "987654",
            },
            authenticated=True,
        )
        self.assertEqual(result["base_price"], 2140)
        self.assertEqual(result["extra_km"], 2)
        self.assertEqual(result["total_price"], 2380)
        self.assertEqual(result["task_number"], "987654")

    def test_manual_quote_does_not_require_locations(self):
        result = self.request(
            "/api/quotes/calculate",
            "POST",
            {
                "manual_distance": True,
                "manual_trip_km": 20,
                "include_mobile": False,
                "uninsured": True,
                "special": False,
                "gavilan": False,
            },
            authenticated=True,
        )
        self.assertEqual(result["mode"], "manual")
        self.assertEqual(result["total_price"], 2750)

    def test_quote_rules_expose_coverage_specific_catalog(self):
        rules = self.request("/api/settings/quote-rules", authenticated=True)
        for field in ("transfer_insured_base", "transfer_uninsured_base", "toll_insured", "toll_uninsured"):
            self.assertIn(field, rules)
        original = rules["transfer_uninsured_base"]
        rules["transfer_uninsured_base"] = original + 1
        self.request("/api/settings/quote-rules", "PATCH", rules, authenticated=True)
        updated = self.request("/api/settings/quote-rules", authenticated=True)
        self.assertEqual(updated["transfer_uninsured_base"], original + 1)

    def test_uninsured_gavilan_quote_is_allowed(self):
        result = self.request(
            "/api/quotes/calculate",
            "POST",
            {
                "manual_distance": True,
                "manual_trip_km": 20,
                "include_mobile": False,
                "uninsured": True,
                "special": False,
                "gavilan": True,
            },
            authenticated=True,
        )
        self.assertEqual(result["customer_type"], "No asegurado · Gavilán")

    def test_schedule_history_can_be_created_and_filtered_by_week(self):
        with local_server.connect() as database:
            role_id=database.execute("SELECT id FROM roles WHERE name='Telefonista'").fetchone()[0]
            database.execute("INSERT INTO users(username,display_name,password_hash,role_id,active) VALUES(?,?,?,?,1)",("telefonista.prueba","Telefonista de prueba",local_server.hash_password("telefonista-prueba"),role_id))
            user_id=database.execute("SELECT id FROM users WHERE username='telefonista.prueba'").fetchone()[0]
        created=self.request("/api/schedules","POST",{"user_id":user_id,"schedule_date":"2026-09-07","shift_name":"Mañana","start_time":"08:00","end_time":"16:00","notes":"Cobertura"},authenticated=True)
        self.assertEqual(created["week_start"],"2026-09-07")
        rows=self.request("/api/schedules?week=2026-09-07&employee_id=%s"%user_id,authenticated=True)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["display_name"],"Telefonista de prueba")
        self.assertEqual(len(self.request("/api/schedules?week=2026-09-07&q=Cobertura",authenticated=True)),1)
        self.assertEqual(self.request("/api/schedules?week=2026-09-07&q=Inexistente",authenticated=True),[])
        self.request("/api/schedules/%s"%created["id"],"PATCH",{"user_id":user_id,"schedule_date":"2026-09-08","shift_name":"Tarde","start_time":"14:00","end_time":"22:00"},authenticated=True)
        self.request("/api/schedules/%s"%created["id"],"DELETE",authenticated=True)

    def test_schedule_copy_week_is_idempotent_and_preserves_dates(self):
        with local_server.connect() as database:
            role_id=database.execute("SELECT id FROM roles WHERE name='Planificador'").fetchone()[0]
            database.execute("INSERT INTO users(username,display_name,password_hash,role_id,active) VALUES(?,?,?,?,1)",("planificador.copia","Planificador copia",local_server.hash_password("planificador-copia"),role_id))
            user_id=database.execute("SELECT id FROM users WHERE username='planificador.copia'").fetchone()[0]
        self.request("/api/schedules","POST",{"user_id":user_id,"schedule_date":"2026-10-07","shift_name":"Administrativo","start_time":"09:00","end_time":"17:00","notes":"Reunión semanal"},authenticated=True)
        first=self.request("/api/schedules/copy-week","POST",{"source_week":"2026-10-05","target_week":"2026-10-12","employee_id":user_id},authenticated=True)
        self.assertEqual((first["copied"],first["skipped"]),(1,0))
        second=self.request("/api/schedules/copy-week","POST",{"source_week":"2026-10-05","target_week":"2026-10-12","employee_id":user_id},authenticated=True)
        self.assertEqual((second["copied"],second["skipped"]),(0,1))
        copied=self.request("/api/schedules?week=2026-10-12&employee_id=%s"%user_id,authenticated=True)
        self.assertEqual(len(copied),1)
        self.assertEqual(copied[0]["schedule_date"],"2026-10-14")
        self.assertEqual(copied[0]["notes"],"Reunión semanal")

    def test_schedule_rejects_duplicates_and_overnight_overlaps(self):
        with local_server.connect() as database:
            role_id=database.execute("SELECT id FROM roles WHERE name='Telefonista'").fetchone()[0]
            database.execute("INSERT INTO users(username,display_name,password_hash,role_id,active) VALUES(?,?,?,?,1)",("telefonista.conflicto","Telefonista conflicto",local_server.hash_password("telefonista-conflicto"),role_id))
            user_id=database.execute("SELECT id FROM users WHERE username='telefonista.conflicto'").fetchone()[0]
        schedule={"user_id":user_id,"schedule_date":"2026-11-02","shift_name":"Noche","start_time":"22:00","end_time":"06:00"}
        self.request("/api/schedules","POST",schedule,authenticated=True)
        code,detail=self.request_error("/api/schedules","POST",schedule,authenticated=True)
        self.assertEqual(code,409)
        self.assertIn("mismo horario",detail["detail"])
        code,detail=self.request_error("/api/schedules","POST",{"user_id":user_id,"schedule_date":"2026-11-03","shift_name":"Mañana","start_time":"05:00","end_time":"12:00"},authenticated=True)
        self.assertEqual(code,409)
        self.assertIn("superpone",detail["detail"])
        adjacent=self.request("/api/schedules","POST",{"user_id":user_id,"schedule_date":"2026-11-03","shift_name":"Mañana","start_time":"06:00","end_time":"12:00"},authenticated=True)
        self.assertEqual(adjacent["start_time"],"06:00")

    def test_mobile_distance_is_added_to_trip(self):
        result = self.request(
            "/api/quotes/calculate",
            "POST",
            {
                "origin": "Origen de prueba",
                "destination": "Destino de prueba",
                "mobile_origin": "Salida de prueba",
                "manual_distance": True,
                "manual_trip_km": 22,
                "manual_mobile_km": 10,
                "include_mobile": True,
                "uninsured": False,
                "special": False,
                "gavilan": False,
            },
            authenticated=True,
        )
        self.assertEqual(result["total_km"], 32)
        self.assertEqual(result["extra_km"], 7)
        self.assertEqual(result["total_price"], 2980)

    def test_manual_tolls_use_configured_unit_price(self):
        result = self.request(
            "/api/quotes/calculate",
            "POST",
            {
                "manual_distance": True,
                "manual_trip_km": 20,
                "include_mobile": False,
                "include_tolls": True,
                "manual_toll_count": 3,
                "uninsured": False,
                "special": False,
                "gavilan": False,
            },
            authenticated=True,
        )
        self.assertEqual(result["toll_count"], 3)
        self.assertEqual(result["toll_price"], 1248)
        self.assertEqual(result["total_price"], 3388)
        self.assertEqual(result["toll_details"][0]["name"], "Peajes manuales (3)")

    def test_manual_tolls_require_a_positive_integer_when_enabled(self):
        status, error = self.request_error(
            "/api/quotes/calculate",
            "POST",
            {
                "manual_distance": True,
                "manual_trip_km": 20,
                "include_tolls": True,
                "manual_toll_count": 0,
            },
            authenticated=True,
        )
        self.assertEqual(status, 400)
        self.assertIn("cantidad válida de peajes", error["detail"])
        status, error = self.request_error(
            "/api/quotes/calculate",
            "POST",
            {
                "manual_distance": True,
                "manual_trip_km": 20,
                "include_tolls": True,
                "manual_toll_count": 1.5,
            },
            authenticated=True,
        )
        self.assertEqual(status, 400)
        self.assertIn("cantidad válida de peajes", error["detail"])

    def test_quote_history_is_persisted(self):
        history = self.request("/api/quotes", authenticated=True)
        self.assertGreaterEqual(len(history), 2)
        self.assertEqual(history[0]["created_by"], "Administrador")

    def test_user_coordinate_formats_are_supported(self):
        full_link = "https://www.google.com/maps/place/34%C2%B051'50.7%22S+55%C2%B007'31.0%22W/@-34.8640815,-55.1278455,17z/data=!3m1!4b1!4m4!3m3!8m2!3d-34.8640859!4d-55.1252706"
        self.assertEqual(local_server.parse_coordinates(full_link), (-34.8640859, -55.1252706))
        self.assertEqual(
            local_server.parse_coordinates("-34.86408594691901, -55.12527063102186"),
            (-34.86408594691901, -55.12527063102186),
        )

    def test_corporate_user_and_google_login(self):
        roles = self.request("/api/settings/roles", authenticated=True)
        telefonista = next(role for role in roles if role["name"] == "Telefonista")
        status, error = self.request_error(
            "/api/settings/users",
            body={"display_name": "Externo", "email": "externo@gmail.com", "role_id": telefonista["id"]},
            authenticated=True,
        )
        self.assertEqual(status, 400)
        self.assertIn("@portoservicios.com.uy", error["detail"])
        self.request(
            "/api/settings/users",
            "POST",
            {
                "display_name": "Operador Google",
                "email": "operador@portoservicios.com.uy",
                "password": "alternativa123",
                "role_id": telefonista["id"],
            },
            authenticated=True,
        )
        password_login = self.request(
            "/api/auth/login",
            "POST",
            {"username": "operador@portoservicios.com.uy", "password": "alternativa123"},
        )
        self.assertEqual(password_login, {"ok": True})
        with local_server.connect() as database:
            database.execute(
                "UPDATE app_settings SET value=? WHERE key='google_client_id'",
                ("123456789-test.apps.googleusercontent.com",),
            )
        config = self.request("/api/auth/google-config")
        self.assertEqual(config["allowed_domain"], "portoservicios.com.uy")
        identity = {
            "sub": "google-user-123",
            "email": "operador@portoservicios.com.uy",
            "hd": "portoservicios.com.uy",
            "email_verified": True,
        }
        with patch.object(local_server, "verify_google_id_token", return_value=identity):
            result = self.request(
                "/api/auth/google",
                "POST",
                {"credential": "token-de-prueba", "nonce": config["nonce"]},
            )
        self.assertEqual(result, {"ok": True})
        with local_server.connect() as database:
            linked = database.execute(
                "SELECT google_sub FROM users WHERE email='operador@portoservicios.com.uy'"
            ).fetchone()[0]
        self.assertEqual(linked, "google-user-123")
        self.request("/api/auth/login", "POST", {"username": "admin", "password": "admin1234"})

    def test_cookie_session_csrf_logout_and_expiration(self):
        result = self.request("/api/auth/login", "POST", {"username": "admin", "password": "admin1234"})
        self.assertEqual(result, {"ok": True})
        cookies = self.last_response_headers.get_all("Set-Cookie")
        session_cookie = next(value for value in cookies if value.startswith("centro_session="))
        self.assertIn("HttpOnly", session_cookie)
        self.assertIn("SameSite=Strict", session_cookie)
        self.assertIn("Path=/", session_cookie)
        self.assertNotIn("Domain=", session_cookie)
        self.assertNotIn("token", result)

        status, _ = self.request_error("/api/notices", "POST", {"detail": "sin csrf"}, authenticated=False)
        self.assertEqual(status, 403)

        self.request("/api/auth/logout", "POST", {}, authenticated=True)
        status, _ = self.request_error("/api/auth/me", "GET")
        self.assertEqual(status, 401)

        self.request("/api/auth/login", "POST", {"username": "admin", "password": "admin1234"})
        token = next(cookie.value for cookie in self.cookie_jar if cookie.name == "centro_session")
        local_server.SESSIONS[token]["last_seen"] = 0
        status, _ = self.request_error("/api/auth/me", "GET")
        self.assertEqual(status, 401)
        self.request("/api/auth/login", "POST", {"username": "admin", "password": "admin1234"})

    def test_custom_roles_can_be_created(self):
        role = self.request(
            "/api/settings/roles",
            "POST",
            {"name": "Coordinador de prueba", "description": "Rol temporal de pruebas"},
            authenticated=True,
        )
        self.assertEqual(role["name"], "Coordinador de prueba")
        self.assertEqual(role["permissions"], [])

    def test_last_active_administrator_cannot_be_disabled(self):
        users = self.request("/api/settings/users", authenticated=True)
        admin = next(user for user in users if user["username"] == "admin")
        roles = self.request("/api/settings/roles", authenticated=True)
        admin_role = next(role for role in roles if role["name"] == "Administrador")
        status, error = self.request_error(
            f"/api/users/{admin['id']}",
            "PATCH",
            {
                "display_name": "Administrador",
                "email": "admin@portoservicios.com.uy",
                "role_id": admin_role["id"],
                "active": False,
            },
            authenticated=True,
        )
        self.assertEqual(status, 400)
        self.assertIn("Administrador activo", error["detail"])

    def test_daily_backup_is_consistent_and_never_overwrites(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "centro_operativo.db"
            backup_directory = root / "backups"
            with closing(sqlite3.connect(source)) as database:
                database.execute("CREATE TABLE sample(value TEXT)")
                database.execute("INSERT INTO sample(value) VALUES('registro conservado')")
                database.commit()
            original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            with patch.object(local_server, "DB_PATH", source), patch.object(local_server, "BACKUP_DIR", backup_directory):
                first = local_server.create_daily_backup()
                second = local_server.create_daily_backup()
            self.assertEqual(first, second)
            self.assertEqual(original_hash, hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(len(list(backup_directory.glob("*.db"))), 1)
            with closing(sqlite3.connect(first)) as database:
                self.assertEqual(database.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(database.execute("SELECT value FROM sample").fetchone()[0], "registro conservado")

    def test_z_administrator_permissions_are_restored_on_restart(self):
        with local_server.connect() as database:
            role_id = database.execute("SELECT id FROM roles WHERE name='Administrador'").fetchone()[0]
            database.execute(
                "DELETE FROM role_permissions WHERE role_id=? AND permission='quotes.create'",
                (role_id,),
            )
        local_server.initialize()
        with local_server.connect() as database:
            restored = database.execute(
                "SELECT 1 FROM role_permissions WHERE role_id=? AND permission='quotes.create'",
                (role_id,),
            ).fetchone()
        self.assertIsNotNone(restored)


if __name__ == "__main__":
    unittest.main()
