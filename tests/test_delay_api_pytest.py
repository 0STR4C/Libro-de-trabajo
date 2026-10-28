"""Contrato HTTP de demoras en PostgreSQL aislado; ejecutar con Pytest."""

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from zoneinfo import ZoneInfo

import pytest


pytestmark = pytest.mark.skipif(
    not os.getenv("SECURITY_TEST_DATABASE_URL"),
    reason="requiere PostgreSQL temporal de tools/postgres_test_db",
)


def _request(client, path, method="GET", body=None, csrf=False):
    opener, cookies, base = client
    headers = {"Content-Type": "application/json"}
    if csrf:
        token = next((cookie.value for cookie in cookies if cookie.name == "centro_csrf"), "")
        headers["X-CSRF-Token"] = token
    request = Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers=headers,
    )
    try:
        with opener.open(request, timeout=5) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except HTTPError as error:
        return error.code, json.loads(error.read())


@pytest.fixture(scope="module")
def delay_client():
    os.environ["DATABASE_URL"] = os.environ["SECURITY_TEST_DATABASE_URL"]
    os.environ.setdefault("APP_ENV", "development")
    if not os.environ.get("APP_SECRET") or not os.environ.get("ADMIN_PASSWORD"):
        pytest.skip("faltan las variables del entorno aislado de pruebas")
    import uvicorn
    from app import postgres_server

    postgres_server.initialize()
    server = uvicorn.Server(uvicorn.Config(postgres_server.app, host="127.0.0.1", port=18766, log_level="critical"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    client = (build_opener(HTTPCookieProcessor(cookies := CookieJar())), cookies, "http://127.0.0.1:18766")
    try:
        for _ in range(60):
            try:
                status, _ = _request(client, "/health")
                if status == 200:
                    break
            except Exception:
                time.sleep(0.1)
        else:
            raise AssertionError("No inició el servidor PostgreSQL temporal")
        status, _ = _request(client, "/api/auth/login", "POST", {
            "username": "admin", "password": os.environ["ADMIN_PASSWORD"],
        })
        assert status == 200
        yield client, postgres_server
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_delays_endpoint_paginates_with_exact_contract(delay_client):
    client, server = delay_client
    now = datetime.now(timezone.utc)
    marker = "PYTEST_DELAY_PAGE_2026"
    with server.connect() as database:
        for number in range(12):
            department, zone = ("MONTEVIDEO", "Pocitos") if number % 2 == 0 else ("CANELONES", "Pando")
            database.execute(
                """INSERT INTO delay_zones(service,department,zone,message,status,agent,created_at,
                    normalized_at,next_review_at,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                ("GRÚA", department, zone, "A confirmar", "NORMALIZADO", marker,
                 now - timedelta(minutes=number), now, now, now),
            )
    status, page = _request(client, f"/api/delays?limit=7&offset=0&q={marker}")
    assert status == 200
    assert set(page) == {"items", "total", "limit", "offset"}
    assert (page["total"], page["limit"], page["offset"], len(page["items"])) == (12, 7, 0, 7)
    status, second = _request(client, f"/api/delays?limit=7&offset=7&q={marker}")
    assert status == 200
    assert (second["total"], second["offset"], len(second["items"])) == (12, 7, 5)
    assert set(item["id"] for item in page["items"]).isdisjoint(item["id"] for item in second["items"])
    status, filtered = _request(client, f"/api/delays?department=CANELONES&status=NORMALIZADO&q={marker}")
    assert status == 200 and filtered["total"] == 6
    status, _ = _request(client, "/api/delays?limit=51")
    assert status == 422


def test_next_review_is_computed_from_duration_minutes(delay_client):
    client, _ = delay_client
    status, item = _request(client, "/api/delays", "POST", {
        "service": "ML", "department": "ARTIGAS", "zone": "Baltasar Brum",
        "catalog_zone": True, "message": "A confirmar", "status": "VIGENTE",
        "duration_minutes": 30, "review_minutes": 120,
    }, csrf=True)
    assert status == 201, item
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    due = datetime.fromisoformat(item["next_review_at"].replace("Z", "+00:00"))
    assert item["duration_minutes"] == 30
    assert abs((due - created).total_seconds() - 30 * 60) < 3
    assert item["review_due_at"] == item["next_review_at"]
    assert item["is_current"] is True


def test_normalize_without_note_is_immediate_and_audited(delay_client):
    client, server = delay_client
    status, item = _request(client, "/api/delays", "POST", {
        "service": "ML", "department": "ROCHA", "zone": "Chuy",
        "catalog_zone": True, "message": "Margen de", "minutes": 45,
    }, csrf=True)
    assert status == 201, item
    status, closed = _request(client, f"/api/delays/{item['id']}/normalize", "PATCH", {
        "expected_revision": item["revision"],
    }, csrf=True)
    assert status == 200, closed
    assert closed["status"] == "NORMALIZADO" and closed["resolution_note"] is None
    assert closed["normalized_at"] and closed["normalized_by"]
    assert closed["revision"] == item["revision"] + 1
    status, again = _request(client, f"/api/delays/{item['id']}/normalize", "PATCH", {
        "expected_revision": item["revision"],
    }, csrf=True)
    assert status == 409, again
    with server.connect() as database:
        events = database.execute(
            "SELECT event_type,note FROM delay_events WHERE delay_id=%s ORDER BY id", (item["id"],)
        ).fetchall()
        audit = database.execute(
            "SELECT action,actor_id FROM audit_events WHERE entity='delay' AND entity_id=%s ORDER BY id", (item["id"],)
        ).fetchall()
    assert [event["event_type"] for event in events] == ["CREADO", "NORMALIZADO"]
    assert events[-1]["note"] is None
    assert audit[-1]["action"] == "NORMALIZADO" and audit[-1]["actor_id"]


def test_map_keeps_overlapping_exceptions_separate_through_normalization(delay_client):
    client, server = delay_client
    created = []
    for service, zone, message, minutes in (
        ("TODAS", "Todo el departamento", "No confirmar tiempos", None),
        ("ML", "Vergara", "Margen de", 25),
        ("GRÚA", "Vergara", "A confirmar", None),
    ):
        status, item = _request(client, "/api/delays", "POST", {
            "service": service, "department": "TREINTA Y TRES", "zone": zone,
            "catalog_zone": True, "message": message, "minutes": minutes,
            "duration_minutes": 30, "status": "VIGENTE",
        }, csrf=True)
        assert status == 201, item
        created.append(item)
    general, specific, other_service = created
    standard_path = "/api/arrival-times/resolve?service=ML&department=TREINTA%20Y%20TRES&zone=Vergara"
    status, standard = _request(client, standard_path)
    assert status == 200 and standard["status"] == "not_configured"
    assert standard["base_estimated_minutes"] is None
    status, duplicate = _request(client, "/api/delays", "POST", {
        "service": "ML", "department": "TREINTA Y TRES", "zone": "Vergara",
        "catalog_zone": True, "message": "A confirmar", "status": "VIGENTE",
    }, csrf=True)
    assert status == 409, duplicate
    from app.delay_map_stats import map_delay_stats
    with server.connect() as database:
        snapshot = map_delay_stats(database)
    department = next(row for row in snapshot["departments"] if row["department"] == "TREINTA Y TRES")
    by_id = {row["id"]: row for row in department["delays"]}
    assert specific["id"] in by_id[general["id"]]["overlap_ids"]
    assert other_service["id"] in by_id[general["id"]]["overlap_ids"]
    assert other_service["id"] not in by_id[specific["id"]]["overlap_ids"]
    assert by_id[specific["id"]]["minutes_meaning"] == "margin_unspecified"
    assert by_id[specific["id"]]["minutes"] == 25
    assert all(by_id[row["id"]]["status"] == "VIGENTE" for row in created)
    with server.connect() as database:
        overdue = datetime.now(timezone.utc) - timedelta(minutes=1)
        database.execute("UPDATE delay_zones SET next_review_at=%s WHERE id=%s", (overdue, specific["id"]))
    with server.connect() as database:
        snapshot = map_delay_stats(database)
    department = next(row for row in snapshot["departments"] if row["department"] == "TREINTA Y TRES")
    assert next(row for row in department["delays"] if row["id"] == specific["id"])["needs_review"] is True
    status, normalized = _request(client, f"/api/delays/{specific['id']}/normalize", "PATCH", {
        "expected_revision": specific["revision"], "status": "NORMALIZADO",
        "resolution_note": "Situación sintética restablecida",
    }, csrf=True)
    assert status == 200, normalized
    with server.connect() as database:
        snapshot = map_delay_stats(database)
        events = database.execute("SELECT event_type FROM delay_events WHERE delay_id=%s ORDER BY id", (specific["id"],)).fetchall()
    department = next(row for row in snapshot["departments"] if row["department"] == "TREINTA Y TRES")
    assert specific["id"] not in {row["id"] for row in department["delays"]}
    assert {general["id"], other_service["id"]}.issubset({row["id"] for row in department["delays"]})
    assert [row["event_type"] for row in events] == ["CREADO", "NORMALIZADO"]
    status, standard_after = _request(client, standard_path)
    assert status == 200 and standard_after == standard


def test_delay_lifecycle_never_creates_or_changes_notices(delay_client):
    client, server = delay_client
    from app.delay_review_worker import run_once
    with server.connect() as database:
        before = database.execute("SELECT count(*) n FROM notices").fetchone()["n"]
    status, notice_before = _request(client, "/api/notices/page")
    assert status == 200
    status, item = _request(client, "/api/delays", "POST", {
        "service": "ML", "department": "TREINTA Y TRES", "zone": "General Enrique Martínez",
        "catalog_zone": True, "message": "No confirmar tiempos", "status": "VIGENTE",
    }, csrf=True)
    assert status == 201, item
    status, verified = _request(client, f"/api/delays/{item['id']}/verify", "PATCH", {
        "expected_revision": item["revision"], "review_minutes": 30,
        "verification_note": "Sigue la afectación sintética",
    }, csrf=True)
    assert status == 200, verified
    with server.connect() as database:
        due = datetime.now(timezone.utc) - timedelta(minutes=1)
        database.execute("UPDATE delay_zones SET next_review_at=%s WHERE id=%s", (due, item["id"]))
        assert run_once(database, due) == 0
    status, review = _request(client, "/api/dashboard/map-stats")
    assert status == 200
    department = next(row for row in review["departments"] if row["department"] == "TREINTA Y TRES")
    assert next(row for row in department["delays"] if row["id"] == item["id"])["needs_review"] is True
    status, normalized = _request(client, f"/api/delays/{item['id']}/normalize", "PATCH", {
        "expected_revision": verified["revision"], "status": "NORMALIZADO",
        "resolution_note": "Situación sintética normalizada",
    }, csrf=True)
    assert status == 200, normalized
    with server.connect() as database:
        assert database.execute("SELECT count(*) n FROM notices").fetchone()["n"] == before
        events = database.execute("SELECT event_type,actor FROM delay_events WHERE delay_id=%s ORDER BY id", (item["id"],)).fetchall()
        assert [event["event_type"] for event in events] == ["CREADO", "VERIFICADO", "NORMALIZADO"]
        assert all(event["actor"] for event in events)
    status, notice_after = _request(client, "/api/notices/page")
    assert status == 200
    assert notice_after["total"] == notice_before["total"]
    assert notice_after["counts"] == notice_before["counts"]


def test_delay_indications_keep_maximum_interval_and_distinct_instructions(delay_client):
    client, server = delay_client
    from app.delays import clean_delay
    base = {"service": "GRÚA", "department": "ROCHA", "zone": "La Paloma", "catalog_zone": True}
    for message, fields in (
        ("No confirmar tiempos", {}),
        ("A confirmar", {}),
        ("No generar servicio", {}),
        ("Margen de", {"minutes": 25}),
        ("Máximo de", {"minutes": 90}),
        ("Intervalo estimado", {"minutes_min": 60, "minutes_max": 90}),
        ("Otra indicación", {"instruction_text": "Confirmar con Planificación antes de informar"}),
    ):
        cleaned = clean_delay({**base, "message": message, **fields})
        assert cleaned["message"] == message
        for field, value in fields.items():
            assert cleaned[field] == value
    for payload in (
        {"message": "Intervalo estimado", "minutes_min": 90, "minutes_max": 60},
        {"message": "Intervalo estimado", "minutes_min": 60},
        {"message": "No confirmar tiempos", "minutes": 30},
        {"message": "No generar servicio", "minutes": 30},
        {"message": "Otra indicación", "instruction_text": " "},
        {"message": "Margen de", "minutes": 25, "minutes_max": 90},
        {"message": "A confirmar", "zone": "Todo el departamento, La Paloma"},
    ):
        with pytest.raises(ValueError):
            clean_delay({**base, **payload})
    status, item = _request(client, "/api/delays", "POST", {
        "service": "SINIESTROS", "department": "TREINTA Y TRES",
        "zone": "Vergara, Santa Clara de Olimar", "catalog_zone": True,
        "message": "Intervalo estimado", "minutes_min": 60, "minutes_max": 90,
    }, csrf=True)
    assert status == 201, item
    assert (item["zone"], item["minutes"], item["minutes_min"], item["minutes_max"]) == (
        "Vergara, Santa Clara de Olimar", None, 60, 90)
    with server.connect() as database:
        assert database.execute("SELECT count(*) n FROM notices WHERE source_delay_id=%s", (item["id"],)).fetchone()["n"] == 0
    status, snapshot = _request(client, "/api/dashboard/map-stats")
    assert status == 200
    department = next(row for row in snapshot["departments"] if row["department"] == "TREINTA Y TRES")
    mapped = next(row for row in department["delays"] if row["id"] == item["id"])
    assert (mapped["minutes_min"], mapped["minutes_max"]) == (60, 90)
    status, _ = _request(client, "/api/notices", "POST", {
        "notice_type": "REVISIÓN DE DEMORA", "detail": "No debe crearse",
    }, csrf=True)
    assert status == 422


def test_delay_rejects_a_second_save_from_an_old_version(delay_client):
    client, server = delay_client
    stamp = datetime.now(timezone.utc)
    with server.connect() as database:
        item = database.execute(
            """INSERT INTO delay_zones(service,department,zone,message,status,agent,created_at,
                   next_review_at,expires_at)
               VALUES('GRÚA','FLORES','Trinidad','A confirmar','VIGENTE','Prueba de concurrencia',%s,%s,%s)
               RETURNING id,revision""",
            (stamp, stamp + timedelta(hours=2), stamp + timedelta(hours=2)),
        ).fetchone()
    path = f"/api/delays/{item['id']}"
    status, first = _request(client, f"{path}/verify", "PATCH", {
        "expected_revision": item["revision"], "review_minutes": 120,
        "verification_note": "Primera verificación",
    }, csrf=True)
    assert status == 200, first
    assert first["revision"] == item["revision"] + 1
    status, second = _request(client, f"{path}/verify", "PATCH", {
        "expected_revision": item["revision"], "review_minutes": 240,
        "verification_note": "Verificación desde una pestaña atrasada",
    }, csrf=True)
    assert status == 409, second
    status, normalized = _request(client, f"{path}/normalize", "PATCH", {
        "expected_revision": item["revision"], "status": "NORMALIZADO",
        "resolution_note": "Cierre desde una pestaña atrasada",
    }, csrf=True)
    assert status == 409, normalized
    with server.connect() as database:
        current = database.execute("SELECT status,revision FROM delay_zones WHERE id=%s", (item["id"],)).fetchone()
    assert current["status"] == "VIGENTE"
    assert current["revision"] == first["revision"]
    status, normalized = _request(client, f"{path}/normalize", "PATCH", {
        "expected_revision": first["revision"], "status": "NORMALIZADO",
        "resolution_note": "Cierre sobre la versión vigente",
    }, csrf=True)
    assert status == 200, normalized
    assert normalized["revision"] == first["revision"] + 1


def test_map_stats_aggregates_active_delays_for_all_departments(delay_client):
    client, server = delay_client
    status, before = _request(client, "/api/dashboard/map-stats")
    assert status == 200
    assert len(before["departments"]) == 19
    assert set(before) == {"as_of", "departments", "unmapped"}
    previous = next(item for item in before["departments"] if item["department"] == "MALDONADO")
    stamp = datetime.now(timezone.utc)
    created_ids = []
    with server.connect() as database:
        for status_value, due, zone in (
            ("VIGENTE", stamp - timedelta(minutes=5), "Punta Ballena"),
            ("VIGENTE", stamp + timedelta(hours=3), "Punta Ballena"),
            ("NORMALIZADO", stamp - timedelta(hours=2), "Piriápolis"),
        ):
            created_ids.append(database.execute(
                """INSERT INTO delay_zones(service,department,zone,message,status,agent,
                       created_at,last_verified_at,next_review_at,expires_at,minutes)
                   VALUES('SINIESTROS','MALDONADO',%s,'Margen de',%s,'Pytest mapa',%s,%s,%s,%s,45)
                   RETURNING id""",
                (zone, status_value, stamp - timedelta(hours=4), stamp - timedelta(hours=2), due, due),
            ).fetchone()["id"])
    status, after = _request(client, "/api/dashboard/map-stats")
    assert status == 200
    department = next(item for item in after["departments"] if item["department"] == "MALDONADO")
    assert department["active_count"] == previous["active_count"] + 2
    assert department["review_due_count"] == previous["review_due_count"] + 1
    assert department["verified_count"] == department["active_count"] - department["review_due_count"]
    details = {item["id"]: item for item in department["delays"]}
    assert details[created_ids[0]]["needs_review"] is True
    assert details[created_ids[1]]["needs_review"] is False
    assert created_ids[2] not in details
    assert details[created_ids[0]]["service"] == "SINIESTROS"
    assert details[created_ids[0]]["zone"] == "Punta Ballena"
    assert details[created_ids[0]]["minutes"] == 45
    assert details[created_ids[0]]["last_verified_at"] is not None
    assert details[created_ids[0]]["review_due_at"] is not None
    assert {"service": "SINIESTROS", "zone": "Punta Ballena"} in department["affected"]
    assert department["affected"].count({"service": "SINIESTROS", "zone": "Punta Ballena"}) == 1
    assert "SINIESTROS" in department["services"] and "Punta Ballena" in department["zones"]
    canelones_before = next(item for item in before["departments"] if item["department"] == "CANELONES")
    canelones_after = next(item for item in after["departments"] if item["department"] == "CANELONES")
    assert canelones_after["active_count"] == canelones_before["active_count"]
    status, normalized = _request(client, f"/api/delays/{created_ids[0]}/normalize", "PATCH", {
        "expected_revision": 1, "status": "NORMALIZADO", "resolution_note": "Normalización aislada del test",
    }, csrf=True)
    assert status == 200, normalized
    status, normalized_map = _request(client, "/api/dashboard/map-stats")
    assert status == 200
    normalized_department = next(item for item in normalized_map["departments"] if item["department"] == "MALDONADO")
    assert normalized_department["active_count"] == department["active_count"] - 1
    assert created_ids[0] not in {item["id"] for item in normalized_department["delays"]}
    anonymous = (build_opener(HTTPCookieProcessor(CookieJar())), CookieJar(), "http://127.0.0.1:18766")
    status, _ = _request(anonymous, "/api/dashboard/map-stats")
    assert status == 401


def test_seed_uses_catalog_and_is_idempotent(delay_client):
    _, server = delay_client
    from app.geography import ALL_DEPARTMENT, URUGUAY_ZONES
    from tools.seed_delays.seed_delays import SEED_COUNT, SEED_PREFIX, build_seed_rows, seed_postgres

    rows = build_seed_rows()
    assert len(rows) == SEED_COUNT == 72
    assert {row["department"] for row in rows} == set(URUGUAY_ZONES)
    assert all(row["zone"] in (ALL_DEPARTMENT, *URUGUAY_ZONES[row["department"]]) for row in rows)
    assert seed_postgres(rows, apply=True) == 72
    assert seed_postgres(rows, apply=True) == 0
    with server.connect() as database:
        result = database.execute(
            """SELECT count(*) AS total,
                      count(*) FILTER (WHERE status='NORMALIZADO') AS normalized,
                      count(*) FILTER (WHERE status='VIGENTE' AND next_review_at < now()) AS overdue,
                      count(DISTINCT department) AS departments
               FROM delay_zones WHERE agent LIKE %s""",
            (f"{SEED_PREFIX}%",),
        ).fetchone()
    assert result == {"total": 72, "normalized": 16, "overdue": 20, "departments": 19}


def test_delay_filter_indexes_exist(delay_client):
    _, server = delay_client
    with server.connect() as database:
        indexes = {row["indexname"]: row["indexdef"] for row in database.execute(
            "SELECT indexname,indexdef FROM pg_indexes WHERE tablename='delay_zones'"
        ).fetchall()}
    assert "delay_zones_status_created_idx" in indexes
    assert "delay_zones_location_idx" in indexes
    assert "delay_review_queue_idx" in indexes
    assert "delay_department_review_idx" in indexes
    assert "delay_map_active_idx" in indexes
    assert "lower(department)" in indexes["delay_department_review_idx"]


def _cycle_delay(server, due, agent):
    with server.connect() as database:
        return database.execute(
            """INSERT INTO delay_zones(service,department,zone,message,status,agent,
                   created_at,last_verified_at,next_review_at,expires_at)
               VALUES('ML','FLORES','Trinidad','A confirmar','VIGENTE',%s,%s,%s,%s,%s)
               RETURNING id""",
            (agent, due - timedelta(hours=2), due - timedelta(hours=1), due,
             due + timedelta(hours=1)),
        ).fetchone()["id"]


def test_review_boundary_and_montevideo_date_match_every_read_path(delay_client):
    from app.delay_map_stats import map_delay_stats
    from app.delays import enrich_delay

    _, server = delay_client
    due = datetime(2010, 1, 15, 12, tzinfo=ZoneInfo("America/Montevideo"))
    marker = "Pytest límite Montevideo"
    delay_id = _cycle_delay(server, due, marker)
    before = due - timedelta(microseconds=1)
    with server.connect() as database:
        record = database.execute("SELECT * FROM delay_zones WHERE id=%s", (delay_id,)).fetchone()
        assert enrich_delay(record, before)["is_current"] is True
        assert enrich_delay(record, due)["needs_review"] is True
        for instant, scope in ((before, "current"), (due, "review")):
            for session_zone in ("UTC", "Pacific/Kiritimati"):
                database.execute("SELECT set_config('TimeZone',%s,true)", (session_zone,))
                filters = {"scope": scope, "q": marker, "date_from": "2010-01-15", "date_to": "2010-01-15"}
                operational = server.paged_delays(database, filters, as_of=instant)
                audit = server.paged_operational_records(database, "delays", filters, as_of=instant)
                assert [item["id"] for item in operational["items"]] == [delay_id]
                assert [item["id"] for item in audit["items"]] == [delay_id]
                assert operational["items"][0]["needs_review"] == (scope == "review")
                assert audit["items"][0]["needs_review"] == (scope == "review")
            map_item = next(item for item in map_delay_stats(database, instant)["departments"]
                            if item["department"] == "FLORES")
            assert next(item for item in map_item["delays"] if item["id"] == delay_id)["needs_review"] == (scope == "review")
    from app.delay_review_worker import run_once
    with server.connect() as database:
        assert run_once(database, before) == 0
    with server.connect() as database:
        assert run_once(database, due) == 0
        assert database.execute("SELECT count(*) n FROM notices WHERE source_delay_id=%s", (delay_id,)).fetchone()["n"] == 0


def test_historical_worker_notice_is_excluded_but_preserved(delay_client):
    client, server = delay_client
    due = datetime(2008, 3, 4, 10, tzinfo=ZoneInfo("America/Montevideo"))
    delay_id = _cycle_delay(server, due, "Pytest aviso histórico")
    status, notices_before = _request(client, "/api/notices/page")
    assert status == 200
    status, dashboard_before = _request(client, "/api/dashboard")
    assert status == 200
    with server.connect() as database:
        notice = database.execute(
            """INSERT INTO notices(notice_type,audience,detail,communicated_by,status,
                   created_at,updated_at,source_delay_id,source_review_due_at)
               VALUES('REVISIÓN DE DEMORA','PLANIFICADORES','Aviso histórico sintético',
                      'Sistema','PENDIENTE',%s,%s,%s,%s) RETURNING id,revision,status""",
            (due, due, delay_id, due),
        ).fetchone()
        human = database.execute(
            """INSERT INTO notices(notice_type,audience,detail,communicated_by,status,
                   task_number,phone,created_at,updated_at)
               VALUES('Reclamo','TODOS','El cliente volvió a llamar por una demora',
                      'Telefonista','PENDIENTE','T-HUMANO','099123456',%s,%s) RETURNING id""",
            (due, due),
        ).fetchone()
        assert server.retire_delay_review_notices(database) == 1
        assert server.retire_delay_review_notices(database) == 0
        retired = database.execute("SELECT status,revision,source_delay_id,administratively_retired_at FROM notices WHERE id=%s", (notice["id"],)).fetchone()
        events = database.execute("SELECT count(*) AS total FROM notice_events WHERE notice_id=%s AND event_type='RETIRO_ADMINISTRATIVO'", (notice["id"],)).fetchone()["total"]
        assert retired["status"] == notice["status"] and retired["revision"] == notice["revision"]
        assert retired["source_delay_id"] == delay_id and retired["administratively_retired_at"] is not None
        assert events == 1
    status, notices_after = _request(client, "/api/notices/page?scope=all")
    assert status == 200
    assert notice["id"] not in {item["id"] for item in notices_after["items"]}
    assert human["id"] in {item["id"] for item in notices_after["items"]}
    status, notices_current = _request(client, "/api/notices/page")
    assert status == 200
    assert notices_current["total"] == notices_before["total"] + 1
    assert notices_current["counts"]["open"] == notices_before["counts"]["open"] + 1
    status, dashboard_after = _request(client, "/api/dashboard")
    assert status == 200
    assert dashboard_after["notices_open"] == dashboard_before["notices_open"] + 1
    status, legacy_list = _request(client, "/api/notices")
    assert status == 200
    assert notice["id"] not in {item["id"] for item in legacy_list}
    assert human["id"] in {item["id"] for item in legacy_list}
    status, hidden_detail = _request(client, f"/api/notices/{notice['id']}")
    assert status == 404
    with server.connect() as database:
        assert notice["id"] not in {item["id"] for item in server.filtered_operational_records(database, "notices")}
        assert human["id"] in {item["id"] for item in server.filtered_operational_records(database, "notices")}
    status, verified = _request(client, f"/api/delays/{delay_id}/verify", "PATCH", {
        "expected_revision": 1, "review_minutes": 30,
        "verification_note": "Aviso histórico conservado",
    }, csrf=True)
    assert status == 200, verified
    status, normalized = _request(client, f"/api/delays/{delay_id}/normalize", "PATCH", {
        "expected_revision": verified["revision"], "status": "NORMALIZADO",
        "resolution_note": "Aviso histórico conservado",
    }, csrf=True)
    assert status == 200, normalized
    with server.connect() as database:
        current = database.execute("SELECT status,revision FROM notices WHERE id=%s", (notice["id"],)).fetchone()
    assert current == {"status": notice["status"], "revision": notice["revision"]}
    with server.connect() as database:
        assert server.restore_administratively_retired_notice(database, notice["id"], "Auditor sintético", "Vínculo revisado")
        assert not server.restore_administratively_retired_notice(database, notice["id"], "Auditor sintético", "Vínculo revisado")
    server.initialize()
    with server.connect() as database:
        restored = database.execute("SELECT source_delay_id,administratively_retired_at,administratively_restored_at FROM notices WHERE id=%s", (notice["id"],)).fetchone()
        assert restored["source_delay_id"] == delay_id
        assert restored["administratively_retired_at"] is None
        assert restored["administratively_restored_at"] is not None
        assert server.retire_delay_review_notices(database) == 0
        assert database.execute("SELECT count(*) AS total FROM notice_events WHERE notice_id=%s AND event_type='RESTITUCION_ADMINISTRATIVA'", (notice["id"],)).fetchone()["total"] == 1


def test_historical_normalized_row_keeps_unknown_close_date(delay_client):
    _, server = delay_client
    with server.connect() as database:
        delay_id = database.execute(
            """INSERT INTO delay_zones(service,department,zone,message,status,agent,created_at)
               VALUES('GRÚA','FLORES','Trinidad','A confirmar','NORMALIZADO','Pytest histórico',%s)
               RETURNING id""",
            (datetime(2004, 5, 6, tzinfo=timezone.utc),),
        ).fetchone()["id"]
    server.initialize()
    with server.connect() as database:
        row = database.execute("SELECT status,normalized_at FROM delay_zones WHERE id=%s", (delay_id,)).fetchone()
    assert row == {"status": "NORMALIZADO", "normalized_at": None}


def test_retired_worker_cannot_access_database(capsys):
    from app.delay_review_worker import main, run_once

    class DatabaseThatFailsOnAccess:
        def execute(self, *args, **kwargs):
            raise AssertionError("El worker retirado no debe consultar ni escribir la base")

    assert run_once(DatabaseThatFailsOnAccess()) == 0
    main()
    assert "retirado" in capsys.readouterr().out
