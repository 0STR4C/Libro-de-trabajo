"""Pruebas de seguridad PostgreSQL sobre una base temporal aislada.

La suite se omite salvo que SECURITY_TEST_DATABASE_URL esté definido. Nunca usa
la URL de producción por defecto.
"""
import json
import os
import threading
import time
import unittest
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener


@unittest.skipUnless(os.getenv("SECURITY_TEST_DATABASE_URL"), "requiere una base PostgreSQL temporal")
class PostgresSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["DATABASE_URL"] = os.environ["SECURITY_TEST_DATABASE_URL"]
        os.environ.setdefault("APP_ENV", "development")
        os.environ.setdefault("APP_SECRET", "test-app-secret-9f3c8e7b6d54120a9f3c8e7b6d54120")
        os.environ.setdefault("ADMIN_PASSWORD", "test-admin-9f3c8e7b6d54120")
        import uvicorn

        from app import postgres_server

        cls.server_module = postgres_server
        postgres_server.initialize()
        cls.config = uvicorn.Config(postgres_server.app, host="127.0.0.1", port=18765, log_level="critical")
        cls.server = uvicorn.Server(cls.config)
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        cls.base_url = "http://127.0.0.1:18765"
        cls.cookie_jar = CookieJar()
        cls.opener = build_opener(HTTPCookieProcessor(cls.cookie_jar))
        for _ in range(50):
            try:
                cls.request("/health")
                break
            except Exception:
                time.sleep(0.1)
        else:
            raise AssertionError("El servidor PostgreSQL temporal no inició")

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=5)

    def setUp(self):
        self.cookie_jar.clear()
        with self.server_module.connect() as database:
            database.execute("DELETE FROM app_sessions")
            database.execute("DELETE FROM auth_attempts")

    @classmethod
    def request(cls, path, method="GET", body=None, csrf=False):
        headers = {"Content-Type": "application/json"}
        if csrf:
            csrf_cookie = next((item.value for item in cls.cookie_jar if item.name == "centro_csrf"), "")
            headers["X-CSRF-Token"] = csrf_cookie
        request = Request(
            cls.base_url + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers=headers,
        )
        try:
            with cls.opener.open(request, timeout=5) as response:
                return response.status, response.headers, json.loads(response.read() or b"{}")
        except HTTPError as error:
            return error.code, error.headers, json.loads(error.read() or b"{}")

    @classmethod
    def login(cls):
        status, headers, body = cls.request("/api/auth/login", "POST", {"username": "admin", "password": os.environ["ADMIN_PASSWORD"]})
        if status != 200 or body != {"ok": True}:
            raise AssertionError("El login temporal no creó la sesión esperada")
        return headers

    def test_login_cookie_does_not_return_bearer(self):
        headers = self.login()
        cookies = headers.get_all("Set-Cookie")
        session = next(value for value in cookies if value.startswith("centro_session="))
        self.assertIn("HttpOnly", session)
        self.assertIn("samesite=strict", session.lower())
        self.assertNotIn("token", json.dumps({"ok": True}))

    def test_write_requires_csrf(self):
        self.login()
        status, _, _ = self.request("/api/notices", "POST", {"notice_type": "Prueba", "detail": "Prueba"})
        self.assertEqual(status, 403)

    def test_onboarding_and_admin_password_reset(self):
        from tools.user_onboarding.import_users import provision, validate_roster
        from app.security import verify_password
        import secrets
        roster=validate_roster([dict(name='Prueba alta A',email='alta-prueba-a@portoservicios.com.uy'),dict(name='Prueba alta B',email='alta-prueba-b@portoservicios.com.uy')])
        with self.server_module.connect() as db:
            self.assertEqual(provision(db,roster)['would_create'],2)
            self.assertEqual(provision(db,roster,True)['created'],2)
            self.assertEqual(provision(db,roster,True)['created'],0)
            accounts=db.execute("SELECT u.*,r.name role_name FROM users u JOIN roles r ON r.id=u.role_id WHERE email LIKE 'alta-prueba-%@portoservicios.com.uy' ORDER BY email").fetchall()
            self.assertEqual(len(accounts),2)
            self.assertTrue(all(r['role_name']=='Telefonista' for r in accounts))
            self.assertNotEqual(accounts[0]['password_hash'],accounts[1]['password_hash'])
        self.login()
        person=accounts[0];password=secrets.token_urlsafe(24)
        status,_,_=self.request(f"/api/users/{person['id']}",'PATCH',dict(display_name=person['display_name'],email=person['email'],role_id=person['role_id'],active=True,password=password),csrf=True)
        self.assertEqual(status,200)
        with self.server_module.connect() as db:
            updated=db.execute('SELECT password_hash FROM users WHERE id=%s',(person['id'],)).fetchone()
            self.assertTrue(verify_password(password,updated['password_hash']))
        self.cookie_jar.clear()
        self.assertEqual(self.request('/api/auth/login','POST',dict(username=person['email'],password=password))[0],200)
        self.assertEqual(self.request('/api/settings/users')[0],403)

    def test_toll_catalog_requires_admin_and_is_audited(self):
        self.login()
        payload={'name':'Peaje temporal','latitude':-34.000000,'longitude':-56.000000,'price':416,'active':True}
        status,_,_=self.request('/api/settings/tolls','POST',payload)
        self.assertEqual(status,403)
        status,_,_=self.request('/api/settings/tolls','POST',payload,csrf=True)
        self.assertEqual(status,201)
        status,_,items=self.request('/api/settings/tolls')
        self.assertEqual(status,200)
        item=next(value for value in items if value['name']=='Peaje temporal')
        payload['price']=500
        self.assertEqual(self.request(f"/api/settings/tolls/{item['id']}",'PATCH',payload,csrf=True)[0],200)
        self.assertEqual(self.request(f"/api/settings/tolls/{item['id']}",'DELETE',{},csrf=True)[0],200)

    def test_wfm_revision_publish_and_csrf(self):
        self.login()
        url='/api/wfm/plan?date=2026-09-08&team=Telefonista'
        status,_,plan=self.request(url)
        self.assertEqual(status,200)
        body=dict(plan,operation='save',demand=[0]*48)
        self.assertEqual(self.request(url,'POST',body)[0],403)
        status,_,saved=self.request(url,'POST',body,csrf=True)
        self.assertEqual(status,200)
        self.assertEqual(saved['revision'],plan['revision']+1)
        self.assertEqual(self.request(url,'POST',body,csrf=True)[0],409)
        status,_,published=self.request(url,'POST',dict(saved,operation='publish'),csrf=True)
        self.assertEqual(status,200)
        self.assertEqual(published['revision'],published['published_revision'])

    def test_logout_invalidates_session(self):
        self.login()
        status, _, _ = self.request("/api/auth/logout", "POST", {}, csrf=True)
        self.assertEqual(status, 200)
        status, _, _ = self.request("/api/auth/me")
        self.assertEqual(status, 401)

    def test_rate_limit_returns_429(self):
        with self.server_module.connect() as database:
            database.execute("DELETE FROM auth_attempts")
        for _ in range(4):
            status, _, _ = self.request("/api/auth/login", "POST", {"username": "admin", "password": "incorrecta"})
            self.assertEqual(status, 401)
        status, headers, _ = self.request("/api/auth/login", "POST", {"username": "admin", "password": "incorrecta"})
        self.assertEqual(status, 429)
        self.assertTrue(headers.get("Retry-After"))

    def test_protected_read_without_session_is_401(self):
        self.assertEqual(self.request("/api/notices")[0], 401)

    def test_schedule_conflicts_and_week_copy_on_postgres(self):
        self.login()
        with self.server_module.connect() as database:
            role_id = database.execute("SELECT id FROM roles WHERE name='Telefonista'").fetchone()["id"]
            user_id = database.execute(
                "INSERT INTO users(username,display_name,password_hash,role_id,active) VALUES(%s,%s,%s,%s,TRUE) RETURNING id",
                ("telefonista.pg", "Telefonista PostgreSQL", self.server_module.hash_password("ephemeral-user-password"), role_id),
            ).fetchone()["id"]
        schedule = {"user_id": user_id, "schedule_date": "2026-12-09", "shift_name": "Mañana", "start_time": "09:00", "end_time": "17:00"}
        self.assertEqual(self.request("/api/schedules", "POST", schedule, csrf=True)[0], 201)
        status, _, body = self.request("/api/schedules", "POST", schedule, csrf=True)
        self.assertEqual(status, 409)
        self.assertIn("mismo horario", body["detail"])
        status, _, body = self.request("/api/schedules", "POST", {**schedule, "shift_name": "Tarde", "start_time": "16:00", "end_time": "20:00"}, csrf=True)
        self.assertEqual(status, 409)
        self.assertIn("superpone", body["detail"])
        first = self.request("/api/schedules/copy-week", "POST", {"source_week": "2026-12-07", "target_week": "2026-12-14", "employee_id": user_id}, csrf=True)
        self.assertEqual(first[0], 201)
        self.assertEqual((first[2]["copied"], first[2]["skipped"]), (1, 0))
        second = self.request("/api/schedules/copy-week", "POST", {"source_week": "2026-12-07", "target_week": "2026-12-14", "employee_id": user_id}, csrf=True)
        self.assertEqual((second[2]["copied"], second[2]["skipped"]), (0, 1))

    def test_backup_path_is_not_served(self):
        status, _, _ = self.request("/postgres-backups/centro_operativo_test.dump")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
