import json
import hashlib
import sqlite3
import threading
import unittest
from contextlib import closing
from http.client import RemoteDisconnected
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
        cls.test_directory = TemporaryDirectory(prefix="libro-trabajo-quotes-")
        cls.test_db = Path(cls.test_directory.name) / "quote_test.db"
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
        cls.test_directory.cleanup()

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
        self.assertEqual(result["pricing_snapshot"]["coverage"], "insured")
        self.assertEqual(result["pricing_snapshot"]["extra_rate"], 120)

    def test_manual_distance_has_the_same_upper_bound_as_postgres(self):
        status, error = self.request_error(
            "/api/quotes/calculate",
            "POST",
            {"manual_distance": True, "manual_trip_km": 1_000_001},
            authenticated=True,
        )
        self.assertEqual(status, 400)
        self.assertIn("1.000.000", error["detail"])

    def test_quote_rounding_uses_half_up_and_exact_extra_boundary(self):
        self.assertEqual(local_server.round_currency("1.005"), 1.01)
        self.assertEqual(local_server.round_distance("12.345"), 12.35)
        self.assertEqual(local_server.calculate_extra_km("25.00", "25.00"), 0)
        self.assertEqual(local_server.calculate_extra_km("25.01", "25.00"), 1)

    def test_quote_rule_values_reject_non_finite_and_out_of_range_values(self):
        with self.assertRaises(ValueError):
            local_server.validate_quote_rule_values(["insured_base"], [float("nan")])
        with self.assertRaises(ValueError):
            local_server.validate_quote_rule_values(["included_km"], [1_000_001])

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

    def test_automatic_route_counts_the_same_toll_on_both_segments(self):
        with local_server.connect() as database:
            database.execute(
                "INSERT INTO toll_catalog(name,latitude,longitude,price,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                ("Peaje doble sintético", -34.0, -56.0, 500, 1, local_server.now(), local_server.now()),
            )
        routes = [
            {"km": 10, "coordinates": [[-56.01, -34.0], [-55.99, -34.0]]},
            {"km": 27, "coordinates": [[-56.02, -34.0], [-55.98, -34.0]]},
        ]
        with patch.object(local_server, "route_data", side_effect=routes):
            result = self.request(
                "/api/quotes/calculate",
                "POST",
                {
                    "origin": "-34.0000, -56.0000",
                    "destination": "-34.0100, -56.0100",
                    "mobile_origin": "-34.0200, -56.0200",
                    "include_mobile": True,
                    "uninsured": False,
                },
                authenticated=True,
            )
        self.assertEqual(result["mode"], "automatic")
        self.assertEqual(result["toll_count"], 2)
        self.assertEqual(result["toll_price"], 1000)
        self.assertEqual([item["segment"] for item in result["toll_details"]], [
            "Traslado: origen → destino",
            "Salida de la grúa → origen del cliente",
        ])

    def test_automatic_route_failure_is_a_recoverable_manual_contingency(self):
        before = len(self.request("/api/quotes", authenticated=True))
        with patch.object(local_server, "route_data", side_effect=ValueError("No se pudo calcular la ruta automáticamente. Use la distancia manual.")):
            status, error = self.request_error(
                "/api/quotes/calculate",
                "POST",
                {
                    "origin": "-34.0000, -56.0000",
                    "destination": "-34.0100, -56.0100",
                    "uninsured": False,
                },
                authenticated=True,
            )
        self.assertEqual(status, 400)
        self.assertIn("distancia manual", error["detail"])
        self.assertEqual(len(self.request("/api/quotes", authenticated=True)), before)

    def test_uruguayan_segments_are_summed_without_changing_rates(self):
        routes = [
            {"km": 12.5, "coordinates": [[-56.17, -34.90], [-56.16, -34.89]]},
            {"km": 8.25, "coordinates": [[-56.15, -34.88], [-56.17, -34.90]]},
        ]
        with patch.object(local_server, "route_data", side_effect=routes):
            quote = self.request("/api/quotes/calculate", "POST", {
                "origin": "-34.9000, -56.1700", "destination": "-34.8900, -56.1600",
                "mobile_origin": "-34.8800, -56.1500", "include_mobile": True,
            }, authenticated=True)
        self.assertEqual(quote["trip_km"], 12.5)
        self.assertEqual(quote["mobile_km"], 8.25)
        self.assertEqual(quote["total_km"], 20.75)
        self.assertEqual([segment["label"] for segment in quote["route_segments"]], [
            "Traslado: origen → destino", "Salida de la grúa → origen del cliente",
        ])

    def test_regional_endpoint_and_cross_border_route_do_not_create_price(self):
        before = len(self.request("/api/quotes", authenticated=True))
        with patch.object(local_server, "route_data") as routing:
            status, error = self.request_error("/api/quotes/calculate", "POST", {
                "origin": "-34.6037, -58.3816", "destination": "-34.9011, -56.1645",
            }, authenticated=True)
            routing.assert_not_called()
        self.assertEqual(status, 400)
        self.assertIn("tarifa regional", error["detail"])
        with patch.object(local_server, "route_data", return_value={"km": 10, "coordinates": [[-56.1645, -34.9011], [-58.3816, -34.6037], [-56.1645, -34.9011]]}):
            status, error = self.request_error("/api/quotes/calculate", "POST", {
                "origin": "-34.9011, -56.1645", "destination": "-34.9011, -56.1645",
            }, authenticated=True)
        self.assertEqual(status, 400)
        self.assertIn("tarifa regional", error["detail"])
        self.assertEqual(len(self.request("/api/quotes", authenticated=True)), before)

    def test_capture_point_is_rejected_before_osrm_route_and_not_saved(self):
        before = len(self.request("/api/quotes", authenticated=True))
        road = {"distance": 3474.786778, "location": [-58.356012, -33.957245]}
        with patch.object(local_server, "nearest_road", return_value=road), patch.object(local_server, "route_data") as routing:
            status, error = self.request_error("/api/quotes/calculate", "POST", {
                "origin": "-34.813803, -55.238921", "destination": "-33.979809, -58.382095", "include_mobile": False,
            }, authenticated=True)
            routing.assert_not_called()
        self.assertEqual(status, 400)
        self.assertIn("Destino: ubicación en agua o sin vía cercana", error["detail"])
        self.assertEqual(len(self.request("/api/quotes", authenticated=True)), before)

    def test_manual_quote_with_known_brazilian_point_is_rejected(self):
        status, error = self.request_error("/api/quotes/calculate", "POST", {
            "manual_distance": True, "manual_trip_km": 20,
            "manual_region_points": ["-23.5505, -46.6333"],
        }, authenticated=True)
        self.assertEqual(status, 400)
        self.assertIn("tarifa regional", error["detail"])

    def test_geocoding_returns_distinct_synthetic_suggestions_without_external_calls(self):
        suggestions = [
            {"label": "San Martín 100, Buenos Aires, Buenos Aires, Argentina", "latitude": -34.6, "longitude": -58.4, "country_code": "AR"},
            {"label": "San Martín 100, Rosario, Santa Fe, Argentina", "latitude": -32.9, "longitude": -60.7, "country_code": "AR"},
        ]
        with patch.object(local_server, "search_address", return_value=suggestions) as geocode:
            result = self.request("/api/quotes/geocode?q=San%20Mart%C3%ADn%20100", authenticated=True)
        geocode.assert_called_once_with("San Martín 100", None)
        self.assertEqual(result, suggestions)

    def test_country_filter_and_coordinate_preview_require_quotes_permission(self):
        with patch.object(local_server, "search_address", return_value=[]) as geocode:
            self.assertEqual(self.request("/api/quotes/geocode?q=18%20de%20Julio%20y%20Ejido&country=UY", authenticated=True), [])
        geocode.assert_called_once_with("18 de Julio y Ejido", "UY")
        point = self.request("/api/quotes/resolve-location?q=-33.979809%2C%20-58.382095", authenticated=True)
        self.assertEqual((point["latitude"], point["longitude"]), (-33.979809, -58.382095))
        self.assertFalse(point["inside_uruguay"])

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
        self.assertIn("pricing_snapshot", history[0])

    def test_quote_history_returns_complete_filtered_list(self):
        history = self.request("/api/quotes/history?mode=manual", authenticated=True)
        self.assertIsInstance(history, list)
        self.assertGreaterEqual(len(history), 1)
        self.assertTrue(all(row["origin_input"] == "Cotización manual" for row in history))

    def test_historical_price_is_unchanged_after_rule_update(self):
        payload = {"manual_distance": True, "manual_trip_km": 27, "uninsured": False}
        first = self.request("/api/quotes/calculate", "POST", payload, authenticated=True)
        with local_server.connect() as database:
            original = database.execute("SELECT insured_base FROM quote_rules WHERE id=1").fetchone()[0]
        try:
            with local_server.connect() as database:
                database.execute("UPDATE quote_rules SET insured_base=? WHERE id=1", (original + 100,))
            historical = next(row for row in self.request("/api/quotes/history", authenticated=True) if row["id"] == first["id"])
            self.assertEqual(historical["total_price"], first["total_price"])
            self.assertEqual(json.loads(historical["pricing_snapshot"])["base_price"], first["base_price"])
            second = self.request("/api/quotes/calculate", "POST", payload, authenticated=True)
            self.assertNotEqual(second["id"], first["id"])
            self.assertEqual(second["total_price"], first["total_price"] + 100)
        finally:
            with local_server.connect() as database:
                database.execute("UPDATE quote_rules SET insured_base=? WHERE id=1", (original,))

    def test_lost_response_after_save_does_not_trigger_another_write(self):
        with local_server.connect() as database:
            before = database.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]
        with patch.object(self.server, "handle_error"), patch.object(local_server.Handler, "send_json", side_effect=ConnectionAbortedError("respuesta perdida")):
            with self.assertRaises(RemoteDisconnected):
                self.request(
                    "/api/quotes/calculate", "POST",
                    {"manual_distance": True, "manual_trip_km": 11, "task_number": "respuesta-perdida-sintética"},
                    authenticated=True,
                )
        with local_server.connect() as database:
            saved = database.execute("SELECT COUNT(*) FROM quotes WHERE task_number=?", ("respuesta-perdida-sintética",)).fetchone()[0]
            after = database.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]
        self.assertEqual(saved, 1)
        self.assertEqual(after, before + 1)

    def test_catalog_change_preserves_historical_toll_passes(self):
        with local_server.connect() as database:
            toll_id = database.execute(
                "INSERT INTO toll_catalog(name,latitude,longitude,price,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                ("Peaje histórico sintético", -33.8, -56.2, 123, 1, local_server.now(), local_server.now()),
            ).lastrowid
        payload = {"origin": "-33.8, -56.21", "destination": "-33.8, -56.19"}
        route = {"km": 10, "coordinates": [[-56.21, -33.8], [-56.19, -33.8]]}
        with patch.object(local_server, "route_data", return_value=route):
            first = self.request("/api/quotes/calculate", "POST", payload, authenticated=True)
            with local_server.connect() as database:
                database.execute("UPDATE toll_catalog SET price=321 WHERE id=?", (toll_id,))
            second = self.request("/api/quotes/calculate", "POST", payload, authenticated=True)
        historical = next(row for row in self.request("/api/quotes/history", authenticated=True) if row["id"] == first["id"])
        self.assertEqual(first["toll_price"], 123)
        self.assertEqual(second["toll_price"], 321)
        self.assertEqual(historical["toll_price"], 123)
        self.assertEqual(json.loads(historical["toll_details"])[0]["price"], 123)

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

    def test_schema_migrations_have_checksums_and_initialize_is_idempotent(self):
        with local_server.connect() as database:
            before = database.execute("SELECT key, checksum FROM schema_migrations ORDER BY key").fetchall()
        self.assertTrue(before)
        self.assertTrue(all(row["checksum"] for row in before))
        local_server.initialize()
        with local_server.connect() as database:
            after = database.execute("SELECT key, checksum FROM schema_migrations ORDER BY key").fetchall()
        self.assertEqual([(row["key"], row["checksum"]) for row in before], [(row["key"], row["checksum"]) for row in after])


    def test_delay_takes_precedence_and_normalization_keeps_evidence(self):
        standard = self.request(
            "/api/settings/standards",
            "POST",
            {
                "department": "SALTO",
                "zone": "Zona fase uno",
                "service": "ML",
                "minutes_min": 30,
                "minutes_max": 45,
                "status": "CONFIRMADO",
                "source": "Acuerdo de prueba",
                "effective_from": "2026-09-11",
                "review_due_at": "2026-12-11",
            },
            authenticated=True,
        )
        self.assertEqual(standard["status"], "CONFIRMADO")
        delay = self.request(
            "/api/delays",
            "POST",
            {
                "service": "ML",
                "department": "SALTO",
                "zone": "Zona fase uno",
                "message": "Margen de",
                "minutes": 90,
                "status": "VIGENTE",
            },
            authenticated=True,
        )
        status, detail = self.request_error(
            "/api/delays",
            "POST",
            {
                "service": "ML", "department": "SALTO", "zone": "Zona fase uno",
                "message": "A confirmar", "status": "VIGENTE",
            },
            authenticated=True,
        )
        self.assertEqual(status, 409)
        self.assertIn("demora vigente", detail["detail"])
        guidance = self.request("/api/arrival-guidance?department=SALTO&service=ML&zone=Zona%20fase%20uno")
        self.assertEqual(guidance["precedence"], "ACTIVE_DELAY")
        self.assertEqual(guidance["active_delays"][0]["id"], delay["id"])
        closed = self.request(
            f"/api/delays/{delay['id']}/normalize",
            "PATCH",
            {"status": "NORMALIZADO", "resolution_note": "Prestador confirmó disponibilidad"},
            authenticated=True,
        )
        self.assertEqual(closed["normalized_by"], "Administrador")
        self.assertEqual(closed["resolution_note"], "Prestador confirmó disponibilidad")
        guidance = self.request("/api/arrival-guidance?department=SALTO&service=ML&zone=Zona%20fase%20uno")
        self.assertEqual(guidance["precedence"], "STANDARD")
        self.assertEqual(guidance["standards"][0]["id"], standard["id"])

    def test_expired_delay_requires_review_before_it_is_communicated(self):
        delay=self.request(
            "/api/delays","POST",
            {"service":"GRÚA","department":"ROCHA","zone":"Zona revisión","message":"A confirmar","status":"VIGENTE","review_minutes":15},
            authenticated=True,
        )
        with local_server.connect() as database:
            database.execute("UPDATE delay_zones SET expires_at=?,next_review_at=? WHERE id=?",("2020-01-01T00:00:00+00:00","2020-01-01T00:00:00+00:00",delay["id"]))
        guidance=self.request("/api/arrival-guidance?department=ROCHA&service=GR%C3%9AA&zone=Zona%20revisi%C3%B3n")
        self.assertEqual(guidance["precedence"],"REVIEW_REQUIRED")
        self.assertFalse(guidance["active_delays"])
        verified=self.request(
            f"/api/delays/{delay['id']}/verify","PATCH",
            {"review_minutes":60,"verification_note":"Prestador ratificó la demora"},
            authenticated=True,
        )
        self.assertTrue(verified["is_current"])
        guidance=self.request("/api/arrival-guidance?department=ROCHA&service=GR%C3%9AA&zone=Zona%20revisi%C3%B3n")
        self.assertEqual(guidance["precedence"],"ACTIVE_DELAY")

    def test_zone_catalog_coverage_and_delay_metrics_are_exposed(self):
        standard=self.request(
            "/api/settings/standards","POST",
            {"department":"ARTIGAS","zone":"Centro, Barrio Norte","service":"SINIESTROS",
             "status":"PROVISIONAL","owner":"Mesa Interior","review_interval_days":45,
             "effective_from":"2026-09-11","source":"Prueba de catálogo"},
            authenticated=True,
        )
        self.assertEqual(standard["owner"],"Mesa Interior")
        self.assertEqual(standard["review_interval_days"],45)
        zones=self.request("/api/zones?department=ARTIGAS")
        self.assertTrue({"Centro","Barrio Norte"}.issubset({item["name"] for item in zones}))
        coverage=self.request("/api/settings/standards-coverage")
        siniestros=next(item for item in coverage if item["department"]=="ARTIGAS" and item["service"]=="SINIESTROS")
        self.assertEqual(siniestros["references"],1)
        self.assertEqual(siniestros["coverage"],"PENDING")
        metrics=self.request("/api/delay-metrics")
        self.assertIn("verification_events",metrics)
        self.assertIn("average_resolution_minutes",metrics)

    def test_standard_proposal_approval_versions_and_zone_coverage(self):
        zone=self.request(
            "/api/settings/zones","POST",
            {"department":"FLORIDA","name":"Zona flujo aprobación","owner":"Supervisión Interior","expected_services":["ML","GRÚA"]},
            authenticated=True,
        )
        self.assertEqual(zone["expected_services"],["GRÚA","ML"])
        proposal=self.request(
            "/api/standards/proposals","POST",
            {"department":"FLORIDA","zone":"Zona flujo aprobación","service":"ML","minutes_max":55,
             "status":"CONFIRMADO","source":"Medición controlada","owner":"Supervisión Interior",
             "review_interval_days":60,"effective_from":"2026-09-11"},
            authenticated=True,
        )
        self.assertEqual(proposal["approval_status"],"PENDING")
        self.assertFalse(proposal["is_usable"])
        alerts=self.request("/api/operational-alerts")
        self.assertTrue(any(item["kind"]=="STANDARD_APPROVAL" and item["entity_id"]==proposal["id"] for item in alerts))
        guidance=self.request("/api/arrival-guidance?department=FLORIDA&service=ML&zone=Zona%20flujo%20aprobaci%C3%B3n")
        self.assertEqual(guidance["precedence"],"NO_CONFIRMED_REFERENCE")
        approved=self.request(
            f"/api/settings/standards/{proposal['id']}/decision","PATCH",
            {"decision":"APPROVED","note":"Fuente y alcance validados"},authenticated=True,
        )
        self.assertEqual(approved["approval_status"],"APPROVED")
        self.assertTrue(approved["is_usable"])
        versions=self.request(f"/api/settings/standards/{proposal['id']}/versions")
        self.assertEqual([item["action"] for item in versions[:2]],["APPROVED","SUBMITTED"])
        coverage=self.request("/api/zones-coverage?department=FLORIDA")
        ml=next(item for item in coverage if item["zone_id"]==zone["id"] and item["service"]=="ML")
        grua=next(item for item in coverage if item["zone_id"]==zone["id"] and item["service"]=="GRÚA")
        self.assertEqual(ml["coverage"],"CURRENT")
        self.assertEqual(grua["coverage"],"PENDING")

    def test_delay_event_history_is_queryable(self):
        delay=self.request(
            "/api/delays","POST",
            {"service":"SINIESTROS","department":"DURAZNO","zone":"Zona historial eventos","message":"A confirmar","status":"VIGENTE","review_minutes":60},
            authenticated=True,
        )
        self.request(f"/api/delays/{delay['id']}/verify","PATCH",{"review_minutes":90,"verification_note":"Confirmación de prueba"},authenticated=True)
        events=self.request(f"/api/delays/{delay['id']}/events")
        self.assertEqual([item["event_type"] for item in events[:2]],["VERIFICADO","CREADO"])


if __name__ == "__main__":
    unittest.main()
