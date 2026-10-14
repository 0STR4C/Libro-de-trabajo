"""Contrato HTTP, permisos, catálogo y seed de tiempos de arribo."""

from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import json
import os
import threading
import time
import pytest

pytestmark = pytest.mark.skipif(not os.getenv('SECURITY_TEST_DATABASE_URL'),
                                reason='requiere PostgreSQL temporal de tools/postgres_test_db')


def _request(client, path, method="GET", body=None, csrf=False):
    opener, cookies, base = client
    headers = {"Content-Type": "application/json"}
    if csrf:
        headers["X-CSRF-Token"] = next((cookie.value for cookie in cookies if cookie.name == "centro_csrf"), "")
    request = Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                      method=method, headers=headers)
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


@pytest.fixture(autouse=True)
def clean_arrival_rows(delay_client):
    """Cada caso parte de su propio catálogo en la base efímera de pruebas."""
    _, server = delay_client
    with server.connect() as database:
        database.execute('DELETE FROM arrival_times')
    yield
    with server.connect() as database:
        database.execute('DELETE FROM arrival_times')


def test_arrival_catalog_and_seed_are_valid_and_idempotent(delay_client):
    client, server = delay_client
    from app.geography import ALL_DEPARTMENT, URUGUAY_ZONES
    from tools.seed_arrival_times.seed_arrival_times import build_seed_rows, seed_postgres

    status, catalog = _request(client, "/api/arrival-times/geography")
    assert status == 200
    assert set(catalog["departments"]) == set(URUGUAY_ZONES)
    assert all(zones[0] == ALL_DEPARTMENT for zones in catalog["departments"].values())
    rows = build_seed_rows()
    assert len(rows) == 40
    assert {item["department"] for item in rows} == set(URUGUAY_ZONES)
    assert all(item["zone"] in catalog["departments"][item["department"]] for item in rows)
    with server.connect() as database:
        assert seed_postgres(database, rows, apply=True) == 40
    with server.connect() as database:
        assert seed_postgres(database, rows, apply=True) == 0
        counts = database.execute(
            """SELECT count(*) total, count(*) FILTER (WHERE is_active) active,
                      count(DISTINCT department) departments
               FROM arrival_times WHERE seed_key LIKE 'arrival-time-seed-v1-%'"""
        ).fetchone()
        assert counts == {"total": 40, "active": 35, "departments": 19}


def test_arrival_times_api_pages_and_filters_in_postgres(delay_client):
    client, server = delay_client
    from tools.seed_arrival_times.seed_arrival_times import build_seed_rows, seed_postgres
    with server.connect() as database:
        assert seed_postgres(database, build_seed_rows(), apply=True) == 40
    with server.connect() as database:
        database.execute("""INSERT INTO arrival_times(service,department,zone,base_estimated_minutes,
            is_active,created_by,updated_by,created_at,updated_at)
            SELECT 'GRÚA','CANELONES','Todo el departamento',60,FALSE,'Pytest','Pytest',
                now() + n * interval '1 second',now() + n * interval '1 second'
            FROM generate_series(1,15) n""")
    status, first = _request(client, "/api/arrival-times?limit=17&offset=0")
    assert status == 200
    assert set(first) == {"items", "total", "limit", "offset"}
    assert (first["total"], first["limit"], first["offset"], len(first["items"])) == (55, 17, 0, 17)
    status, second = _request(client, "/api/arrival-times?limit=17&offset=17")
    assert status == 200 and len(second["items"]) == 17
    assert {item["id"] for item in first["items"]}.isdisjoint(item["id"] for item in second["items"])
    status, capped = _request(client, "/api/arrival-times?limit=50&offset=0")
    assert status == 200 and capped["total"] == 55 and len(capped["items"]) == 50
    status, tail = _request(client, "/api/arrival-times?limit=50&offset=50")
    assert status == 200 and tail["total"] == 55 and len(tail["items"]) == 5
    status, filtered = _request(client, "/api/arrival-times?department=MONTEVIDEO&service=ML&is_active=true")
    assert status == 200
    assert all(item["department"] == "MONTEVIDEO" and item["service"] == "ML" and item["is_active"] for item in filtered["items"])
    assert filtered["total"] == len(filtered["items"])
    status, inactive = _request(client, "/api/arrival-times?is_active=false")
    assert status == 200 and inactive["total"] == 20
    status, _ = _request(client, "/api/arrival-times?limit=51")
    assert status == 422
    status, _ = _request(client, "/api/arrival-times?department=Atlantida")
    assert status == 422


def test_arrival_time_crud_validates_catalog_duplicate_and_audit(delay_client):
    client, server = delay_client
    payload = {"service": "ml", "department": "montevideo", "zone": "carrasco",
               "base_estimated_minutes": 35, "is_active": True}
    status, created = _request(client, "/api/arrival-times", "POST", payload, csrf=True)
    assert status == 201, created
    assert (created["service"], created["department"], created["zone"]) == ("ML", "MONTEVIDEO", "Carrasco")
    assert created["base_estimated_minutes"] == 35 and created["is_active"] is True
    assert created["created_by"] and created["updated_by"]
    status, detail = _request(client, f"/api/arrival-times/{created['id']}")
    assert status == 200 and detail["id"] == created["id"]
    status, _ = _request(client, "/api/arrival-times", "POST", payload, csrf=True)
    assert status == 409
    status, _ = _request(client, "/api/arrival-times", "POST", {**payload, "zone": "Chuy"}, csrf=True)
    assert status == 422
    status, updated = _request(client, f"/api/arrival-times/{created['id']}", "PATCH", {
        **payload, "zone": "Pocitos", "base_estimated_minutes": 50, "expected_revision": created["revision"],
    }, csrf=True)
    assert status == 200, updated
    assert updated["zone"] == "Pocitos" and updated["base_estimated_minutes"] == 50
    status, _ = _request(client, f"/api/arrival-times/{created['id']}", "PATCH", {
        **payload, "zone": "Buceo", "expected_revision": created["revision"],
    }, csrf=True)
    assert status == 409
    status, _ = _request(client, f"/api/arrival-times/{created['id']}?expected_revision={created['revision']}", "DELETE", csrf=True)
    assert status == 409
    status, _ = _request(client, f"/api/arrival-times/{created['id']}?expected_revision={updated['revision']}", "DELETE", csrf=True)
    assert status == 204
    status, deactivated = _request(client, f"/api/arrival-times/{created['id']}")
    assert status == 200 and deactivated["is_active"] is False
    assert deactivated["revision"] == updated["revision"] + 1
    with server.connect() as database:
        actions = [row["action"] for row in database.execute(
            "SELECT action FROM audit_events WHERE entity='arrival_time' AND entity_id=%s ORDER BY id",
            (created["id"],),
        ).fetchall()]
    assert actions == ["CREADO", "ACTUALIZADO", "DESACTIVADO"]


def test_arrival_times_permissions_are_dynamic(delay_client):
    client, server = delay_client
    from app.security import hash_password

    with server.connect() as database:
        permissions = {row["name"]: row["allowed"] for row in database.execute(
            """SELECT r.name, EXISTS(SELECT 1 FROM role_permissions p
                 WHERE p.role_id=r.id AND p.permission='arrival_times.manage') allowed
                 FROM roles r WHERE r.name IN ('Administrador','Supervisor','Planificador','Telefonista')"""
        ).fetchall()}
        assert permissions == {"Administrador": True, "Supervisor": True,
                               "Planificador": True, "Telefonista": False}
        role = database.execute("SELECT id FROM roles WHERE name='Telefonista'").fetchone()["id"]
        database.execute(
            """INSERT INTO users(username,display_name,password_hash,role_id,active)
               VALUES('pytest-arrival-reader','Lectura Arribo Pytest',%s,%s,TRUE)""",
            (hash_password("SoloPrueba-Arribo-2026"), role),
        )
    cookies = CookieJar()
    reader = (build_opener(HTTPCookieProcessor(cookies)), cookies, "http://127.0.0.1:18766")
    status, _ = _request(reader, "/api/auth/login", "POST", {
        "username": "pytest-arrival-reader", "password": "SoloPrueba-Arribo-2026",
    })
    assert status == 200
    status, _ = _request(reader, "/api/arrival-times")
    assert status == 200
    status, _ = _request(reader, "/api/arrival-times", "POST", {
        "service": "GRÚA", "department": "ROCHA", "zone": "Chuy",
        "base_estimated_minutes": 60, "is_active": True,
    }, csrf=True)
    assert status == 403


def _second_admin_client():
    cookies = CookieJar()
    client = (build_opener(HTTPCookieProcessor(cookies)), cookies, "http://127.0.0.1:18766")
    status, _ = _request(client, "/api/auth/login", "POST", {
        "username": "admin", "password": os.environ["ADMIN_PASSWORD"],
    })
    assert status == 200
    return client


@pytest.mark.parametrize("patch", [
    {"base_estimated_minutes": None}, {"base_estimated_minutes": 0},
    {"base_estimated_minutes": 1441}, {"base_estimated_minutes": "30"},
    {"base_estimated_minutes": True}, {"is_active": None},
    {"is_active": "false"}, {"service": "TODAS"},
    {"service": None}, {"department": None}, {"zone": None},
    {"zone": "Zona inventada"},
])
def test_arrival_rejects_invalid_payloads_on_create_and_update(delay_client, patch):
    client, _ = delay_client
    valid = {"service": "GRÚA", "department": "MONTEVIDEO", "zone": "Pocitos",
             "base_estimated_minutes": 45, "is_active": True}
    status, created = _request(client, "/api/arrival-times", "POST", valid, csrf=True)
    assert status == 201, created
    status, _ = _request(client, "/api/arrival-times", "POST", {**valid, **patch}, csrf=True)
    assert status == 422
    status, _ = _request(client, f"/api/arrival-times/{created['id']}", "PATCH",
                         {**valid, **patch, "expected_revision": created["revision"]}, csrf=True)
    assert status == 422


def test_department_wide_and_specific_zones_have_distinct_exact_keys(delay_client):
    client, _ = delay_client
    base = {"service": "ML", "department": "MONTEVIDEO", "base_estimated_minutes": 40,
            "is_active": True}
    status, broad = _request(client, "/api/arrival-times", "POST", {**base, "zone": "Todo el departamento"}, csrf=True)
    assert status == 201, broad
    status, specific = _request(client, "/api/arrival-times", "POST", {**base, "zone": "Pocitos"}, csrf=True)
    assert status == 201, specific
    assert broad["id"] != specific["id"]
    status, matched = _request(client, "/api/arrival-times/match?service=ml&department=montevideo&zone=pocitos")
    assert status == 200 and matched["id"] == specific["id"]
    status, matched = _request(client, "/api/arrival-times/match?service=ML&department=MONTEVIDEO&zone=Todo%20el%20departamento")
    assert status == 200 and matched["id"] == broad["id"]
    status, _ = _request(client, "/api/arrival-times/match?service=ML&department=MONTEVIDEO&zone=Zona%20inventada")
    assert status == 422


def test_concurrent_duplicate_create_and_stale_edit(delay_client):
    first, _ = delay_client
    second = _second_admin_client()
    payload = {"service": "SINIESTROS", "department": "SALTO", "zone": "Belén",
               "base_estimated_minutes": 65, "is_active": True}
    barrier = Barrier(2)
    def create(client):
        barrier.wait(timeout=5)
        return _request(client, "/api/arrival-times", "POST", payload, csrf=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(create, first)
        b = pool.submit(create, second)
        results = [a.result(timeout=10), b.result(timeout=10)]
    assert sorted(status for status, _ in results) == [201, 409]
    created = next(item for status, item in results if status == 201)
    barrier = Barrier(2)
    def edit(client, minutes):
        barrier.wait(timeout=5)
        return _request(client, f"/api/arrival-times/{created['id']}", "PATCH",
                        {**payload, "base_estimated_minutes": minutes,
                         "expected_revision": created["revision"]}, csrf=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(edit, first, 70)
        b = pool.submit(edit, second, 75)
        results = [a.result(timeout=10), b.result(timeout=10)]
    assert sorted(status for status, _ in results) == [200, 409]
    status, current = _request(first, f"/api/arrival-times/{created['id']}")
    assert status == 200 and current["revision"] == created["revision"] + 1
    assert current["base_estimated_minutes"] in (70, 75)


def test_deactivate_reactivate_filter_and_audit_history(delay_client):
    client, server = delay_client
    payload = {"service": "GRÚA", "department": "CANELONES", "zone": "Pando",
               "base_estimated_minutes": 30, "is_active": True}
    status, first = _request(client, "/api/arrival-times", "POST", payload, csrf=True)
    assert status == 201, first
    status, _ = _request(client, f"/api/arrival-times/{first['id']}?expected_revision={first['revision']}", "DELETE", csrf=True)
    assert status == 204
    status, inactive = _request(client, f"/api/arrival-times/{first['id']}")
    assert status == 200 and not inactive["is_active"]
    status, other = _request(client, "/api/arrival-times", "POST", payload, csrf=True)
    assert status == 201, other
    status, _ = _request(client, f"/api/arrival-times/{first['id']}", "PATCH",
                         {**payload, "expected_revision": first["revision"]}, csrf=True)
    assert status == 409
    status, _ = _request(client, f"/api/arrival-times/{first['id']}", "PATCH",
                         {**payload, "expected_revision": inactive["revision"]}, csrf=True)
    assert status == 409
    status, _ = _request(client, f"/api/arrival-times/{other['id']}?expected_revision={other['revision']}", "DELETE", csrf=True)
    assert status == 204
    status, reactivated = _request(client, f"/api/arrival-times/{first['id']}", "PATCH",
                                   {**payload, "expected_revision": inactive["revision"]}, csrf=True)
    assert status == 200 and reactivated["is_active"] and reactivated["revision"] == inactive["revision"] + 1
    for active, expected in (("true", first["id"]), ("false", other["id"])):
        status, page = _request(client, f"/api/arrival-times?department=CANELONES&service=GR%C3%9AA&is_active={active}")
        assert status == 200 and page["total"] == 1 and page["items"][0]["id"] == expected
    with server.connect() as database:
        actions = [row["action"] for row in database.execute(
            "SELECT action FROM audit_events WHERE entity='arrival_time' AND entity_id=%s ORDER BY id",
            (first["id"],)).fetchall()]
    assert actions == ["CREADO", "DESACTIVADO", "REACTIVADO"]
