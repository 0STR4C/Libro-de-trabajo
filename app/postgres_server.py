"""Servidor multiusuario de Centro Operativo para PostgreSQL."""
import hashlib
import hmac
import ipaddress
import json
import logging
import math
import os
import re
import secrets
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from psycopg.rows import dict_row
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .local_server import (
    ALLOWED_GOOGLE_DOMAIN,
    APP_VERSION,
    DEFAULT_ROLES,
    PERMISSIONS,
    QUOTE_RULE_EXTRA_COLUMNS,
    QUOTE_RULE_LEGACY_COPIES,
    SCHEDULE_ROLES,
    VERSION_NOTES,
    hash_password,
    password_needs_rehash,
    parse_coordinates,
    route_data,
    valid_corporate_email,
    verify_google_id_token,
    verify_password,
)
from .tolls import detect_toll_passes
from .reporting import notice_csv_bytes, report_csv_bytes
from .scheduling import find_schedule_conflict, schedule_conflict_message, schedule_date_value, schedule_time_text
from .schemas import DelayIn, GoogleAccessIn, GoogleLoginIn, LoginIn, NoticeIn, PermissionsIn, QuoteIn, QuoteRulesIn, RoleCreateIn, ScheduleCopyIn, ScheduleIn, StatusIn, TollIn, TransferEdit, TransferIn, UserCreateIn, UserUpdateIn
from .security import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    RateLimitState,
    SESSION_COOKIE_NAME,
    csrf_token_for_session,
    next_rate_limit_state,
    validate_runtime_environment,
)

LOGGER = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
RUNTIME_SECURITY = validate_runtime_environment(os.environ)
APP_ENV = RUNTIME_SECURITY.app_env
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://operativa:operativa@db:5432/operativa")
APP_SECRET = RUNTIME_SECURITY.app_secret
SESSION_SECONDS = int(os.getenv("SESSION_SECONDS", "43200"))
SESSION_IDLE_SECONDS = int(os.getenv("SESSION_IDLE_SECONDS", "1800"))
LOGIN_WINDOW_SECONDS = 900
LOGIN_MAX_FAILURES = 5
TRUSTED_PROXY_IPS = {item.strip() for item in os.getenv("TRUSTED_PROXY_IPS", "127.0.0.1,::1").split(",") if item.strip()}
ALLOWED_HOSTS = [item.strip() for item in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if item.strip()]
ALLOWED_ORIGINS = {item.strip().rstrip("/") for item in os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",") if item.strip()}
MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", str(1024 * 1024)))
ENABLE_API_DOCS = os.getenv("ENABLE_API_DOCS", "true" if APP_ENV == "development" else "false").strip().lower() == "true"
HTTPS_CONFIRMED = os.getenv("HTTPS_CONFIRMED", "false").strip().lower() == "true"
GOOGLE_NONCES: dict[str, float] = {}

SCHEMA = """
CREATE TABLE IF NOT EXISTS notices(id BIGSERIAL PRIMARY KEY,task_number TEXT,phone TEXT,notice_type TEXT NOT NULL,audience TEXT NOT NULL DEFAULT 'TODOS',detail TEXT NOT NULL,communicated_by TEXT NOT NULL,managed_by TEXT,status TEXT NOT NULL DEFAULT 'PENDIENTE',comments TEXT,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS delay_zones(id BIGSERIAL PRIMARY KEY,service TEXT NOT NULL,department TEXT NOT NULL,zone TEXT NOT NULL,message TEXT NOT NULL,minutes INTEGER,status TEXT NOT NULL,agent TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL,normalized_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS scheduled_transfers(id BIGSERIAL PRIMARY KEY,task_number TEXT NOT NULL,transfer_type TEXT NOT NULL,scheduled_date DATE NOT NULL,scheduled_time TIME,origin TEXT NOT NULL,destination TEXT NOT NULL,provider TEXT,planner TEXT NOT NULL,status TEXT NOT NULL,comments TEXT,created_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS arrival_standards(id BIGSERIAL PRIMARY KEY,department TEXT NOT NULL,zone TEXT NOT NULL,service TEXT NOT NULL,minutes_min INTEGER,minutes_max INTEGER,note TEXT);
CREATE TABLE IF NOT EXISTS audit_events(id BIGSERIAL PRIMARY KEY,entity TEXT NOT NULL,entity_id BIGINT NOT NULL,action TEXT NOT NULL,actor TEXT NOT NULL,detail TEXT,created_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS roles(id BIGSERIAL PRIMARY KEY,name TEXT NOT NULL UNIQUE,description TEXT);
CREATE TABLE IF NOT EXISTS role_permissions(role_id BIGINT NOT NULL REFERENCES roles(id),permission TEXT NOT NULL,PRIMARY KEY(role_id,permission));
CREATE TABLE IF NOT EXISTS users(id BIGSERIAL PRIMARY KEY,username TEXT NOT NULL UNIQUE,email TEXT,google_sub TEXT UNIQUE,display_name TEXT NOT NULL,password_hash TEXT NOT NULL,role_id BIGINT NOT NULL REFERENCES roles(id),active BOOLEAN NOT NULL DEFAULT TRUE);
CREATE TABLE IF NOT EXISTS work_schedules(id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL REFERENCES users(id),schedule_date DATE NOT NULL,week_start DATE NOT NULL,role_name TEXT NOT NULL,shift_name TEXT NOT NULL,start_time TIME,end_time TIME,notes TEXT,created_by TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL);
CREATE INDEX IF NOT EXISTS work_schedules_date_idx ON work_schedules(schedule_date,week_start);
CREATE INDEX IF NOT EXISTS work_schedules_user_idx ON work_schedules(user_id,schedule_date);
CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique ON users(lower(email)) WHERE email IS NOT NULL;
CREATE TABLE IF NOT EXISTS app_sessions(token_hash TEXT PRIMARY KEY,user_id BIGINT NOT NULL REFERENCES users(id),expires_at TIMESTAMPTZ NOT NULL,created_at TIMESTAMPTZ NOT NULL,last_seen_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS auth_attempts(attempt_key TEXT PRIMARY KEY,failures INTEGER NOT NULL,window_started_at TIMESTAMPTZ NOT NULL,blocked_until TIMESTAMPTZ,last_failed_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS schema_migrations(key TEXT PRIMARY KEY,applied_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS quote_rules(
 id INTEGER PRIMARY KEY CHECK(id=1),insured_base DOUBLE PRECISION NOT NULL,uninsured_base DOUBLE PRECISION NOT NULL,
 special_insured_base DOUBLE PRECISION NOT NULL,special_uninsured_base DOUBLE PRECISION NOT NULL,gavilan_base DOUBLE PRECISION NOT NULL,
 included_km DOUBLE PRECISION NOT NULL,extra_km_rate DOUBLE PRECISION NOT NULL,special_extra_km_rate DOUBLE PRECISION NOT NULL,
 gavilan_insured_base DOUBLE PRECISION NOT NULL DEFAULT 2140,gavilan_uninsured_base DOUBLE PRECISION NOT NULL DEFAULT 2140,
 transfer_insured_base DOUBLE PRECISION NOT NULL DEFAULT 2550,transfer_uninsured_base DOUBLE PRECISION NOT NULL DEFAULT 2850,
 transfer_special_insured_base DOUBLE PRECISION NOT NULL DEFAULT 4050,transfer_special_uninsured_base DOUBLE PRECISION NOT NULL DEFAULT 4470,
 locksmith_mvd_insured_base DOUBLE PRECISION NOT NULL DEFAULT 1785,locksmith_mvd_uninsured_base DOUBLE PRECISION NOT NULL DEFAULT 1930,
 locksmith_coast_insured_base DOUBLE PRECISION NOT NULL DEFAULT 2720,locksmith_coast_uninsured_base DOUBLE PRECISION NOT NULL DEFAULT 2950,
 locksmith_mvd_after22_insured_base DOUBLE PRECISION NOT NULL DEFAULT 0,locksmith_mvd_after22_uninsured_base DOUBLE PRECISION NOT NULL DEFAULT 0,
 locksmith_coast_after22_insured_base DOUBLE PRECISION NOT NULL DEFAULT 0,locksmith_coast_after22_uninsured_base DOUBLE PRECISION NOT NULL DEFAULT 0,
 extra_km_insured_rate DOUBLE PRECISION NOT NULL DEFAULT 120,extra_km_uninsured_rate DOUBLE PRECISION NOT NULL DEFAULT 90,
 special_extra_km_insured_rate DOUBLE PRECISION NOT NULL DEFAULT 120,special_extra_km_uninsured_rate DOUBLE PRECISION NOT NULL DEFAULT 110,
 toll_insured DOUBLE PRECISION NOT NULL DEFAULT 416,toll_uninsured DOUBLE PRECISION NOT NULL DEFAULT 416,
 waiting_hour_insured DOUBLE PRECISION NOT NULL DEFAULT 820,waiting_hour_uninsured DOUBLE PRECISION NOT NULL DEFAULT 820,
 rescue_hour_insured DOUBLE PRECISION NOT NULL DEFAULT 900,rescue_hour_uninsured DOUBLE PRECISION NOT NULL DEFAULT 900,
 updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS toll_catalog(id BIGSERIAL PRIMARY KEY,name TEXT NOT NULL,latitude DOUBLE PRECISION NOT NULL,longitude DOUBLE PRECISION NOT NULL,price DOUBLE PRECISION,active BOOLEAN NOT NULL DEFAULT TRUE,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS quotes(id BIGSERIAL PRIMARY KEY,task_number TEXT,origin_input TEXT NOT NULL,destination_input TEXT NOT NULL,mobile_input TEXT,uninsured BOOLEAN NOT NULL,special BOOLEAN NOT NULL,gavilan BOOLEAN NOT NULL,trip_km DOUBLE PRECISION NOT NULL,mobile_km DOUBLE PRECISION NOT NULL,total_km DOUBLE PRECISION NOT NULL,included_km DOUBLE PRECISION NOT NULL,extra_km DOUBLE PRECISION NOT NULL,base_price DOUBLE PRECISION NOT NULL,extra_price DOUBLE PRECISION NOT NULL,toll_count INTEGER NOT NULL DEFAULT 0,toll_details TEXT NOT NULL DEFAULT '[]',toll_price DOUBLE PRECISION NOT NULL DEFAULT 0,total_price DOUBLE PRECISION NOT NULL,created_by TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL);
"""


def now():
    return datetime.now(timezone.utc)

def schedule_week_start(value):
    parsed=value if hasattr(value,"weekday") else datetime.strptime(str(value),"%Y-%m-%d").date()
    return parsed-timedelta(days=parsed.weekday())

def schedule_people(database):
    return rows(database,"SELECT u.id,u.display_name,u.role_id,r.name role_name FROM users u JOIN roles r ON r.id=u.role_id WHERE u.active=TRUE AND r.name = ANY(%s) ORDER BY CASE r.name WHEN 'Supervisor' THEN 1 WHEN 'Planificador' THEN 2 ELSE 3 END,u.display_name",(list(SCHEDULE_ROLES),))

def filtered_schedules(database, week="", date_from="", date_to="", employee_id=None, role="", q="", limit=20000):
    query="SELECT s.id,s.user_id,s.schedule_date,s.week_start,COALESCE(NULLIF(s.role_name,''),r.name,'') AS role_name,s.shift_name,s.start_time,s.end_time,s.notes,s.created_by,s.created_at,s.updated_at,COALESCE(u.display_name,'Usuario no disponible') AS display_name FROM work_schedules s LEFT JOIN users u ON u.id=s.user_id LEFT JOIN roles r ON r.id=u.role_id WHERE TRUE"; values=[]
    if week:query+=" AND s.week_start=%s";values.append(schedule_week_start(week))
    else:
        if date_from:query+=" AND s.schedule_date>=%s::date";values.append(date_from)
        if date_to:query+=" AND s.schedule_date<=%s::date";values.append(date_to)
    if employee_id is not None:query+=" AND s.user_id=%s";values.append(employee_id)
    if role:query+=" AND COALESCE(NULLIF(s.role_name,''),r.name)=%s";values.append(role)
    if q:query+=" AND concat_ws(' ',u.display_name,s.role_name,s.shift_name,s.notes) ILIKE %s";values.append(f"%{q}%")
    query+=f" ORDER BY s.schedule_date,s.start_time,display_name LIMIT {int(limit)}"
    return rows(database,query,values)

def schedule_item(database,item_id):
    return database.execute("SELECT s.id,s.user_id,s.schedule_date,s.week_start,COALESCE(NULLIF(s.role_name,''),r.name,'') AS role_name,s.shift_name,s.start_time,s.end_time,s.notes,s.created_by,s.created_at,s.updated_at,COALESCE(u.display_name,'Usuario no disponible') AS display_name FROM work_schedules s LEFT JOIN users u ON u.id=s.user_id LEFT JOIN roles r ON r.id=u.role_id WHERE s.id=%s",(item_id,)).fetchone()

def lock_schedule_slot(database,user_id,schedule_date):
    day=schedule_date_value(schedule_date)
    for offset in (-1,0,1):
        lock_key=int(user_id)*10_000_000+(day+timedelta(days=offset)).toordinal()
        database.execute("SELECT pg_advisory_xact_lock(%s)",(lock_key,))

def postgres_schedule_conflict(database,user_id,schedule_date,shift_name,start_time,end_time,exclude_id=None):
    day=schedule_date_value(schedule_date)
    candidates=database.execute("SELECT id,schedule_date,shift_name,start_time,end_time FROM work_schedules WHERE user_id=%s AND schedule_date BETWEEN %s AND %s",(user_id,day-timedelta(days=1),day+timedelta(days=1))).fetchall()
    return find_schedule_conflict(candidates,day,shift_name,start_time,end_time,exclude_id)


@contextmanager
def connect():
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as database:
        yield database


def rows(database, query, parameters=()):
    return database.execute(query, parameters).fetchall()


def execute_many(database, query, parameters):
    with database.cursor() as cursor:
        cursor.executemany(query, parameters)


def validated_body(model, payload):
    try:
        return model.model_validate(payload).model_dump()
    except ValidationError as exc:
        raise HTTPException(422, "Los datos enviados no tienen un formato válido") from exc


def setting(database, key, default=""):
    item = database.execute("SELECT value FROM app_settings WHERE key=%s", (key,)).fetchone()
    return item["value"] if item else default


def audit(database, entity, entity_id, action, actor, detail=""):
    database.execute(
        "INSERT INTO audit_events(entity,entity_id,action,actor,detail,created_at) VALUES(%s,%s,%s,%s,%s,%s)",
        (entity, entity_id, action, actor, detail, now()),
    )


def initialize():
    with connect() as database:
        database.execute(SCHEMA)
        from .wfm import SCHEMA as WFM_SCHEMA
        database.execute(WFM_SCHEMA)
        quote_rule_columns={row["column_name"] for row in database.execute("SELECT column_name FROM information_schema.columns WHERE table_name='quote_rules'").fetchall()}
        added_quote_rule_columns=[]
        for column,default in QUOTE_RULE_EXTRA_COLUMNS.items():
            if column not in quote_rule_columns:
                database.execute(f"ALTER TABLE quote_rules ADD COLUMN {column} DOUBLE PRECISION NOT NULL DEFAULT {float(default)}")
                added_quote_rule_columns.append(column)
        database.execute("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS toll_count INTEGER NOT NULL DEFAULT 0")
        database.execute("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS toll_details TEXT NOT NULL DEFAULT '[]'")
        database.execute("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS toll_price DOUBLE PRECISION NOT NULL DEFAULT 0")
        database.execute("ALTER TABLE app_sessions ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ")
        database.execute("UPDATE app_sessions SET last_seen_at=created_at WHERE last_seen_at IS NULL")
        database.execute("ALTER TABLE app_sessions ALTER COLUMN last_seen_at SET NOT NULL")
        database.execute("INSERT INTO app_settings(key,value) VALUES('google_client_id','') ON CONFLICT(key) DO NOTHING")
        database.execute(
            "INSERT INTO app_settings(key,value) VALUES('google_allowed_domain',%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
            (ALLOWED_GOOGLE_DOMAIN,),
        )
        role_ids = {}
        for name, permissions in DEFAULT_ROLES.items():
            role = database.execute("SELECT id FROM roles WHERE name=%s", (name,)).fetchone()
            if not role:
                role = database.execute(
                    "INSERT INTO roles(name,description) VALUES(%s,%s) RETURNING id", (name, f"Rol {name}")
                ).fetchone()
            role_ids[name] = role["id"]
            if name != "Administrador":
                execute_many(database,
                    "INSERT INTO role_permissions(role_id,permission) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                    [(role["id"], permission) for permission in permissions],
                )
        admin_id = role_ids["Administrador"]
        database.execute("DELETE FROM role_permissions WHERE role_id=%s", (admin_id,))
        execute_many(database,
            "INSERT INTO role_permissions(role_id,permission) VALUES(%s,%s)",
            [(admin_id, permission) for permission in PERMISSIONS],
        )
        if not database.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            database.execute(
                "INSERT INTO users(username,display_name,password_hash,role_id,active) VALUES(%s,%s,%s,%s,TRUE)",
                (
                    os.getenv("ADMIN_USER", "admin"),
                    "Administrador",
                    hash_password(RUNTIME_SECURITY.admin_password),
                    admin_id,
                ),
            )
        database.execute(
            """INSERT INTO quote_rules(id,insured_base,uninsured_base,special_insured_base,special_uninsured_base,gavilan_base,included_km,extra_km_rate,special_extra_km_rate,updated_at)
            VALUES(1,2140,2750,4050,4470,2140,25,120,120,%s) ON CONFLICT(id) DO NOTHING""",
            (now(),),
        )
        assignments=[f"{column}={QUOTE_RULE_LEGACY_COPIES[column]}" for column in added_quote_rule_columns if column in QUOTE_RULE_LEGACY_COPIES]
        if assignments:
            database.execute(f"UPDATE quote_rules SET {','.join(assignments)} WHERE id=1")
        if not database.execute("SELECT 1 FROM arrival_standards LIMIT 1").fetchone():
            execute_many(database,
                "INSERT INTO arrival_standards(department,zone,service,minutes_min,minutes_max,note) VALUES(%s,%s,%s,%s,%s,%s)",
                [
                    ("MONTEVIDEO", "Centro, Parque Rodó, Pocitos, Punta Carretas, Tres Cruces, Buceo", "ML", None, 30, None),
                    ("MONTEVIDEO", "Nuevo París, Cerro, Colón, Casavalle, Peñarol, La Teja, Manga", "ML", None, 45, None),
                    ("MONTEVIDEO", "Ciudad", "GRÚA", None, 45, None),
                    ("CANELONES", "Ciudad de la Costa", "ML", None, 45, None),
                    ("ARTIGAS", "Artigas", "ML", None, 45, None),
                    ("ARTIGAS", "Artigas", "GRÚA", None, 60, None),
                    ("MALDONADO", "Maldonado Ciudad, Piriápolis", "ML", 30, 45, None),
                    ("INTERIOR", "Zona no listada", "ML", None, None, "A confirmar"),
                ],
            )


def token_from(request: Request):
    return request.cookies.get(SESSION_COOKIE_NAME, "")


def token_hash(token):
    return hmac.new(APP_SECRET.encode(), token.encode(), hashlib.sha256).hexdigest()


def request_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    candidate = peer
    if peer in TRUSTED_PROXY_IPS:
        forwarded = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
        if forwarded:
            candidate = forwarded
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return "unknown"


def attempt_key(identifier: str, source_ip: str) -> str:
    normalized = f"{identifier.strip().lower()}|{source_ip}"
    return hmac.new(APP_SECRET.encode(), normalized.encode(), hashlib.sha256).hexdigest()


def enforce_login_limit(database, key: str):
    item = database.execute("SELECT * FROM auth_attempts WHERE attempt_key=%s", (key,)).fetchone()
    current_time = now()
    if item and item["blocked_until"] and item["blocked_until"] > current_time:
        return max(1, math.ceil((item["blocked_until"] - current_time).total_seconds()))
    return 0


def register_login_failure(database, key: str) -> int:
    item = database.execute("SELECT * FROM auth_attempts WHERE attempt_key=%s", (key,)).fetchone()
    previous = None
    if item:
        previous = RateLimitState(
            failures=item["failures"],
            window_started_at=item["window_started_at"].timestamp(),
            blocked_until=item["blocked_until"].timestamp() if item["blocked_until"] else 0,
        )
    current_time = now()
    state = next_rate_limit_state(previous, current_time.timestamp(), LOGIN_WINDOW_SECONDS, LOGIN_MAX_FAILURES)
    blocked_until = datetime.fromtimestamp(state.blocked_until, timezone.utc) if state.blocked_until else None
    window_started_at = datetime.fromtimestamp(state.window_started_at, timezone.utc)
    database.execute(
        """INSERT INTO auth_attempts(attempt_key,failures,window_started_at,blocked_until,last_failed_at)
        VALUES(%s,%s,%s,%s,%s) ON CONFLICT(attempt_key) DO UPDATE SET
        failures=EXCLUDED.failures,window_started_at=EXCLUDED.window_started_at,
        blocked_until=EXCLUDED.blocked_until,last_failed_at=EXCLUDED.last_failed_at""",
        (key, state.failures, window_started_at, blocked_until, current_time),
    )
    return max(0, math.ceil(state.blocked_until - current_time.timestamp()))


def clear_login_failures(database, key: str):
    database.execute("DELETE FROM auth_attempts WHERE attempt_key=%s", (key,))


def reject_authentication(key: str, entity_id: int = 0):
    with connect() as database:
        retry = register_login_failure(database, key)
        audit(database, "session", entity_id, "INGRESO_BLOQUEADO" if retry else "INGRESO_FALLIDO", "Autenticación", f"huella={key[:16]}")
    if retry:
        raise HTTPException(429, "Demasiados intentos. Intente nuevamente más tarde.", headers={"Retry-After": str(retry)})
    raise HTTPException(401, "No se pudo completar la autenticación")


def ensure_active_admin_survives(database, user_id: int, new_role_id: int, active: bool):
    current = database.execute(
        "SELECT u.active,r.name FROM users u JOIN roles r ON r.id=u.role_id WHERE u.id=%s",
        (user_id,),
    ).fetchone()
    if not current:
        raise HTTPException(404, "Usuario inexistente")
    target_role = database.execute("SELECT name FROM roles WHERE id=%s", (new_role_id,)).fetchone()
    if not target_role:
        raise HTTPException(400, "El rol indicado no existe")
    removing_admin = current["name"] == "Administrador" and (not active or target_role["name"] != "Administrador")
    if removing_admin:
        admins = database.execute(
            "SELECT count(*) AS total FROM users u JOIN roles r ON r.id=u.role_id WHERE u.active=TRUE AND r.name='Administrador' AND u.id<>%s",
            (user_id,),
        ).fetchone()["total"]
        if admins < 1:
            raise HTTPException(400, "No se puede dejar el sistema sin un Administrador activo")


def create_session(database, user_id, previous_token=""):
    token = secrets.token_urlsafe(32)
    database.execute("DELETE FROM app_sessions WHERE expires_at<=%s", (now(),))
    if previous_token:
        database.execute("DELETE FROM app_sessions WHERE token_hash=%s", (token_hash(previous_token),))
    database.execute(
        "INSERT INTO app_sessions(token_hash,user_id,expires_at,created_at,last_seen_at) VALUES(%s,%s,%s + (%s * interval '1 second'),%s,%s)",
        (token_hash(token), user_id, now(), SESSION_SECONDS, now(), now()),
    )
    return token


def set_auth_cookies(response: Response, token: str):
    secure = APP_ENV == "production"
    common = {"secure": secure, "samesite": "strict", "path": "/", "max_age": SESSION_SECONDS}
    response.set_cookie(SESSION_COOKIE_NAME, token, httponly=True, **common)
    response.set_cookie(CSRF_COOKIE_NAME, csrf_token_for_session(token, APP_SECRET), httponly=False, **common)


def clear_auth_cookies(response: Response):
    secure = APP_ENV == "production"
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", secure=secure, httponly=True, samesite="strict")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/", secure=secure, httponly=False, samesite="strict")


def current_user(request: Request):
    token = token_from(request)
    if not token:
        raise HTTPException(401, "Debe iniciar sesión")
    with connect() as database:
        current_time = now()
        user = database.execute(
            """SELECT u.id,u.username,u.email,u.display_name,u.active,r.id role_id,r.name role_name,s.last_seen_at
            FROM app_sessions s JOIN users u ON u.id=s.user_id JOIN roles r ON r.id=u.role_id
            WHERE s.token_hash=%s AND s.expires_at>%s AND s.last_seen_at>%s AND u.active=TRUE""",
            (token_hash(token), current_time, current_time - timedelta(seconds=SESSION_IDLE_SECONDS)),
        ).fetchone()
        if not user:
            database.execute("DELETE FROM app_sessions WHERE token_hash=%s", (token_hash(token),))
            raise HTTPException(401, "Debe iniciar sesión")
        database.execute("UPDATE app_sessions SET last_seen_at=%s WHERE token_hash=%s", (current_time, token_hash(token)))
        user.pop("last_seen_at", None)
        user["permissions"] = [
            item["permission"]
            for item in rows(database, "SELECT permission FROM role_permissions WHERE role_id=%s ORDER BY permission", (user["role_id"],))
        ]
        return user


def authorized(request, permission):
    user = current_user(request)
    if permission == 'schedules.manage' and user['role_name'] not in ('Supervisor', 'Administrador'):
        raise HTTPException(403, 'Solo Supervisor o Administrador puede gestionar horarios')
    if permission not in user["permissions"]:
        raise HTTPException(403, "Su rol no tiene permiso para realizar esta acción")
    return user


@asynccontextmanager
async def lifespan(_app):
    initialize()
    yield


app = FastAPI(
    title="Centro Operativo",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if ENABLE_API_DOCS else None,
    redoc_url="/redoc" if ENABLE_API_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_API_DOCS else None,
)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get('/api/wfm/{action}')
def wfm_get(action: str, request: Request):
    from .wfm import dispatch, WfmError
    actor = authorized(request, 'schedules.view')
    try:
        with connect() as database:
            return dispatch(database, actor, 'GET', action, dict(request.query_params), postgres=True)
    except WfmError as error:
        raise HTTPException(error.status, str(error)) from None
    except Exception:
        LOGGER.exception("Error inesperado al consultar WFM: %s", action)
        raise HTTPException(500, "No se pudo cargar la planificación. Reintentá después de actualizar el servicio.") from None


@app.post('/api/wfm/{action}')
def wfm_post(action: str, request: Request, data: dict = Body(...)):
    from .wfm import dispatch, WfmError
    actor = authorized(request, 'schedules.view')
    try:
        with connect() as database:
            result = dispatch(database, actor, 'POST', action, dict(request.query_params), data, postgres=True)
            if action == 'plan':
                operation = data.get('operation', 'save')
                event = {'save': 'BORRADOR_GUARDADO', 'optimize': 'DESCANSOS_SUGERIDOS', 'publish': 'HORARIOS_PUBLICADOS'}.get(operation, 'PLAN_ACTUALIZADO')
                detail = f"{request.query_params.get('date', '')} · {request.query_params.get('team', '')} · revisión {result.get('revision', 0)}"
            elif action == 'requirements':
                event = 'REQUERIMIENTOS_ACTUALIZADOS'; detail = f"Equipo {request.query_params.get('team', '')}"
            elif action == 'settings':
                event = 'CONFIGURACION_WFM_ACTUALIZADA'; detail = f"Turno {result.get('shift_minutes', 0)} min · descanso {result.get('break_minutes', 0)} min"
            elif action == 'requests':
                decision = data.get('decision')
                event = {'APROBAR': 'SOLICITUD_WFM_APROBADA', 'RECHAZAR': 'SOLICITUD_WFM_RECHAZADA'}.get(decision, 'SOLICITUD_WFM_CREADA')
                detail = f"{result.get('request_id', '')} · {result.get('requested_date', '')} · {result.get('request_type', '')}"
            elif action == 'publish-week':
                event = 'SEMANA_WFM_PUBLICADA'; detail = f"{result.get('week', '')} · {result.get('team', '')} · {result.get('published_count', 0)} días"
            else:
                event = 'WFM_ACTUALIZADO'; detail = request.query_params.get('team', '')
            audit(database, 'wfm', 0, event, actor['display_name'], detail)
            return result
    except WfmError as error:
        raise HTTPException(error.status, str(error)) from None
    except Exception:
        LOGGER.exception("Error inesperado al actualizar WFM: %s", action)
        raise HTTPException(500, "No se pudo actualizar la planificación. Reintentá después de actualizar el servicio.") from None
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)


def request_is_https(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    peer = request.client.host if request.client else ""
    return peer in TRUSTED_PROXY_IPS and request.headers.get("X-Forwarded-Proto", "").lower() == "https"


@app.middleware("http")
async def request_limits_and_security_headers(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_BODY_BYTES:
        return JSONResponse({"detail": "El cuerpo de la solicitud es demasiado grande"}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    docs_sources = " https://cdn.jsdelivr.net" if ENABLE_API_DOCS else ""
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        f"script-src 'self' https://accounts.google.com{docs_sources}; "
        f"style-src 'self' 'unsafe-inline'{docs_sources}; "
        "img-src 'self' data: blob: https://*.tile.openstreetmap.org; "
        "font-src 'self'; connect-src 'self' https://accounts.google.com; "
        "frame-src https://accounts.google.com; frame-ancestors 'none'; "
        "base-uri 'self'; form-action 'self'; object-src 'none'"
    )
    if request.url.path.startswith("/api/") or request.url.path in {"/health", "/docs", "/redoc", "/openapi.json"}:
        response.headers["Cache-Control"] = "no-store"
    if HTTPS_CONFIRMED and request_is_https(request):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.middleware("http")
async def csrf_protection(request: Request, call_next):
    origin = request.headers.get("Origin", "").rstrip("/")
    if origin and origin not in ALLOWED_ORIGINS:
        return JSONResponse({"detail": "Origen no autorizado"}, status_code=403)
    mutating = request.method in {"POST", "PUT", "PATCH", "DELETE"}
    public_auth = request.url.path in {"/api/auth/login", "/api/auth/google"}
    if mutating and not public_auth:
        token = token_from(request)
        if not token:
            return JSONResponse({"detail": "Debe iniciar sesión"}, status_code=401)
        supplied = request.headers.get(CSRF_HEADER_NAME, "")
        cookie_value = request.cookies.get(CSRF_COOKIE_NAME, "")
        expected = csrf_token_for_session(token, APP_SECRET)
        if not supplied or not hmac.compare_digest(supplied, cookie_value) or not hmac.compare_digest(supplied, expected):
            return JSONResponse({"detail": "La validación de seguridad de la solicitud falló"}, status_code=403)
    return await call_next(request)


@app.get("/", include_in_schema=False)
def home(): return FileResponse(STATIC / "index.html")


for _name, _media in (("styles.css", "text/css"), ("settings.css", "text/css"), ("operations.css", "text/css"), ("dashboard.css", "text/css"), ("quotes.css", "text/css"), ("auth.css", "text/css"), ("app.js", "application/javascript"), ("uruguay-departamentos.geojson", "application/geo+json")):
    def static_file(name=_name, media=_media): return FileResponse(STATIC / name, media_type=media)
    app.add_api_route(f"/{_name}", static_file, include_in_schema=False)


@app.get("/health")
def health():
    with connect() as database: database.execute("SELECT 1")
    return {"status": "ok"}


@app.get("/api/auth/me")
def auth_me(request: Request): return current_user(request)


@app.get("/api/auth/google-config")
def google_config():
    stamp = time.time()
    for nonce, expires in list(GOOGLE_NONCES.items()):
        if expires < stamp: GOOGLE_NONCES.pop(nonce, None)
    nonce = secrets.token_urlsafe(24); GOOGLE_NONCES[nonce] = stamp + 3600
    with connect() as database: client_id = setting(database, "google_client_id")
    return {"enabled": bool(client_id), "client_id": client_id, "allowed_domain": ALLOWED_GOOGLE_DOMAIN, "nonce": nonce}


@app.post("/api/auth/login")
def login(request: Request, data: LoginIn = Body(...)):
    data = data.model_dump()
    login_name = str(data.get("username", "")).strip()
    key = attempt_key(login_name, request_ip(request))
    with connect() as database:
        retry = enforce_login_limit(database, key)
        if retry:
            audit(database, "session", 0, "INGRESO_BLOQUEADO", "Autenticación", f"huella={key[:16]}")
            blocked = True
            user = None
        else:
            blocked = False
            user = database.execute(
                "SELECT * FROM users WHERE (lower(username)=lower(%s) OR lower(email)=lower(%s)) AND active=TRUE",
                (login_name, login_name),
            ).fetchone()
            valid = bool(user and verify_password(str(data.get("password", "")), user["password_hash"]))
            if not valid:
                retry = register_login_failure(database, key)
                audit(database, "session", user["id"] if user else 0, "INGRESO_BLOQUEADO" if retry else "INGRESO_FALLIDO", "Autenticación", f"huella={key[:16]}")
    if blocked or retry:
        if retry:
            raise HTTPException(429, "Demasiados intentos. Intente nuevamente más tarde.", headers={"Retry-After": str(retry)})
    if not user or not valid:
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    with connect() as database:
        clear_login_failures(database, key)
        if password_needs_rehash(user["password_hash"]):
            database.execute("UPDATE users SET password_hash=%s WHERE id=%s", (hash_password(str(data.get("password", ""))), user["id"]))
        token = create_session(database, user["id"], token_from(request))
        audit(database, "session", user["id"], "INGRESO_PASSWORD", user["display_name"], f"huella={key[:16]}")
    response = JSONResponse({"ok": True})
    set_auth_cookies(response, token)
    return response


@app.post("/api/auth/logout")
def logout(request: Request):
    token = token_from(request)
    if token:
        with connect() as database:
            user = database.execute("SELECT u.id,u.display_name FROM app_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=%s", (token_hash(token),)).fetchone()
            database.execute("DELETE FROM app_sessions WHERE token_hash=%s", (token_hash(token),))
            if user:
                audit(database, "session", user["id"], "SALIDA", user["display_name"])
    response = JSONResponse({"ok": True})
    clear_auth_cookies(response)
    return response


@app.post("/api/auth/google")
def google_login(request: Request, data: GoogleLoginIn = Body(...)):
    data = data.model_dump()
    key = attempt_key("google", request_ip(request))
    with connect() as database:
        retry = enforce_login_limit(database, key)
        if retry:
            audit(database, "session", 0, "INGRESO_BLOQUEADO", "Autenticación", f"huella={key[:16]}")
    if retry:
        raise HTTPException(429, "Demasiados intentos. Intente nuevamente más tarde.", headers={"Retry-After": str(retry)})
    nonce = str(data.get("nonce") or "")
    if GOOGLE_NONCES.pop(nonce, 0) < time.time(): reject_authentication(key)
    with connect() as database: client_id = setting(database, "google_client_id")
    if not client_id: raise HTTPException(503, "El ingreso con Google todavía no está configurado")
    try: identity = verify_google_id_token(str(data.get("credential") or ""), client_id, nonce)
    except ValueError: reject_authentication(key)
    try:
        with connect() as database:
            user = database.execute("SELECT * FROM users WHERE lower(email)=%s AND active=TRUE", (identity["email"],)).fetchone()
            if not user or (user["google_sub"] and user["google_sub"] != identity["sub"]):
                rejected_user_id = user["id"] if user else 0
            else:
                rejected_user_id = None
                database.execute("UPDATE users SET google_sub=%s WHERE id=%s", (identity["sub"], user["id"]))
        if rejected_user_id is not None: reject_authentication(key, rejected_user_id)
    except psycopg.errors.UniqueViolation: reject_authentication(key)
    with connect() as database:
        clear_login_failures(database, key)
        token = create_session(database, user["id"], token_from(request))
        audit(database, "session", user["id"], "INGRESO_GOOGLE", user["display_name"], f"huella={key[:16]}")
    response = JSONResponse({"ok": True})
    set_auth_cookies(response, token)
    return response


@app.get("/api/settings/permissions")
def permissions(request: Request):
    authorized(request, "settings.manage")
    return [{"key": key, "label": label} for key, label in PERMISSIONS.items()]


@app.get("/api/settings/roles")
def roles(request: Request):
    authorized(request, "settings.manage")
    with connect() as database:
        result = rows(database, "SELECT * FROM roles ORDER BY name")
        for role in result:
            role["permissions"] = [item["permission"] for item in rows(database, "SELECT permission FROM role_permissions WHERE role_id=%s ORDER BY permission", (role["id"],))]
    return result


@app.post("/api/settings/roles", status_code=201)
def create_role(request: Request, data: RoleCreateIn = Body(...)):
    data = data.model_dump()
    actor = authorized(request, "settings.manage"); name = str(data.get("name") or "").strip(); description = str(data.get("description") or "").strip()
    if len(name) < 2: raise HTTPException(400, "Ingrese un nombre para el rol")
    if name.lower() == "administrador": raise HTTPException(400, "El rol Administrador está reservado")
    try:
        with connect() as database:
            item = database.execute("INSERT INTO roles(name,description) VALUES(%s,%s) RETURNING id", (name, description or f"Rol {name}")).fetchone()
            audit(database, "role", item["id"], "CREADO", actor["display_name"], name)
    except psycopg.errors.UniqueViolation as exc: raise HTTPException(400, "Ya existe un rol con ese nombre") from exc
    return {"id": item["id"], "name": name, "permissions": []}


@app.patch("/api/roles/{role_id}/permissions")
def update_permissions(role_id: int, request: Request, data: PermissionsIn = Body(...)):
    data = data.model_dump()
    actor = authorized(request, "settings.manage"); valid = [item for item in data.get("permissions", []) if item in PERMISSIONS]
    with connect() as database:
        role = database.execute("SELECT name FROM roles WHERE id=%s", (role_id,)).fetchone()
        if not role: raise HTTPException(404, "Rol inexistente")
        if role["name"] == "Administrador": raise HTTPException(400, "Los permisos del Administrador son obligatorios y no se pueden modificar")
        database.execute("DELETE FROM role_permissions WHERE role_id=%s", (role_id,))
        execute_many(database, "INSERT INTO role_permissions(role_id,permission) VALUES(%s,%s)", [(role_id, item) for item in valid])
        audit(database, "role", role_id, "PERMISOS_ACTUALIZADOS", actor["display_name"], ", ".join(valid))
    return {"ok": True}


@app.get("/api/settings/users")
def users(request: Request):
    authorized(request, "settings.manage")
    with connect() as database:
        return rows(database, "SELECT u.id,u.username,u.email,(u.google_sub IS NOT NULL) google_linked,u.display_name,u.active,u.role_id,r.name role_name FROM users u JOIN roles r ON r.id=u.role_id ORDER BY u.display_name")


@app.post("/api/settings/users", status_code=201)
def create_user(request: Request, data: UserCreateIn = Body(...)):
    data = data.model_dump()
    actor = authorized(request, "settings.manage"); email = valid_corporate_email(data.get("email"))
    if not email: raise HTTPException(400, "El correo debe pertenecer a @portoservicios.com.uy")
    if data.get("password") and len(data["password"]) < 12: raise HTTPException(400, "La contraseña alternativa debe tener al menos 12 caracteres")
    username = str(data.get("username") or email.split("@", 1)[0]).strip().lower(); password = data.get("password") or secrets.token_urlsafe(32)
    try:
        with connect() as database:
            item = database.execute("INSERT INTO users(username,email,display_name,password_hash,role_id,active) VALUES(%s,%s,%s,%s,%s,TRUE) RETURNING id", (username, email, data["display_name"], hash_password(password), int(data["role_id"]))).fetchone()
            audit(database, "user", item["id"], "CREADO", actor["display_name"], email)
    except (psycopg.errors.UniqueViolation, psycopg.errors.ForeignKeyViolation) as exc: raise HTTPException(400, "Ese usuario, correo o rol no es válido") from exc
    return {"ok": True}


@app.patch("/api/users/{user_id}")
def update_user(user_id: int, request: Request, data: UserUpdateIn = Body(...)):
    data = data.model_dump()
    actor = authorized(request, "settings.manage"); email = valid_corporate_email(data.get("email"))
    if not email: raise HTTPException(400, "El correo debe pertenecer a @portoservicios.com.uy")
    if data.get("password") and len(data["password"]) < 12: raise HTTPException(400, "La contraseña debe tener al menos 12 caracteres")
    try:
        with connect() as database:
            previous = database.execute("SELECT email FROM users WHERE id=%s", (user_id,)).fetchone()
            if not previous: raise HTTPException(404, "Usuario inexistente")
            ensure_active_admin_survives(database, user_id, int(data["role_id"]), bool(data.get("active", True)))
            google_sub = None if str(previous["email"] or "").lower() != email else database.execute("SELECT google_sub FROM users WHERE id=%s", (user_id,)).fetchone()["google_sub"]
            if data.get("password"):
                database.execute("UPDATE users SET display_name=%s,email=%s,role_id=%s,active=%s,password_hash=%s,google_sub=%s WHERE id=%s", (data["display_name"], email, int(data["role_id"]), bool(data.get("active", True)), hash_password(data["password"]), google_sub, user_id))
            else:
                database.execute("UPDATE users SET display_name=%s,email=%s,role_id=%s,active=%s,google_sub=%s WHERE id=%s", (data["display_name"], email, int(data["role_id"]), bool(data.get("active", True)), google_sub, user_id))
            if data.get("password") or not bool(data.get("active", True)):
                database.execute("DELETE FROM app_sessions WHERE user_id=%s", (user_id,))
            audit(database, "user", user_id, "ACTUALIZADO", actor["display_name"], email)
    except psycopg.errors.UniqueViolation as exc: raise HTTPException(400, "Ese correo corporativo ya está asignado") from exc
    return {"ok": True}


@app.get("/api/settings/google-access")
def google_access(request: Request):
    authorized(request, "settings.manage")
    with connect() as database: client_id = setting(database, "google_client_id")
    return {"client_id": client_id, "allowed_domain": ALLOWED_GOOGLE_DOMAIN, "enabled": bool(client_id)}


@app.patch("/api/settings/google-access")
def update_google_access(request: Request, data: GoogleAccessIn = Body(...)):
    data = data.model_dump()
    actor = authorized(request, "settings.manage"); client_id = str(data.get("client_id") or "").strip()
    if client_id and not re.fullmatch(r"\d+-[a-z0-9_-]+\.apps\.googleusercontent\.com", client_id, re.I): raise HTTPException(400, "El ID de cliente OAuth de Google no tiene un formato válido")
    with connect() as database:
        database.execute("INSERT INTO app_settings(key,value) VALUES('google_client_id',%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value", (client_id,))
        audit(database, "settings", 1, "GOOGLE_ACTUALIZADO", actor["display_name"], "Activado" if client_id else "Desactivado")
    return {"ok": True, "enabled": bool(client_id)}


@app.get("/api/settings/version")
def version(request: Request):
    authorized(request, "settings.manage")
    return {"version": APP_VERSION, "released": "2026-09-09", "notes": VERSION_NOTES}

@app.get("/api/schedules/people")
def schedule_people_list(request: Request):
    actor=authorized(request, "schedules.view")
    with connect() as database:
        return [p for p in schedule_people(database) if actor['role_name'] in ('Supervisor','Administrador') or p['id']==actor['id']]

@app.get("/api/schedules")
def schedules(request: Request, week: str = "", date_from: str = "", date_to: str = "", employee_id: int | None = None, role: str = "", q: str = ""):
    actor=authorized(request, "schedules.view")
    if actor['role_name'] not in ('Supervisor','Administrador'):employee_id=actor['id']
    try:
        if week: week=schedule_week_start(week).isoformat()
        if date_from: datetime.strptime(date_from,"%Y-%m-%d")
        if date_to: datetime.strptime(date_to,"%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(400, "El período indicado no es válido") from exc
    with connect() as database:
        return filtered_schedules(database,week,date_from,date_to,employee_id,role,q)

@app.get("/api/reports/schedules.csv")
def schedules_report(request: Request, week: str = "", date_from: str = "", date_to: str = "", employee_id: int | None = None, role: str = "", q: str = ""):
    actor=authorized(request, "reports.export")
    if actor['role_name'] not in ('Supervisor','Administrador'):employee_id=actor['id']
    try:
        if week: week=schedule_week_start(week).isoformat()
        if date_from: datetime.strptime(date_from,"%Y-%m-%d")
        if date_to: datetime.strptime(date_to,"%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(400, "El período indicado no es válido") from exc
    with connect() as database:
        content=report_csv_bytes("schedules",filtered_schedules(database,week,date_from,date_to,employee_id,role,q))
    return Response(content=content,media_type="text/csv; charset=utf-8",headers={"Content-Disposition":'attachment; filename="reporte_horarios.csv"'})


@app.get("/api/settings/quote-rules")
def quote_rules(request: Request):
    authorized(request, "settings.manage")
    with connect() as database: return database.execute("SELECT * FROM quote_rules WHERE id=1").fetchone()


@app.patch("/api/settings/quote-rules")
def update_quote_rules(request: Request, data: QuoteRulesIn = Body(...)):
    data = data.model_dump(exclude_unset=True)
    actor = authorized(request, "settings.manage")
    legacy_fields = ["insured_base", "uninsured_base", "special_insured_base", "special_uninsured_base", "gavilan_base", "included_km", "extra_km_rate", "special_extra_km_rate"]
    fields = legacy_fields + [field for field in QUOTE_RULE_EXTRA_COLUMNS if field in data]
    with connect() as database:
        current = database.execute("SELECT * FROM quote_rules WHERE id=1").fetchone()
        try:
            values = [float(data[field] if field in data else current[field]) for field in fields]
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(400, "Todas las tarifas deben ser numéricas") from exc
        if any(value < 0 for value in values): raise HTTPException(400, "Las tarifas no pueden ser negativas")
        assignments = ",".join(f"{field}=%s" for field in fields)
        database.execute(f"UPDATE quote_rules SET {assignments},updated_at=%s WHERE id=1", values + [now()])
        audit(database, "quote_rules", 1, "ACTUALIZADO", actor["display_name"])
    return {"ok": True}


@app.get("/api/settings/tolls")
def tolls(request: Request):
    authorized(request, "settings.manage")
    with connect() as database:
        return rows(database, "SELECT * FROM toll_catalog ORDER BY name")


@app.post("/api/settings/tolls", status_code=201)
def create_toll(request: Request, data: TollIn = Body(...)):
    data=data.model_dump(); actor=authorized(request, "settings.manage")
    with connect() as database:
        item=database.execute("INSERT INTO toll_catalog(name,latitude,longitude,price,active,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id",(data['name'].strip(),data['latitude'],data['longitude'],data['price'],data['active'],now(),now())).fetchone()
        audit(database,'toll',item['id'],'CREADO',actor['display_name'],data['name'].strip())
    return {'ok':True}


@app.patch("/api/settings/tolls/{item_id}")
def update_toll(item_id: int, request: Request, data: TollIn = Body(...)):
    data=data.model_dump(); actor=authorized(request, "settings.manage")
    with connect() as database:
        item=database.execute("UPDATE toll_catalog SET name=%s,latitude=%s,longitude=%s,price=%s,active=%s,updated_at=%s WHERE id=%s RETURNING id",(data['name'].strip(),data['latitude'],data['longitude'],data['price'],data['active'],now(),item_id)).fetchone()
        if not item:raise HTTPException(404,'Peaje inexistente')
        audit(database,'toll',item_id,'ACTUALIZADO',actor['display_name'],data['name'].strip())
    return {'ok':True}


@app.delete("/api/settings/tolls/{item_id}")
def delete_toll(item_id: int, request: Request):
    actor=authorized(request, "settings.manage")
    with connect() as database:
        item=database.execute("DELETE FROM toll_catalog WHERE id=%s RETURNING name",(item_id,)).fetchone()
        if not item:raise HTTPException(404,'Peaje inexistente')
        audit(database,'toll',item_id,'ELIMINADO',actor['display_name'],item['name'])
    return {'ok':True}


LISTS = {
    "delays": ("delays.view", "SELECT * FROM delay_zones ORDER BY created_at DESC LIMIT 5000"),
    "transfers": ("transfers.view", "SELECT * FROM scheduled_transfers ORDER BY scheduled_date,scheduled_time LIMIT 5000"),
    "quotes": ("quotes.view", "SELECT * FROM quotes ORDER BY created_at DESC LIMIT 1000"),
    "standards": ("standards.view", "SELECT * FROM arrival_standards ORDER BY department,zone"),
    "audit": ("audit.view", "SELECT * FROM audit_events ORDER BY created_at DESC LIMIT 500"),
}


def filtered_notices(database, date_from="", date_to="", status="", task="", contact="", q="", limit=None):
    query = "SELECT * FROM notices WHERE TRUE"; values = []
    if date_from: query += " AND created_at >= %s::date"; values.append(date_from)
    if date_to: query += " AND created_at < (%s::date + interval '1 day')"; values.append(date_to)
    if status: query += " AND status=%s"; values.append(status)
    if task: query += " AND COALESCE(task_number,'') ILIKE %s"; values.append(f"%{task}%")
    if contact: query += " AND COALESCE(phone,'') ILIKE %s"; values.append(f"%{contact}%")
    if q:
        query += " AND concat_ws(' ',task_number,phone,notice_type,detail,managed_by,communicated_by,comments) ILIKE %s"; values.append(f"%{q}%")
    query += " ORDER BY created_at DESC"
    if limit: query += f" LIMIT {int(limit)}"
    return rows(database, query, values)


@app.get("/api/notices")
def notices(request: Request, date_from: str = "", date_to: str = "", status: str = "", task: str = "", contact: str = "", q: str = ""):
    authorized(request, "notices.view")
    with connect() as database: return filtered_notices(database, date_from, date_to, status, task, contact, q, 20000)


@app.get("/api/reports/notices.csv")
def notices_report(request: Request, date_from: str = "", date_to: str = "", status: str = "", task: str = "", contact: str = "", q: str = ""):
    authorized(request, "reports.export")
    with connect() as database: content = notice_csv_bytes(filtered_notices(database, date_from, date_to, status, task, contact, q))
    return Response(content=content, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="reporte_avisos.csv"'})


def filtered_report_rows(database, kind, date_from="", date_to="", status="", task="", department="", service="", provider="", created_by="", q=""):
    config = {
        "delays": ("delay_zones", "created_at", ("service", "department", "zone", "message", "agent")),
        "transfers": ("scheduled_transfers", "scheduled_date", ("task_number", "transfer_type", "origin", "destination", "provider", "planner", "comments")),
        "quotes": ("quotes", "created_at", ("task_number", "origin_input", "destination_input", "mobile_input", "created_by")),
        "audit": ("audit_events", "created_at", ("entity", "action", "actor", "detail")),
    }
    if kind not in config: raise HTTPException(404, "Reporte inexistente")
    table, date_field, search_fields = config[kind]; query = f"SELECT * FROM {table} WHERE TRUE"; values = []
    if date_from: query += f" AND {date_field} >= %s::date"; values.append(date_from)
    if date_to: query += f" AND {date_field} < (%s::date + interval '1 day')"; values.append(date_to)
    allowed_fields = set(search_fields)
    if kind in ("delays", "transfers"): allowed_fields.add("status")
    for field, value in (("status", status), ("task_number", task), ("department", department), ("service", service), ("provider", provider), ("created_by", created_by)):
        if value and field in allowed_fields: query += f" AND COALESCE({field},'') ILIKE %s"; values.append(f"%{value}%")
    if q:
        query += " AND concat_ws(' '," + ",".join(search_fields) + ") ILIKE %s"; values.append(f"%{q}%")
    query += f" ORDER BY {date_field} DESC"
    return rows(database, query, values)


@app.get("/api/reports/{kind}.csv")
def operational_report(kind: str, request: Request, date_from: str = "", date_to: str = "", status: str = "", task: str = "", department: str = "", service: str = "", provider: str = "", created_by: str = "", q: str = ""):
    authorized(request, "reports.export")
    if kind == "audit": authorized(request, "audit.view")
    with connect() as database: content = report_csv_bytes(kind, filtered_report_rows(database, kind, date_from, date_to, status, task, department, service, provider, created_by, q))
    names = {"delays": "demoras", "transfers": "programados", "quotes": "cotizaciones", "audit": "auditoria"}
    if kind not in names: raise HTTPException(404, "Reporte inexistente")
    return Response(content=content, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="reporte_{names[kind]}.csv"'})


@app.get("/api/dashboard")
def dashboard(request: Request):
    authorized(request, "dashboard.view")
    with connect() as database:
        return {"notices_open": database.execute("SELECT count(*) total FROM notices WHERE status NOT IN ('RESUELTO','CANCELADO')").fetchone()["total"], "delays_active": database.execute("SELECT count(*) total FROM delay_zones WHERE status='VIGENTE'").fetchone()["total"], "transfers_pending": database.execute("SELECT count(*) total FROM scheduled_transfers WHERE status IN ('PENDIENTE','CONFIRMADO','SIN_ASIGNAR','ASIGNADO')").fetchone()["total"]}


@app.get("/api/{kind}")
def list_items(kind: str, request: Request):
    if kind not in LISTS: raise HTTPException(404, "Ruta inexistente")
    permission, query = LISTS[kind]; authorized(request, permission)
    with connect() as database: return rows(database, query)


@app.post("/api/schedules/copy-week", status_code=201)
def copy_schedule_week(request: Request, data: ScheduleCopyIn = Body(...)):
    data=data.model_dump();actor=authorized(request,"schedules.manage")
    source_week=schedule_week_start(data["source_week"]);target_week=schedule_week_start(data["target_week"]);role=str(data.get("role") or "").strip()
    if source_week==target_week:raise HTTPException(400,"La semana de origen y destino deben ser diferentes")
    if role and role not in SCHEDULE_ROLES:raise HTTPException(400,"El rol indicado no pertenece al equipo operativo")
    with connect() as database:
        query="""SELECT s.*,r.name current_role FROM work_schedules s JOIN users u ON u.id=s.user_id JOIN roles r ON r.id=u.role_id
            WHERE s.week_start=%s AND s.schedule_date BETWEEN %s AND %s AND u.active=TRUE AND r.name=ANY(%s)""";values=[source_week,source_week,source_week+timedelta(days=6),list(SCHEDULE_ROLES)]
        if data.get("employee_id") is not None:query+=" AND s.user_id=%s";values.append(data["employee_id"])
        if role:query+=" AND r.name=%s";values.append(role)
        query+=" ORDER BY s.user_id,s.schedule_date,s.start_time,s.id"
        source_rows=database.execute(query,values).fetchall();copied=0;skipped=0;stamp=now()
        for source in source_rows:
            target_date=target_week+timedelta(days=(schedule_date_value(source["schedule_date"])-source_week).days)
            lock_schedule_slot(database,source["user_id"],target_date)
            if source["start_time"] is not None and schedule_time_text(source["start_time"])==schedule_time_text(source["end_time"]):
                skipped+=1;continue
            if postgres_schedule_conflict(database,source["user_id"],target_date,source["shift_name"],source["start_time"],source["end_time"]):
                skipped+=1;continue
            database.execute("""INSERT INTO work_schedules(user_id,schedule_date,week_start,role_name,shift_name,start_time,end_time,notes,created_by,created_at,updated_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",(source["user_id"],target_date,target_week,source["current_role"],source["shift_name"],source["start_time"],source["end_time"],source["notes"],actor["display_name"],stamp,stamp));copied+=1
        if copied or skipped:audit(database,"schedule_week",int(target_week.strftime("%Y%m%d")),"COPIA_SEMANAL",actor["display_name"],f"{source_week.isoformat()} → {target_week.isoformat()}; copiados={copied}; omitidos={skipped}")
    return {"copied":copied,"skipped":skipped,"source_week":source_week.isoformat(),"target_week":target_week.isoformat()}


@app.post("/api/schedules", status_code=201)
def create_schedule(request: Request, data: dict = Body(...)):
    data=validated_body(ScheduleIn,data); actor=authorized(request,"schedules.manage")
    if (data.get("start_time") is None)!=(data.get("end_time") is None): raise HTTPException(400,"Complete ambas horas o deje ambas vacías")
    if data.get("start_time") is not None and schedule_time_text(data["start_time"])==schedule_time_text(data["end_time"]):raise HTTPException(400,"La hora de inicio y fin no pueden ser iguales")
    schedule_date=data["schedule_date"]; shift_name=str(data.get("shift_name") or "").strip()
    if len(shift_name)<2: raise HTTPException(400,"Indique el turno del horario")
    with connect() as database:
        person=database.execute("SELECT u.id,r.name role_name FROM users u JOIN roles r ON r.id=u.role_id WHERE u.id=%s AND u.active=TRUE AND r.name=ANY(%s)",(data["user_id"],list(SCHEDULE_ROLES))).fetchone()
        if not person: raise HTTPException(400,"La persona debe ser un usuario activo del equipo operativo")
        lock_schedule_slot(database,data["user_id"],schedule_date)
        conflict=postgres_schedule_conflict(database,data["user_id"],schedule_date,shift_name,data.get("start_time"),data.get("end_time"))
        if conflict:raise HTTPException(409,schedule_conflict_message(conflict))
        item=database.execute("""INSERT INTO work_schedules(user_id,schedule_date,week_start,role_name,shift_name,start_time,end_time,notes,created_by,created_at,updated_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",(data["user_id"],schedule_date,schedule_week_start(schedule_date),person["role_name"],shift_name,data.get("start_time"),data.get("end_time"),data.get("notes"),actor["display_name"],now(),now())).fetchone()
        audit(database,"schedule",item["id"],"CREADO",actor["display_name"],f"{schedule_date.isoformat()} · {person['role_name']}")
        return schedule_item(database,item["id"])


CREATE_CONFIG = {
    "notices": ("notices.create", "notices", ["task_number", "phone", "notice_type", "audience", "detail", "communicated_by", "managed_by", "status", "comments"], "notice"),
    "delays": ("delays.create", "delay_zones", ["service", "department", "zone", "message", "minutes", "status", "agent"], "delay"),
    "transfers": ("transfers.create", "scheduled_transfers", ["task_number", "transfer_type", "scheduled_date", "scheduled_time", "origin", "destination", "provider", "planner", "status", "comments"], "transfer"),
}


@app.post("/api/{kind}", status_code=201)
def create_item(kind: str, request: Request, data: dict = Body(...)):
    if kind not in CREATE_CONFIG: raise HTTPException(404, "Ruta inexistente")
    permission, table, fields, entity = CREATE_CONFIG[kind]; user = authorized(request, permission)
    data = validated_body({"notices": NoticeIn, "delays": DelayIn, "transfers": TransferIn}[kind], data)
    actor_field = {"notices": "communicated_by", "delays": "agent", "transfers": "planner"}[kind]; data[actor_field] = user["display_name"]
    defaults = {"audience": "TODOS", "status": "PENDIENTE", "service": "TODAS", "message": "Margen de"}
    values = [data.get(field, defaults.get(field)) for field in fields]; stamp = now(); extra = ["created_at", "updated_at"] if table == "notices" else ["created_at"]
    columns = fields + extra; values += [stamp] * len(extra); placeholders = ",".join(["%s"] * len(columns))
    with connect() as database:
        item = database.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders}) RETURNING *", values).fetchone()
        audit(database, entity, item["id"], "CREADO", user["display_name"])
    return item


@app.post("/api/quotes/calculate", status_code=201)
def calculate_quote(request: Request, data: QuoteIn = Body(...)):
    data = data.model_dump()
    user = authorized(request, "quotes.create"); uninsured = bool(data.get("uninsured")); special = bool(data.get("special")); gavilan = bool(data.get("gavilan")); manual = bool(data.get("manual_distance"))
    if gavilan and special: raise HTTPException(400, "Gavilán no es compatible con Especial")
    if not manual and (not data.get("origin") or not data.get("destination")): raise HTTPException(400, "Origen y destino son obligatorios para la cotización automática")
    try:
        segments = []
        manual_toll_count = 0
        if manual:
            trip_km = float(data.get("manual_trip_km") or 0); mobile_km = float(data.get("manual_mobile_km") or 0) if data.get("include_mobile") else 0
            if trip_km <= 0 or mobile_km < 0: raise ValueError("La distancia manual debe ser mayor a cero")
            if data.get("include_mobile") and mobile_km <= 0: raise ValueError("Ingrese los kilómetros desde la salida del móvil hasta el origen")
            manual_toll_count = int(data.get("manual_toll_count") or 0) if data.get("include_tolls") else 0
            if data.get("include_tolls") and manual_toll_count < 1: raise ValueError("Ingrese una cantidad válida de peajes")
        else:
            trip = route_data(parse_coordinates(data["origin"]), parse_coordinates(data["destination"])); trip_km = trip["km"]; mobile_km = 0
            segments.append({"label": "Traslado: origen → destino", "color": "#2878b5", "coordinates": trip["coordinates"]})
            if data.get("include_mobile"):
                mobile = route_data(parse_coordinates(data["mobile_origin"]), parse_coordinates(data["origin"])); mobile_km = mobile["km"]
                segments.insert(0, {"label": "Salida de la grúa → origen del cliente", "color": "#d8872f", "coordinates": mobile["coordinates"]})
        with connect() as database:
            rule = database.execute("SELECT * FROM quote_rules WHERE id=1").fetchone(); base = rule["gavilan_uninsured_base" if uninsured else "gavilan_insured_base"] if gavilan else rule["special_uninsured_base"] if special and uninsured else rule["special_insured_base"] if special else rule["uninsured_base"] if uninsured else rule["insured_base"]
            rate = rule["special_extra_km_uninsured_rate" if uninsured else "special_extra_km_insured_rate"] if special else rule["extra_km_uninsured_rate" if uninsured else "extra_km_insured_rate"]
            toll_rate=rule["toll_uninsured" if uninsured else "toll_insured"]
            if manual:
                toll_price=round(manual_toll_count*toll_rate,2)
                toll_passes=[] if not manual_toll_count else [{"name":f"Peajes manuales ({manual_toll_count})","segment":"Cantidad ingresada manualmente","price":toll_price}]
                toll_count=manual_toll_count
            else:
                catalog=rows(database,"SELECT * FROM toll_catalog WHERE active=TRUE")
                toll_passes=detect_toll_passes(segments,catalog,toll_rate);toll_price=round(sum(item['price'] for item in toll_passes),2);toll_count=len(toll_passes)
            total_km = round(trip_km + mobile_km, 2); extra_km = max(0, math.ceil(total_km - rule["included_km"])); extra_price = extra_km * rate; total_price = base + extra_price + toll_price; created_at = now(); task = str(data.get("task_number") or "").strip()
            item = database.execute("""INSERT INTO quotes(task_number,origin_input,destination_input,mobile_input,uninsured,special,gavilan,trip_km,mobile_km,total_km,included_km,extra_km,base_price,extra_price,toll_count,toll_details,toll_price,total_price,created_by,created_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""", (task or None, data.get("origin") or "Cotización manual", data.get("destination") or "Cotización manual", data.get("mobile_origin"), uninsured, special, gavilan, trip_km, mobile_km, total_km, rule["included_km"], extra_km, base, extra_price,toll_count,json.dumps(toll_passes,ensure_ascii=False),toll_price,total_price,user["display_name"],created_at)).fetchone()
            audit(database, "quote", item["id"], "COTIZADO", user["display_name"], f"${total_price:.0f}; peajes={toll_count}")
        customer_type = ("No asegurado" if uninsured else "Asegurado") + (" · Gavilán" if gavilan else " · Especial" if special else "")
        return {"id": item["id"], "task_number": task, "created_at": created_at, "origin_input": data.get("origin") or "Cotización manual", "destination_input": data.get("destination") or "Cotización manual", "mobile_input": data.get("mobile_origin"), "uninsured": uninsured, "special": special, "gavilan": gavilan, "mode": "manual" if manual else "automatic", "trip_km": trip_km, "mobile_km": mobile_km, "total_km": total_km, "included_km": rule["included_km"], "extra_km": extra_km, "base_price": base, "extra_rate": rate, "extra_price": extra_price, "toll_count":toll_count,"toll_details":toll_passes,"toll_price":toll_price,"total_price": total_price, "route_segments": segments, "customer_type": customer_type}
    except ValueError as exc: raise HTTPException(400, str(exc)) from exc


@app.patch("/api/notices/{item_id}/status")
def notice_status(item_id: int, request: Request, data: StatusIn = Body(...)):
    data = data.model_dump()
    user = authorized(request, "notices.manage")
    with connect() as database:
        item = database.execute("UPDATE notices SET status=%s,managed_by=COALESCE(%s,managed_by),comments=COALESCE(%s,comments),updated_at=%s WHERE id=%s RETURNING *", (data["status"], data.get("managed_by"), data.get("comments"), now(), item_id)).fetchone()
        if not item: raise HTTPException(404, "Aviso inexistente")
        audit(database, "notice", item_id, "CAMBIO_ESTADO", user["display_name"], data["status"])
    return item


@app.patch("/api/delays/{item_id}/normalize")
def normalize_delay(item_id: int, request: Request, data: StatusIn = Body(...)):
    data = data.model_dump()
    user = authorized(request, "delays.normalize")
    with connect() as database:
        item = database.execute("UPDATE delay_zones SET status='NORMALIZADO',normalized_at=%s WHERE id=%s RETURNING *", (now(), item_id)).fetchone()
        if not item: raise HTTPException(404, "Demora inexistente")
        audit(database, "delay", item_id, "CAMBIO_ESTADO", user["display_name"], "NORMALIZADO")
    return item


@app.patch("/api/schedules/{item_id}")
def edit_schedule(item_id: int, request: Request, data: dict = Body(...)):
    data=validated_body(ScheduleIn,data); actor=authorized(request,"schedules.manage")
    if (data.get("start_time") is None)!=(data.get("end_time") is None): raise HTTPException(400,"Complete ambas horas o deje ambas vacías")
    if data.get("start_time") is not None and schedule_time_text(data["start_time"])==schedule_time_text(data["end_time"]):raise HTTPException(400,"La hora de inicio y fin no pueden ser iguales")
    schedule_date=data["schedule_date"];shift_name=str(data.get("shift_name") or "").strip()
    if len(shift_name)<2: raise HTTPException(400,"Indique el turno del horario")
    with connect() as database:
        person=database.execute("SELECT u.id,r.name role_name FROM users u JOIN roles r ON r.id=u.role_id WHERE u.id=%s AND r.name=ANY(%s)",(data["user_id"],list(SCHEDULE_ROLES))).fetchone()
        if not person: raise HTTPException(400,"La persona debe pertenecer al equipo operativo")
        current=database.execute("SELECT id FROM work_schedules WHERE id=%s FOR UPDATE",(item_id,)).fetchone()
        if not current: raise HTTPException(404,"Horario inexistente")
        lock_schedule_slot(database,data["user_id"],schedule_date)
        conflict=postgres_schedule_conflict(database,data["user_id"],schedule_date,shift_name,data.get("start_time"),data.get("end_time"),item_id)
        if conflict:raise HTTPException(409,schedule_conflict_message(conflict))
        database.execute("""UPDATE work_schedules SET user_id=%s,schedule_date=%s,week_start=%s,role_name=%s,shift_name=%s,start_time=%s,end_time=%s,notes=%s,updated_at=%s WHERE id=%s""",(data["user_id"],schedule_date,schedule_week_start(schedule_date),person["role_name"],shift_name,data.get("start_time"),data.get("end_time"),data.get("notes"),now(),item_id))
        audit(database,"schedule",item_id,"EDITADO",actor["display_name"],f"{schedule_date.isoformat()} · {person['role_name']}")
        return schedule_item(database,item_id)

@app.delete("/api/schedules/{item_id}")
def delete_schedule(item_id: int, request: Request):
    actor=authorized(request,"schedules.manage")
    with connect() as database:
        item=database.execute("SELECT schedule_date,shift_name FROM work_schedules WHERE id=%s",(item_id,)).fetchone()
        if not item: raise HTTPException(404,"Horario inexistente")
        database.execute("DELETE FROM work_schedules WHERE id=%s",(item_id,)); audit(database,"schedule",item_id,"ELIMINADO",actor["display_name"],f"{item['schedule_date']} · {item['shift_name']}")
    return {"ok":True}


@app.patch("/api/transfers/{item_id}/status")
def transfer_status(item_id: int, request: Request, data: StatusIn = Body(...)):
    data = data.model_dump()
    user = authorized(request, "transfers.manage")
    with connect() as database:
        item = database.execute("UPDATE scheduled_transfers SET status=%s WHERE id=%s RETURNING *", (data["status"], item_id)).fetchone()
        if not item: raise HTTPException(404, "Programado inexistente")
        audit(database, "transfer", item_id, "CAMBIO_ESTADO", user["display_name"], data["status"])
    return item


@app.patch("/api/transfers/{item_id}")
def edit_transfer(item_id: int, request: Request, data: TransferEdit = Body(...)):
    data = data.model_dump()
    user = authorized(request, "transfers.manage"); fields = ["task_number", "transfer_type", "scheduled_date", "scheduled_time", "origin", "destination", "provider", "comments"]
    with connect() as database:
        item = database.execute(f"UPDATE scheduled_transfers SET {','.join(field+'=%s' for field in fields)} WHERE id=%s RETURNING *", [data.get(field) for field in fields] + [item_id]).fetchone()
        if not item: raise HTTPException(404, "Registro inexistente")
        audit(database, "transfer", item_id, "EDITADO", user["display_name"], data.get("task_number", ""))
    return item


@app.delete("/api/transfers/{item_id}")
def delete_transfer(item_id: int, request: Request):
    user = authorized(request, "transfers.manage")
    with connect() as database:
        item = database.execute("DELETE FROM scheduled_transfers WHERE id=%s RETURNING task_number", (item_id,)).fetchone()
        if not item: raise HTTPException(404, "Programado inexistente")
        audit(database, "transfer", item_id, "ELIMINADO", user["display_name"], item["task_number"])
    return {"ok": True}
    RateLimitState,
