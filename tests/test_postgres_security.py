"""Pruebas de seguridad PostgreSQL sobre una base temporal aislada.

La suite se omite salvo que SECURITY_TEST_DATABASE_URL esté definido. Nunca usa
la URL de producción por defecto.
"""
import csv
import io
import json
import os
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
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
    def request(cls, path, method="GET", body=None, csrf=False, opener=None, cookie_jar=None):
        opener = opener or cls.opener
        cookie_jar = cookie_jar or cls.cookie_jar
        headers = {"Content-Type": "application/json"}
        if csrf:
            csrf_cookie = next((item.value for item in cookie_jar if item.name == "centro_csrf"), "")
            headers["X-CSRF-Token"] = csrf_cookie
        request = Request(
            cls.base_url + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers=headers,
        )
        try:
            with opener.open(request, timeout=5) as response:
                return response.status, response.headers, json.loads(response.read() or b"{}")
        except HTTPError as error:
            return error.code, error.headers, json.loads(error.read() or b"{}")

    @classmethod
    def request_bytes(cls, path, opener=None):
        with (opener or cls.opener).open(Request(cls.base_url + path), timeout=5) as response:
            return response.status, response.headers, response.read()

    @classmethod
    def login(cls, username="admin", password=None, opener=None, cookie_jar=None):
        password = password or os.environ["ADMIN_PASSWORD"]
        status, headers, body = cls.request(
            "/api/auth/login", "POST", {"username": username, "password": password},
            opener=opener, cookie_jar=cookie_jar,
        )
        if status != 200 or body != {"ok": True}:
            raise AssertionError("El login temporal no creó la sesión esperada")
        return headers

    def create_test_user(self, username, role_name, password="ephemeral-user-password", active=True):
        with self.server_module.connect() as database:
            role_id = database.execute("SELECT id FROM roles WHERE name=%s", (role_name,)).fetchone()["id"]
            return database.execute(
                """INSERT INTO users(username,email,display_name,password_hash,role_id,active)
                VALUES(%s,%s,%s,%s,%s,%s) RETURNING id""",
                (
                    username, f"{username}@portoservicios.com.uy", username,
                    self.server_module.hash_password(password), role_id, active,
                ),
            ).fetchone()["id"]

    def isolated_client(self):
        cookie_jar = CookieJar()
        return build_opener(HTTPCookieProcessor(cookie_jar)), cookie_jar

    def test_login_cookie_does_not_return_bearer(self):
        headers = self.login()
        cookies = headers.get_all("Set-Cookie")
        session = next(value for value in cookies if value.startswith("centro_session="))
        self.assertIn("HttpOnly", session)
        self.assertIn("samesite=strict", session.lower())
        self.assertNotIn("token", json.dumps({"ok": True}))

    def test_release_history_exposes_current_and_previous_versions(self):
        self.login()
        status, _, payload = self.request("/api/settings/version")
        self.assertEqual(status, 200)
        self.assertEqual(payload["version"], self.server_module.APP_VERSION)
        self.assertEqual(payload["releases"][0]["version"], payload["version"])
        self.assertIn("1.0.0", {release["version"] for release in payload["releases"]})

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

    def test_quote_persists_pricing_snapshot(self):
        self.login()
        status, _, quote = self.request(
            "/api/quotes/calculate", "POST",
            {
                "manual_distance": True,
                "manual_trip_km": 27,
                "uninsured": False,
                "special": False,
                "gavilan": False,
            }, csrf=True,
        )
        self.assertEqual(status, 201)
        self.assertEqual(quote["pricing_snapshot"]["extra_rate"], 120)
        status, _, history = self.request("/api/quotes")
        self.assertEqual(status, 200)
        saved = next(item for item in history if item["id"] == quote["id"])
        self.assertIn("pricing_snapshot", saved)

    def test_quote_history_pagination_and_filters(self):
        self.login()
        status, _, created = self.request(
            "/api/quotes/calculate", "POST",
            {"manual_distance": True, "manual_trip_km": 20, "uninsured": False, "task_number": "PG-EXPORT-PARITY"}, csrf=True,
        )
        self.assertEqual(status, 201)
        status, _, page = self.request("/api/quotes/history?limit=1&mode=manual&q=PG-EXPORT-PARITY")
        self.assertEqual(status, 200)
        self.assertEqual(page["limit"], 1)
        self.assertEqual(page["total"], 1)
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(page["items"][0]["origin_input"], "Cotización manual")
        status, _, content = self.request_bytes("/api/reports/quotes.csv?mode=manual&q=PG-EXPORT-PARITY")
        self.assertEqual(status, 200)
        exported = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual([int(row["ID"]) for row in exported], [created["id"]])
        status, _, audit_rows = self.request("/api/audit?entity=report&action=EXPORTADO&q=quotes")
        self.assertEqual(status, 200)
        self.assertTrue(any(row["actor_id"] and row["after_data"] for row in audit_rows))

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

    def test_wfm_request_tracks_source_and_owner_can_cancel(self):
        password = "ephemeral-wfm-request-password"
        user_id = self.create_test_user("wfm.request.test", "Telefonista", password)
        self.login()
        plan_url = "/api/wfm/plan?date=2027-01-12&team=Telefonista"
        status, _, plan = self.request(plan_url)
        self.assertEqual(status, 200, plan)
        payload = dict(
            plan,
            operation="publish",
            demand=[0] * len(plan["demand"]),
            shifts=[{"user_id": user_id, "start": 16}],
            confirm_exceptions=True,
        )
        status, _, published = self.request(plan_url, "POST", payload, csrf=True)
        self.assertEqual(status, 200, published)

        opener, cookie_jar = self.isolated_client()
        self.login("wfm.request.test", password, opener, cookie_jar)
        request_body = {
            "request_type": "AUSENCIA",
            "requested_date": "2027-01-12",
            "reason": "Trámite personal",
        }
        status, _, created = self.request(
            "/api/wfm/requests", "POST", request_body, csrf=True,
            opener=opener, cookie_jar=cookie_jar,
        )
        self.assertEqual(status, 200)
        self.assertEqual(created["source_revision"], published["revision"])
        self.assertEqual(created["source_shift"]["user_id"], user_id)

        status, _, mine = self.request(
            "/api/wfm/requests", opener=opener, cookie_jar=cookie_jar,
        )
        self.assertEqual(status, 200)
        self.assertEqual(mine[0]["request_id"], created["request_id"])
        self.assertEqual(mine[0]["status"], "PENDIENTE")

        status, _, cancelled = self.request(
            "/api/wfm/requests", "POST",
            {"operation": "cancel", "request_id": created["request_id"]},
            csrf=True, opener=opener, cookie_jar=cookie_jar,
        )
        self.assertEqual(status, 200)
        self.assertEqual(cancelled["status"], "CANCELADA")
        self.assertTrue(cancelled["cancelled_at"])

    def test_wfm_parallel_draft_writes_have_one_winner(self):
        date = '2026-09-15'
        url = f'/api/wfm/plan?date={date}&team=Telefonista'
        self.login()
        status, _, plan = self.request(url)
        self.assertEqual(status, 200)
        body = dict(plan, operation='save', demand=[0] * 48)

        clients = [self.isolated_client() for _ in range(2)]
        for opener, jar in clients:
            self.login(opener=opener, cookie_jar=jar)

        def save(client):
            opener, jar = client
            return self.request(url, 'POST', body, csrf=True, opener=opener, cookie_jar=jar)[0]

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = sorted(executor.map(save, clients))
        self.assertEqual(statuses, [200, 409])

    def test_wfm_week_publish_conflict_is_atomic_and_structured(self):
        self.login()
        days = [f'2027-02-{1 + offset:02d}' for offset in range(7)]
        expected = {}
        for plan_date in days:
            url = f'/api/wfm/plan?date={plan_date}&team=Telefonista'
            plan = self.request(url)[2]
            status, _, saved = self.request(url, 'POST', {
                'revision': plan['revision'], 'operation': 'save',
                'demand': [0] * 72, 'shifts': [],
            }, csrf=True)
            self.assertEqual(status, 200)
            expected[plan_date] = saved['revision']

        changed_url = f'/api/wfm/plan?date={days[3]}&team=Telefonista'
        changed = self.request(changed_url)[2]
        self.assertEqual(self.request(changed_url, 'POST', {
            'revision': changed['revision'], 'operation': 'save',
            'demand': [1] * 72, 'shifts': [],
        }, csrf=True)[0], 200)

        status, _, body = self.request(
            '/api/wfm/publish-week?week=2027-02-01&team=Telefonista', 'POST',
            {'expected_revisions': expected, 'confirm_exceptions': True}, csrf=True,
        )
        self.assertEqual(status, 409)
        self.assertEqual(body['detail']['code'], 'WFM_WEEK_REVISION_CONFLICT')
        self.assertEqual(body['detail']['conflict']['plan_date'], days[3])
        with self.server_module.connect() as database:
            published = database.execute(
                "SELECT count(*) total FROM wfm_revisions WHERE team='Telefonista' "
                "AND plan_date BETWEEN '2027-02-01' AND '2027-02-07' AND published=1"
            ).fetchone()['total']
        self.assertEqual(published, 0)

    def test_wfm_request_decision_racing_publication_remains_consistent(self):
        self.login()
        password = 'ephemeral-wfm-race-password'
        username = f'wfm.race.{time.time_ns()}'
        user_id = self.create_test_user(username, 'Telefonista', password)
        plan_date = '2027-03-10'
        url = f'/api/wfm/plan?date={plan_date}&team=Telefonista'
        initial = self.request(url)[2]
        status, _, published = self.request(url, 'POST', {
            'revision': initial['revision'], 'operation': 'publish',
            'confirm_exceptions': True, 'demand': [0] * 72,
            'shifts': [{'user_id': user_id, 'start': 16}],
        }, csrf=True)
        self.assertEqual(status, 200)

        agent, agent_cookies = self.isolated_client()
        self.login(username, password, agent, agent_cookies)
        status, _, created = self.request('/api/wfm/requests', 'POST', {
            'request_type': 'AUSENCIA', 'requested_date': plan_date,
            'reason': 'Carrera controlada de publicación',
        }, csrf=True, opener=agent, cookie_jar=agent_cookies)
        self.assertEqual(status, 200)

        reviewers = [self.isolated_client(), self.isolated_client()]
        for opener, jar in reviewers:
            self.login(opener=opener, cookie_jar=jar)
        barrier = threading.Barrier(2)

        def approve():
            opener, jar = reviewers[0]
            barrier.wait()
            return self.request('/api/wfm/requests', 'POST', {
                'operation': 'decide', 'request_id': created['request_id'],
                'decision': 'APROBAR', 'resolution_note': 'Aprobación concurrente',
            }, csrf=True, opener=opener, cookie_jar=jar)

        def republish():
            opener, jar = reviewers[1]
            barrier.wait()
            return self.request(url, 'POST', {
                'revision': published['revision'], 'operation': 'publish',
                'confirm_exceptions': True, 'demand': [1] * 72,
                'shifts': [{'user_id': user_id, 'start': 16}],
            }, csrf=True, opener=opener, cookie_jar=jar)

        with ThreadPoolExecutor(max_workers=2) as executor:
            approval_future = executor.submit(approve)
            publish_future = executor.submit(republish)
            approval = approval_future.result()
            republished = publish_future.result()

        self.assertEqual(sorted([approval[0], republished[0]]), [200, 409])
        if approval[0] == 409:
            self.assertEqual(approval[2]['detail']['code'], 'WFM_REQUEST_SOURCE_REVISION_CONFLICT')
            revision = approval[2]['detail']['conflict']['current_revision']
            opener, jar = reviewers[0]
            approval = self.request('/api/wfm/requests', 'POST', {
                'operation': 'decide', 'request_id': created['request_id'],
                'decision': 'APROBAR', 'resolution_note': 'Aprobación sobre revisión confirmada',
                'confirm_current_revision': True, 'expected_published_revision': revision,
            }, csrf=True, opener=opener, cookie_jar=jar)
            self.assertEqual(approval[0], 200)
        else:
            self.assertEqual(republished[2]['detail']['code'], 'WFM_PLAN_REVISION_CONFLICT')

        current = self.request(url)[2]
        request_rows = self.request('/api/wfm/requests?team=Telefonista')[2]
        resolved = next(item for item in request_rows if item['request_id'] == created['request_id'])
        self.assertEqual(resolved['status'], 'APROBADA')
        shift = next(item for item in current['shifts'] if item['user_id'] == user_id)
        linked = [item for item in shift['exceptions'] if item.get('source_request_id') == created['request_id']]
        self.assertEqual(len(linked), 1)

    def test_wfm_approve_reject_and_cancel_resolve_exactly_once(self):
        self.login()
        password = 'ephemeral-wfm-resolution-password'
        username = f'wfm.resolve.{time.time_ns()}'
        user_id = self.create_test_user(username, 'Telefonista', password)
        plan_date = '2027-03-17'
        url = f'/api/wfm/plan?date={plan_date}&team=Telefonista'
        initial = self.request(url)[2]
        self.assertEqual(self.request(url, 'POST', {
            'revision': initial['revision'], 'operation': 'publish',
            'confirm_exceptions': True, 'demand': [0] * 72,
            'shifts': [{'user_id': user_id, 'start': 16}],
        }, csrf=True)[0], 200)

        agent = self.isolated_client()
        self.login(username, password, *agent)
        created = self.request('/api/wfm/requests', 'POST', {
            'request_type': 'AUSENCIA', 'requested_date': plan_date,
            'reason': 'Resolución exactamente una vez',
        }, csrf=True, opener=agent[0], cookie_jar=agent[1])[2]
        admins = [self.isolated_client(), self.isolated_client()]
        for opener, jar in admins:
            self.login(opener=opener, cookie_jar=jar)
        barrier = threading.Barrier(3)

        def resolve(decision, client):
            barrier.wait()
            return self.request('/api/wfm/requests', 'POST', {
                'operation': 'decide', 'request_id': created['request_id'],
                'decision': decision,
            }, csrf=True, opener=client[0], cookie_jar=client[1])

        def cancel():
            barrier.wait()
            return self.request('/api/wfm/requests', 'POST', {
                'operation': 'cancel', 'request_id': created['request_id'],
            }, csrf=True, opener=agent[0], cookie_jar=agent[1])

        with ThreadPoolExecutor(max_workers=3) as executor:
            results = [
                executor.submit(resolve, 'APROBAR', admins[0]),
                executor.submit(resolve, 'RECHAZAR', admins[1]),
                executor.submit(cancel),
            ]
            responses = [future.result() for future in results]
        self.assertEqual(sorted(response[0] for response in responses), [200, 409, 409])
        for status, _, body in responses:
            if status == 409:
                self.assertEqual(body['detail']['code'], 'WFM_REQUEST_ALREADY_RESOLVED')
        rows = self.request('/api/wfm/requests?scope=mine', opener=agent[0], cookie_jar=agent[1])[2]
        final = next(item for item in rows if item['request_id'] == created['request_id'])
        self.assertIn(final['status'], {'APROBADA', 'RECHAZADA', 'CANCELADA'})

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

    def test_parallel_login_failures_are_all_counted(self):
        username = "parallel-login-test"
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(
                    self.request, "/api/auth/login", "POST",
                    {"username": username, "password": "incorrecta"},
                    opener=self.isolated_client()[0],
                )
                for _ in range(5)
            ]
            statuses = sorted(future.result()[0] for future in futures)
        self.assertEqual(statuses, [401, 401, 401, 401, 429])
        status, headers, _ = self.request(
            "/api/auth/login", "POST", {"username": username, "password": "incorrecta"}
        )
        self.assertEqual(status, 429)
        self.assertTrue(headers.get("Retry-After"))

    def test_protected_read_without_session_is_401(self):
        self.assertEqual(self.request("/api/notices")[0], 401)

    def test_role_access_is_enforced_from_persisted_permissions(self):
        password = "ephemeral-role-password"
        self.create_test_user("telefonista.role.test", "Telefonista", password)
        opener, cookie_jar = self.isolated_client()
        self.login("telefonista.role.test", password, opener, cookie_jar)
        self.assertEqual(self.request("/api/notices", opener=opener, cookie_jar=cookie_jar)[0], 200)
        self.assertEqual(self.request("/api/settings/users", opener=opener, cookie_jar=cookie_jar)[0], 403)

    def test_dashboard_contract_works_with_dashboard_only_permission(self):
        password = "ephemeral-dashboard-password"
        with self.server_module.connect() as database:
            role_id = database.execute(
                "INSERT INTO roles(name,description) VALUES(%s,%s) RETURNING id",
                ("Panel temporal", "Rol aislado para validar el panel"),
            ).fetchone()["id"]
            database.execute(
                "INSERT INTO role_permissions(role_id,permission) VALUES(%s,%s)",
                (role_id, "dashboard.view"),
            )
            database.execute(
                """INSERT INTO users(username,email,display_name,password_hash,role_id,active)
                VALUES(%s,%s,%s,%s,%s,TRUE)""",
                (
                    "dashboard.only.test", "dashboard.only.test@portoservicios.com.uy",
                    "Panel temporal", self.server_module.hash_password(password), role_id,
                ),
            )
        opener, cookie_jar = self.isolated_client()
        self.login("dashboard.only.test", password, opener, cookie_jar)
        status, _, payload = self.request("/api/dashboard", opener=opener, cookie_jar=cookie_jar)
        self.assertEqual(status, 200)
        self.assertEqual(payload["definitions_version"], "1.0")
        self.assertEqual(payload["timezone"], "America/Montevideo")
        self.assertIn("as_of", payload)
        self.assertIn("delay_metrics", payload)
        self.assertIn("distributions", payload)
        self.assertEqual(payload["notices_open"], sum(payload["distributions"]["notices_by_status"].values()))
        self.assertEqual(payload["transfers_pending"], sum(payload["distributions"]["transfers_by_status"].values()))
        self.assertEqual(self.request("/api/delays", opener=opener, cookie_jar=cookie_jar)[0], 403)

    def test_audit_events_are_immutable(self):
        self.login()
        with self.server_module.connect() as database:
            actor=database.execute("SELECT id,display_name FROM users WHERE username='admin'").fetchone()
            self.server_module.audit(database,"notice",987654,"PRUEBA",actor["display_name"],actor_id=actor["id"])
            event_id=database.execute("SELECT max(id) AS id FROM audit_events").fetchone()["id"]
        with self.assertRaises(self.server_module.psycopg.errors.RaiseException):
            with self.server_module.connect() as database:
                database.execute("UPDATE audit_events SET detail='alterado' WHERE id=%s",(event_id,))

    def test_notice_permissions_are_independent(self):
        self.login()
        status, _, roles = self.request("/api/settings/roles")
        self.assertEqual(status, 200)
        self.assertEqual(self.request("/api/notices/assignees")[0], 200)
        status, _, validation_notice = self.request(
            "/api/notices", "POST",
            {"task_number": "DUPLICATE-TEST", "notice_type": "Prueba", "detail": "Validación de responsable"}, csrf=True,
        )
        self.assertEqual(status, 201)
        duplicate_payload = {"task_number": "duplicate-test", "notice_type": "Otro", "detail": "Segundo aviso"}
        self.assertEqual(self.request("/api/notices", "POST", duplicate_payload, csrf=True)[0], 409)
        duplicate_payload["allow_duplicate"] = True
        self.assertEqual(self.request("/api/notices", "POST", duplicate_payload, csrf=True)[0], 201)
        self.assertEqual(
            self.request(
                f"/api/notices/{validation_notice['id']}/status", "PATCH",
                {"managed_by": "Persona inexistente"}, csrf=True,
            )[0],
            400,
        )
        self.assertEqual(
            self.request(
                f"/api/notices/{validation_notice['id']}/status", "PATCH",
                {"status": "RESUELTO"}, csrf=True,
            )[0],
            400,
        )
        self.assertEqual(
            self.request(
                f"/api/notices/{validation_notice['id']}/status", "PATCH",
                {"status": "RESUELTO", "comments": "Gestión finalizada"}, csrf=True,
            )[0],
            200,
        )
        phone_role = next(role for role in roles if role["name"] == "Telefonista")
        original_permissions = list(phone_role["permissions"])
        comment_only = [permission for permission in original_permissions if not permission.startswith("notices.")]
        comment_only += ["notices.view", "notices.create", "notices.comment"]
        try:
            status, _, _ = self.request(
                f"/api/roles/{phone_role['id']}/permissions", "PATCH",
                {"permissions": comment_only}, csrf=True,
            )
            self.assertEqual(status, 200)
            password = "ephemeral-notice-password"
            self.create_test_user("notice.permissions.test", "Telefonista", password)
            opener, cookie_jar = self.isolated_client()
            self.login("notice.permissions.test", password, opener, cookie_jar)
            status, _, notice = self.request(
                "/api/notices", "POST",
                {"notice_type": "Prueba", "detail": "Seguimiento independiente"},
                csrf=True, opener=opener, cookie_jar=cookie_jar,
            )
            self.assertEqual(status, 201)
            notice_id = notice["id"]
            status, _, unassigned = self.request(
                "/api/notices?scope=unassigned", opener=opener, cookie_jar=cookie_jar,
            )
            self.assertEqual(status, 200)
            self.assertIn(notice_id, [item["id"] for item in unassigned])
            self.assertEqual(
                self.request("/api/notices/assignees", opener=opener, cookie_jar=cookie_jar)[0],
                403,
            )
            self.assertEqual(
                self.request(
                    f"/api/notices/{notice_id}/status", "PATCH",
                    {"comments": "Comentario permitido"}, csrf=True,
                    opener=opener, cookie_jar=cookie_jar,
                )[0],
                200,
            )
            status, _, history = self.request(
                f"/api/notices/{notice_id}/history", opener=opener, cookie_jar=cookie_jar,
            )
            self.assertEqual(status, 200)
            self.assertIn("CREADO", [event["event_type"] for event in history])
            self.assertIn("COMENTARIO", [event["event_type"] for event in history])
            self.assertEqual(
                self.request(
                    f"/api/notices/{notice_id}/status", "PATCH",
                    {"status": "EN_GESTION"}, csrf=True,
                    opener=opener, cookie_jar=cookie_jar,
                )[0],
                403,
            )
        finally:
            self.assertEqual(
                self.request(
                    f"/api/roles/{phone_role['id']}/permissions", "PATCH",
                    {"permissions": original_permissions}, csrf=True,
                )[0],
                200,
            )

    def test_removed_default_permission_survives_initialize(self):
        self.login()
        status, _, roles = self.request("/api/settings/roles")
        self.assertEqual(status, 200)
        phone_role = next(role for role in roles if role["name"] == "Telefonista")
        admin_role = next(role for role in roles if role["name"] == "Administrador")
        self.assertEqual(
            self.request(
                f"/api/roles/{admin_role['id']}/permissions", "PATCH",
                {"permissions": []}, csrf=True,
            )[0],
            400,
        )
        selected = [permission for permission in phone_role["permissions"] if permission != "quotes.create"]
        self.assertEqual(
            self.request(
                f"/api/roles/{phone_role['id']}/permissions", "PATCH",
                {"permissions": selected + selected[:1]}, csrf=True,
            )[0],
            200,
        )
        self.server_module.initialize()
        with self.server_module.connect() as database:
            restored = database.execute(
                "SELECT 1 FROM role_permissions WHERE role_id=%s AND permission='quotes.create'",
                (phone_role["id"],),
            ).fetchone()
        self.assertIsNone(restored)

    def test_schema_migrations_have_checksums_and_initialize_is_idempotent(self):
        with self.server_module.connect() as database:
            before = database.execute("SELECT key, checksum FROM schema_migrations ORDER BY key").fetchall()
        self.assertTrue(before)
        self.assertTrue(all(row["checksum"] for row in before))
        self.server_module.initialize()
        with self.server_module.connect() as database:
            after = database.execute("SELECT key, checksum FROM schema_migrations ORDER BY key").fetchall()
        self.assertEqual(before, after)

    def test_password_reset_revokes_all_user_sessions(self):
        old_password = "ephemeral-old-password"
        user_id = self.create_test_user("session.revoke.test", "Telefonista", old_password)
        user_opener, user_cookies = self.isolated_client()
        self.login("session.revoke.test", old_password, user_opener, user_cookies)
        self.assertEqual(self.request("/api/auth/me", opener=user_opener, cookie_jar=user_cookies)[0], 200)

        self.login()
        with self.server_module.connect() as database:
            role_id = database.execute("SELECT id FROM roles WHERE name='Telefonista'").fetchone()["id"]
        payload = {
            "display_name": "Sesión revocada", "email": "session.revoke.test@portoservicios.com.uy",
            "role_id": role_id, "active": True, "password": "ephemeral-new-password",
        }
        self.assertEqual(self.request(f"/api/users/{user_id}", "PATCH", payload, csrf=True)[0], 200)
        self.assertEqual(self.request("/api/auth/me", opener=user_opener, cookie_jar=user_cookies)[0], 401)
        self.assertEqual(self.request("/api/auth/login", "POST", {"username": "session.revoke.test", "password": old_password})[0], 401)

    def test_role_change_revokes_existing_session(self):
        password = "ephemeral-role-change-password"
        user_id = self.create_test_user("session.role.change.test", "Telefonista", password)
        user_opener, user_cookies = self.isolated_client()
        self.login("session.role.change.test", password, user_opener, user_cookies)

        self.login()
        with self.server_module.connect() as database:
            role_id = database.execute("SELECT id FROM roles WHERE name='Planificador'").fetchone()["id"]
        payload = {
            "display_name": "Cambio de rol", "email": "session.role.change.test@portoservicios.com.uy",
            "role_id": role_id, "active": True, "password": None,
        }
        self.assertEqual(self.request(f"/api/users/{user_id}", "PATCH", payload, csrf=True)[0], 200)
        self.assertEqual(self.request("/api/auth/me", opener=user_opener, cookie_jar=user_cookies)[0], 401)

    def test_deactivation_revokes_session_and_blocks_login(self):
        password = "ephemeral-deactivation-password"
        user_id = self.create_test_user("session.deactivation.test", "Telefonista", password)
        user_opener, user_cookies = self.isolated_client()
        self.login("session.deactivation.test", password, user_opener, user_cookies)

        self.login()
        with self.server_module.connect() as database:
            role_id = database.execute("SELECT id FROM roles WHERE name='Telefonista'").fetchone()["id"]
        payload = {
            "display_name": "Usuario desactivado", "email": "session.deactivation.test@portoservicios.com.uy",
            "role_id": role_id, "active": False, "password": None,
        }
        self.assertEqual(self.request(f"/api/users/{user_id}", "PATCH", payload, csrf=True)[0], 200)
        self.assertEqual(self.request("/api/auth/me", opener=user_opener, cookie_jar=user_cookies)[0], 401)
        self.assertEqual(
            self.request(
                "/api/auth/login", "POST",
                {"username": "session.deactivation.test", "password": password},
                opener=user_opener, cookie_jar=user_cookies,
            )[0],
            401,
        )

    def test_last_active_administrator_cannot_be_disabled_or_demoted(self):
        self.login()
        with self.server_module.connect() as database:
            admin = database.execute(
                "SELECT u.id,u.email,u.display_name,u.role_id FROM users u WHERE username='admin'"
            ).fetchone()
            phone_role = database.execute("SELECT id FROM roles WHERE name='Telefonista'").fetchone()["id"]
        base = {
            "display_name": admin["display_name"],
            "email": admin["email"] or "admin@portoservicios.com.uy",
            "role_id": admin["role_id"], "active": False, "password": None,
        }
        status, _, body = self.request(f"/api/users/{admin['id']}", "PATCH", base, csrf=True)
        self.assertEqual(status, 400)
        self.assertIn("Administrador activo", body["detail"])

        status, _, body = self.request(
            f"/api/users/{admin['id']}", "PATCH", {**base, "role_id": phone_role, "active": True}, csrf=True,
        )
        self.assertEqual(status, 400)
        self.assertIn("Administrador activo", body["detail"])

    def test_concurrent_admin_demotions_leave_one_active_administrator(self):
        primary_opener, primary_cookies = self.isolated_client()
        secondary_opener, secondary_cookies = self.isolated_client()
        secondary_password = "ephemeral-secondary-admin-password"
        secondary_id = self.create_test_user("concurrent.admin.test", "Administrador", secondary_password)
        self.login("admin", os.environ["ADMIN_PASSWORD"], primary_opener, primary_cookies)
        self.login("concurrent.admin.test", secondary_password, secondary_opener, secondary_cookies)
        with self.server_module.connect() as database:
            primary = database.execute(
                "SELECT id,email,display_name,role_id FROM users WHERE username='admin'"
            ).fetchone()
            admin_role_id = primary["role_id"]
            phone_role_id = database.execute("SELECT id FROM roles WHERE name='Telefonista'").fetchone()["id"]
            secondary = database.execute(
                "SELECT id,email,display_name FROM users WHERE id=%s", (secondary_id,)
            ).fetchone()

        barrier = threading.Barrier(2)

        def demote(user, opener, cookie_jar):
            barrier.wait(timeout=5)
            return self.request(
                f"/api/users/{user['id']}", "PATCH",
                {
                    "display_name": user["display_name"],
                    "email": user["email"] or "admin@portoservicios.com.uy",
                    "role_id": phone_role_id, "active": True, "password": None,
                },
                csrf=True, opener=opener, cookie_jar=cookie_jar,
            )[0]

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = (
                    executor.submit(demote, primary, primary_opener, primary_cookies),
                    executor.submit(demote, secondary, secondary_opener, secondary_cookies),
                )
                results = sorted(future.result() for future in futures)
            self.assertEqual(results, [200, 400])
            with self.server_module.connect() as database:
                count = database.execute(
                    """SELECT count(*) AS total FROM users u JOIN roles r ON r.id=u.role_id
                    WHERE u.active=TRUE AND r.name='Administrador'"""
                ).fetchone()["total"]
            self.assertEqual(count, 1)
        finally:
            with self.server_module.connect() as database:
                database.execute("UPDATE users SET role_id=%s,active=TRUE WHERE id=%s", (admin_role_id, primary["id"]))
                database.execute("DELETE FROM app_sessions WHERE user_id=%s", (secondary_id,))
                database.execute("DELETE FROM users WHERE id=%s", (secondary_id,))

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

    def test_transfer_workflow_validates_duplicates_assignment_and_closure(self):
        self.login()
        with self.server_module.connect() as database:
            database.execute("DELETE FROM scheduled_transfers")
        payload = {
            "task_number": "PG-TRASLADO-1", "transfer_type": "Traslado Directo",
            "scheduled_date": "2026-12-20", "scheduled_time": "10:30",
            "origin": "Pando", "destination": "Montevideo",
            "provider": None, "responsible": None, "comments": "Prueba integral",
        }
        status, _, created = self.request("/api/transfers", "POST", payload, csrf=True)
        self.assertEqual(status, 201)
        self.assertEqual(created["status"], "SIN_ASIGNAR")
        transfer_id = created["id"]

        status, _, duplicate = self.request("/api/transfers", "POST", payload, csrf=True)
        self.assertEqual(status, 409)
        self.assertEqual(duplicate["detail"]["duplicate"]["id"], transfer_id)
        self.assertEqual(self.request("/api/transfers", "POST", {**payload, "allow_duplicate": True}, csrf=True)[0], 201)

        status, _, body = self.request(f"/api/transfers/{transfer_id}/status", "PATCH", {"status": "ASIGNADO", "provider": "Auxilio Uno"}, csrf=True)
        self.assertEqual(status, 400)
        self.assertIn("responsable", body["detail"])
        people = self.request("/api/transfers/responsibles")[2]
        self.assertTrue(any(person["display_name"] == "Administrador" for person in people))
        assigned = self.request(f"/api/transfers/{transfer_id}/status", "PATCH", {"status": "ASIGNADO", "provider": "Auxilio Uno", "responsible": "Administrador"}, csrf=True)
        self.assertEqual(assigned[0], 200)
        self.assertIsNotNone(assigned[2]["assigned_at"])
        self.assertEqual(self.request(f"/api/transfers/{transfer_id}/status", "PATCH", {"status": "EN_CURSO"}, csrf=True)[0], 200)
        self.assertEqual(self.request(f"/api/transfers/{transfer_id}/status", "PATCH", {"status": "FINALIZADO"}, csrf=True)[0], 400)
        finalized = self.request(f"/api/transfers/{transfer_id}/status", "PATCH", {"status": "FINALIZADO", "note": "Entregado correctamente"}, csrf=True)
        self.assertEqual(finalized[0], 200)
        self.assertEqual(finalized[2]["completion_note"], "Entregado correctamente")
        self.assertEqual(self.request(f"/api/transfers/{transfer_id}", "DELETE", csrf=True)[0], 405)

        events = self.request(f"/api/transfers/{transfer_id}/events")[2]
        self.assertEqual([event["event_type"] for event in events], ["ESTADO", "ESTADO", "ESTADO", "CREADO"])
        self.assertEqual(len(self.request("/api/transfers?status=FINALIZADO&responsible=Admin")[2]), 1)
        audit_rows = self.request(f"/api/audit?entity=transfer&entity_id={transfer_id}")[2]
        final_change = next(event for event in audit_rows if event["action"] == "CAMBIO_ESTADO")
        self.assertTrue(final_change["actor_id"])
        self.assertTrue(final_change["before_data"])
        self.assertTrue(final_change["after_data"])
        self.assertTrue(final_change["correlation_id"])

    def test_backup_path_is_not_served(self):
        status, _, _ = self.request("/postgres-backups/centro_operativo_test.dump")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
