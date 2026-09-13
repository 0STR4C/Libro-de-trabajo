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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from psycopg.rows import dict_row
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .application import (
    APP_VERSION,
    DEFAULT_ROLES,
    PERMISSIONS,
    SCHEDULE_ROLES,
    current_release_payload,
    NOTICE_MANAGE_PERMISSIONS,
)
from .identity import (
    ALLOWED_GOOGLE_DOMAIN,
    parse_coordinates,
    route_data,
    valid_corporate_email,
    verify_google_id_token,
)
from .notices import (
    NOTICE_CLOSED_STATUSES,
    NOTICE_STATUSES,
    notice_duplicates,
    notice_update_permissions,
)
from .migrations import reconcile_migration_checksums
from .quotes import (
    QUOTE_RULE_EXTRA_COLUMNS,
    QUOTE_RULE_LEGACY_COPIES,
    calculate_extra_km,
    round_currency,
    round_distance,
    validate_quote_rule_values,
    validate_manual_toll_count,
    validate_manual_distances,
)
from .tolls import detect_toll_passes
from .delays import DEPARTMENTS, DELAY_SERVICES, STANDARD_SERVICES, clean_delay, clean_standard, enrich_delay, normalized_key, split_zones, standard_availability, zone_matches
from .dashboard import build_dashboard_payload
from .reporting import filter_report_records, normalized_report_filters, notice_csv_bytes, report_csv_bytes
from .scheduling import find_schedule_conflict, schedule_conflict_message, schedule_date_value, schedule_time_text
from .schemas import ArrivalStandardIn, DelayIn, DelayNormalizeIn, DelayVerifyIn, GoogleAccessIn, GoogleLoginIn, LoginIn, NoticeIn, NoticeUpdateIn, PermissionsIn, QuoteIn, QuoteRulesIn, RoleCreateIn, ScheduleCopyIn, ScheduleIn, StandardDecisionIn, StatusIn, TollIn, TransferEdit, TransferIn, TransferStatusIn, UserCreateIn, UserUpdateIn, ZoneCoverageIn
from .transfers import TRANSFER_STATUSES, clean_transfer, normalized_status, validate_transition
from .security import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    RateLimitState,
    SESSION_COOKIE_NAME,
    csrf_token_for_session,
    hash_password,
    next_rate_limit_state,
    password_needs_rehash,
    validate_runtime_environment,
    verify_password,
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
ALLOWED_HOSTS = [item.strip() for item in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if item.strip()]
ALLOWED_ORIGINS = {item.strip().rstrip("/") for item in os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",") if item.strip()}
MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", str(1024 * 1024)))
ENABLE_API_DOCS = os.getenv("ENABLE_API_DOCS", "true" if APP_ENV == "development" else "false").strip().lower() == "true"
GOOGLE_NONCES: dict[str, float] = {}

SCHEMA = """
CREATE TABLE IF NOT EXISTS notices(id BIGSERIAL PRIMARY KEY,task_number TEXT,phone TEXT,notice_type TEXT NOT NULL,audience TEXT NOT NULL DEFAULT 'TODOS',detail TEXT NOT NULL,communicated_by TEXT NOT NULL,managed_by TEXT,status TEXT NOT NULL DEFAULT 'PENDIENTE',comments TEXT,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS delay_zones(id BIGSERIAL PRIMARY KEY,service TEXT NOT NULL,department TEXT NOT NULL,zone TEXT NOT NULL,message TEXT NOT NULL,minutes INTEGER,status TEXT NOT NULL,agent TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL,normalized_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS scheduled_transfers(id BIGSERIAL PRIMARY KEY,task_number TEXT NOT NULL,transfer_type TEXT NOT NULL,scheduled_date DATE NOT NULL,scheduled_time TIME,origin TEXT NOT NULL,destination TEXT NOT NULL,provider TEXT,responsible TEXT,planner TEXT NOT NULL,status TEXT NOT NULL,comments TEXT,completion_note TEXT,cancellation_reason TEXT,assigned_at TIMESTAMPTZ,started_at TIMESTAMPTZ,completed_at TIMESTAMPTZ,cancelled_at TIMESTAMPTZ,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,updated_by TEXT);
CREATE TABLE IF NOT EXISTS arrival_standards(id BIGSERIAL PRIMARY KEY,department TEXT NOT NULL,zone TEXT NOT NULL,service TEXT NOT NULL,minutes_min INTEGER,minutes_max INTEGER,note TEXT);
CREATE TABLE IF NOT EXISTS audit_events(id BIGSERIAL PRIMARY KEY,entity TEXT NOT NULL,entity_id BIGINT NOT NULL,action TEXT NOT NULL,actor TEXT NOT NULL,detail TEXT,created_at TIMESTAMPTZ NOT NULL,actor_id BIGINT,actor_name TEXT,before_data TEXT,after_data TEXT,correlation_id TEXT,source TEXT NOT NULL DEFAULT 'web');
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
CREATE TABLE IF NOT EXISTS quotes(id BIGSERIAL PRIMARY KEY,task_number TEXT,origin_input TEXT NOT NULL,destination_input TEXT NOT NULL,mobile_input TEXT,uninsured BOOLEAN NOT NULL,special BOOLEAN NOT NULL,gavilan BOOLEAN NOT NULL,trip_km DOUBLE PRECISION NOT NULL,mobile_km DOUBLE PRECISION NOT NULL,total_km DOUBLE PRECISION NOT NULL,included_km DOUBLE PRECISION NOT NULL,extra_km DOUBLE PRECISION NOT NULL,base_price DOUBLE PRECISION NOT NULL,extra_price DOUBLE PRECISION NOT NULL,toll_count INTEGER NOT NULL DEFAULT 0,toll_details TEXT NOT NULL DEFAULT '[]',toll_price DOUBLE PRECISION NOT NULL DEFAULT 0,total_price DOUBLE PRECISION NOT NULL,pricing_snapshot TEXT NOT NULL DEFAULT '{}',created_by TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL);
"""
NOTICE_EVENTS_SCHEMA="""
CREATE TABLE IF NOT EXISTS notice_events(id BIGSERIAL PRIMARY KEY,notice_id BIGINT NOT NULL REFERENCES notices(id) ON DELETE CASCADE,event_type TEXT NOT NULL,actor TEXT NOT NULL,detail TEXT,previous_value TEXT,new_value TEXT,comment TEXT,created_at TIMESTAMPTZ NOT NULL);
CREATE INDEX IF NOT EXISTS notice_events_notice_idx ON notice_events(notice_id,created_at DESC,id DESC);
"""
TRANSFER_EVENTS_SCHEMA="""
CREATE TABLE IF NOT EXISTS transfer_events(id BIGSERIAL PRIMARY KEY,transfer_id BIGINT NOT NULL REFERENCES scheduled_transfers(id) ON DELETE CASCADE,event_type TEXT NOT NULL,actor TEXT NOT NULL,previous_status TEXT,new_status TEXT,note TEXT,created_at TIMESTAMPTZ NOT NULL);
CREATE INDEX IF NOT EXISTS transfer_events_transfer_idx ON transfer_events(transfer_id,created_at DESC,id DESC);
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


def validated_business_data(cleaner, data):
    try:
        return cleaner(data)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


def setting(database, key, default=""):
    item = database.execute("SELECT value FROM app_settings WHERE key=%s", (key,)).fetchone()
    return item["value"] if item else default


def _audit_json(value):
    if value is None:return None
    blocked=("password","token","secret","cookie","google_sub")
    cleaned={key:item for key,item in dict(value).items() if not any(marker in key.casefold() for marker in blocked)} if hasattr(value,"keys") else value
    return json.dumps(cleaned,ensure_ascii=False,sort_keys=True,default=str)


def _audit_snapshot(database,entity,entity_id):
    tables={"notice":"notices","delay":"delay_zones","transfer":"scheduled_transfers","schedule":"work_schedules","quote":"quotes","quote_rules":"quote_rules","toll":"toll_catalog","arrival_standard":"arrival_standards","operational_zone":"operational_zones","user":"users","role":"roles"}
    table=tables.get(entity)
    if not table or not entity_id:return None
    row=database.execute(f"SELECT * FROM {table} WHERE id=%s",(entity_id,)).fetchone()
    if not row:return None
    result=dict(row)
    if entity=="role":result["permissions"]=[item["permission"] for item in database.execute("SELECT permission FROM role_permissions WHERE role_id=%s ORDER BY permission",(entity_id,)).fetchall()]
    return result


def audit(database, entity, entity_id, action, actor, detail="", *, actor_id=None, before=None, after=None, correlation_id=None, source="web"):
    if actor_id is None and actor not in {"Autenticación","Sistema"}:
        match=database.execute("SELECT id FROM users WHERE display_name=%s ORDER BY active DESC,id LIMIT 1",(actor,)).fetchone()
        actor_id=match["id"] if match else None
    if before is None:
        previous=database.execute("SELECT after_data FROM audit_events WHERE entity=%s AND entity_id=%s AND after_data IS NOT NULL ORDER BY id DESC LIMIT 1",(entity,entity_id)).fetchone()
        if previous:
            try:before=json.loads(previous["after_data"])
            except (TypeError,ValueError):before=None
    if after is None:after=_audit_snapshot(database,entity,entity_id)
    database.execute(
        """INSERT INTO audit_events(entity,entity_id,action,actor,detail,created_at,actor_id,actor_name,before_data,after_data,correlation_id,source)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (entity,entity_id,action,actor,detail,now(),actor_id,actor,_audit_json(before),_audit_json(after),correlation_id or secrets.token_hex(12),source),
    )


def record_notice_event(database, notice_id, event_type, actor, detail="", previous_value=None, new_value=None, comment=None):
    database.execute(
        """INSERT INTO notice_events(notice_id,event_type,actor,detail,previous_value,new_value,comment,created_at)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
        (notice_id,event_type,actor,detail,previous_value,new_value,comment,now()),
    )


def record_transfer_event(database, transfer_id, event_type, actor, previous_status=None, new_status=None, note=None):
    database.execute(
        """INSERT INTO transfer_events(transfer_id,event_type,actor,previous_status,new_status,note,created_at)
        VALUES(%s,%s,%s,%s,%s,%s,%s)""",
        (transfer_id,event_type,actor,previous_status,new_status,note,now()),
    )


def transfer_duplicate(database, data, exclude_id=None):
    query = """SELECT * FROM scheduled_transfers WHERE status<>'CANCELADO'
        AND lower(btrim(task_number))=lower(btrim(%s)) AND scheduled_date=%s
        AND scheduled_time IS NOT DISTINCT FROM %s AND lower(btrim(origin))=lower(btrim(%s))
        AND lower(btrim(destination))=lower(btrim(%s))"""
    values = [data["task_number"],data["scheduled_date"],data.get("scheduled_time"),data["origin"],data["destination"]]
    if exclude_id is not None:
        query += " AND id<>%s"; values.append(exclude_id)
    return database.execute(query + " ORDER BY id LIMIT 1", values).fetchone()


def transfer_duplicate_payload(item):
    result=dict(item)
    for field in ("scheduled_date","scheduled_time","created_at","updated_at"):
        value=result.get(field)
        if hasattr(value,"isoformat"):result[field]=value.isoformat()
    return result


def ensure_transfer_responsible(database, responsible):
    if not responsible:
        return
    item=database.execute("""SELECT 1 FROM users u JOIN role_permissions rp ON rp.role_id=u.role_id
        WHERE u.active=TRUE AND rp.permission='transfers.view' AND u.display_name=%s LIMIT 1""",(responsible,)).fetchone()
    if not item:
        raise HTTPException(400,"El responsable debe ser un usuario activo con acceso a Programados")


def filtered_transfers(database, date_from="", date_to="", status="", transfer_type="", provider="", responsible="", task="", q=""):
    query="SELECT * FROM scheduled_transfers WHERE TRUE";values=[]
    if date_from:query+=" AND scheduled_date>=%s::date";values.append(date_from)
    if date_to:query+=" AND scheduled_date<=%s::date";values.append(date_to)
    if status:
        if status.upper()=="ACTIVE":query+=" AND status IN ('SIN_ASIGNAR','ASIGNADO','EN_CURSO')"
        else:query+=" AND status=%s";values.append(normalized_status(status))
    if transfer_type:query+=" AND transfer_type=%s";values.append(transfer_type)
    if provider:query+=" AND COALESCE(provider,'') ILIKE %s";values.append(f"%{provider}%")
    if responsible:query+=" AND COALESCE(responsible,'') ILIKE %s";values.append(f"%{responsible}%")
    if task:query+=" AND task_number ILIKE %s";values.append(f"%{task}%")
    if q:
        query+=" AND concat_ws(' ',task_number,transfer_type,origin,destination,provider,responsible,planner,comments) ILIKE %s";values.append(f"%{q}%")
    query+=" ORDER BY scheduled_date,scheduled_time NULLS LAST,id LIMIT 20000"
    return rows(database,query,values)


def filtered_operational_records(database,kind,filters=None,managed_by=""):
    table={"notices":"notices","delays":"delay_zones","transfers":"scheduled_transfers","quotes":"quotes","audit":"audit_events"}[kind]
    items=rows(database,f"SELECT * FROM {table}")
    if kind=="delays":items=[enrich_delay(item) for item in items]
    return filter_report_records(kind,items,filters or {},managed_by=managed_by)


def initialize():
    with connect() as database:
        database.execute(SCHEMA)
        database.execute(NOTICE_EVENTS_SCHEMA)
        database.execute(TRANSFER_EVENTS_SCHEMA)
        database.execute("ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS actor_id BIGINT")
        database.execute("ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS actor_name TEXT")
        database.execute("ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS before_data TEXT")
        database.execute("ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS after_data TEXT")
        database.execute("ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS correlation_id TEXT")
        database.execute("ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'web'")
        if not database.execute("SELECT 1 FROM schema_migrations WHERE key=%s",("audit_contract_v2",)).fetchone():
            database.execute("UPDATE audit_events SET actor_name=COALESCE(actor_name,actor),source=CASE WHEN correlation_id IS NULL THEN 'migration' ELSE COALESCE(source,'web') END,correlation_id=COALESCE(correlation_id,'legacy-'||id::text)")
            database.execute("UPDATE audit_events a SET actor_id=(SELECT min(u.id) FROM users u WHERE u.display_name=a.actor_name) WHERE actor_id IS NULL")
            database.execute("INSERT INTO schema_migrations(key,applied_at) VALUES(%s,%s)",("audit_contract_v2",now()))
        database.execute("CREATE INDEX IF NOT EXISTS audit_entity_record_idx ON audit_events(entity,entity_id,created_at DESC,id DESC)")
        database.execute("CREATE INDEX IF NOT EXISTS audit_actor_idx ON audit_events(actor_id,created_at DESC,id DESC)")
        database.execute("""CREATE OR REPLACE FUNCTION prevent_audit_event_changes() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'El registro de auditoría es inmutable'; END; $$""")
        database.execute("""DO $audit$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='audit_events_no_changes') THEN
                CREATE TRIGGER audit_events_no_changes BEFORE UPDATE OR DELETE ON audit_events
                FOR EACH ROW EXECUTE FUNCTION prevent_audit_event_changes();
            END IF;
        END $audit$""")
        from .wfm import SCHEMA as WFM_SCHEMA, ensure_schema as ensure_wfm_schema
        database.execute(WFM_SCHEMA)
        ensure_wfm_schema(database, postgres=True)
        database.execute("ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS checksum TEXT")
        if not database.execute("SELECT 1 FROM schema_migrations WHERE key=%s", ("notice_events_v1",)).fetchone():
            database.execute("""INSERT INTO notice_events(notice_id,event_type,actor,detail,created_at)
                SELECT entity_id,action,actor,detail,created_at FROM audit_events WHERE entity='notice' ORDER BY id""")
            database.execute("""INSERT INTO notice_events(notice_id,event_type,actor,detail,new_value,comment,created_at)
                SELECT n.id,'CREADO',n.communicated_by,concat_ws(' · ',n.notice_type,n.audience),n.status,n.comments,n.created_at
                FROM notices n WHERE NOT EXISTS(SELECT 1 FROM notice_events e WHERE e.notice_id=n.id)""")
            database.execute("INSERT INTO schema_migrations(key,applied_at,checksum) VALUES(%s,%s,%s)", ("notice_events_v1", now(), hashlib.sha256(NOTICE_EVENTS_SCHEMA.encode("utf-8")).hexdigest()))
        schema_contracts = (
            # v1 queda como contrato histórico; los cambios aditivos posteriores
            # se registran con una nueva versión para no invalidar instalaciones
            # existentes que ya conservaron su checksum original.
            ("postgres_core_v4", SCHEMA),
            ("postgres_wfm_v2", WFM_SCHEMA),
            ("postgres_compat_v1", "quotes.toll_count,toll_details,toll_price;app_sessions.last_seen_at"),
        )
        for contract_key, contract_definition in schema_contracts:
            contract_checksum = hashlib.sha256(contract_definition.encode("utf-8")).hexdigest()
            existing = database.execute("SELECT checksum FROM schema_migrations WHERE key=%s", (contract_key,)).fetchone()
            if existing and existing["checksum"] and existing["checksum"] != contract_checksum:
                raise RuntimeError(f"El contrato de esquema {contract_key} cambió sin una nueva versión")
            database.execute(
                """INSERT INTO schema_migrations(key,applied_at,checksum) VALUES(%s,%s,%s)
                ON CONFLICT(key) DO UPDATE SET checksum=COALESCE(schema_migrations.checksum,EXCLUDED.checksum)""",
                (contract_key, now(), contract_checksum),
            )
        quote_rule_columns={row["column_name"] for row in database.execute("SELECT column_name FROM information_schema.columns WHERE table_name='quote_rules'").fetchall()}
        added_quote_rule_columns=[]
        for column,default in QUOTE_RULE_EXTRA_COLUMNS.items():
            if column not in quote_rule_columns:
                database.execute(f"ALTER TABLE quote_rules ADD COLUMN {column} DOUBLE PRECISION NOT NULL DEFAULT {float(default)}")
                added_quote_rule_columns.append(column)
        database.execute("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS toll_count INTEGER NOT NULL DEFAULT 0")
        database.execute("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS toll_details TEXT NOT NULL DEFAULT '[]'")
        database.execute("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS toll_price DOUBLE PRECISION NOT NULL DEFAULT 0")
        database.execute("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS pricing_snapshot TEXT NOT NULL DEFAULT '{}'")
        for column, definition in {
            "responsible": "TEXT", "completion_note": "TEXT", "cancellation_reason": "TEXT",
            "assigned_at": "TIMESTAMPTZ", "started_at": "TIMESTAMPTZ", "completed_at": "TIMESTAMPTZ",
            "cancelled_at": "TIMESTAMPTZ", "updated_at": "TIMESTAMPTZ", "updated_by": "TEXT",
        }.items():
            database.execute(f"ALTER TABLE scheduled_transfers ADD COLUMN IF NOT EXISTS {column} {definition}")
        database.execute("UPDATE scheduled_transfers SET status='SIN_ASIGNAR' WHERE status='PENDIENTE'")
        database.execute("UPDATE scheduled_transfers SET status='ASIGNADO' WHERE status='CONFIRMADO'")
        database.execute("UPDATE scheduled_transfers SET status='FINALIZADO' WHERE status='COMPLETADO'")
        database.execute("UPDATE scheduled_transfers SET updated_at=created_at WHERE updated_at IS NULL")
        database.execute("ALTER TABLE scheduled_transfers ALTER COLUMN updated_at SET NOT NULL")
        database.execute("CREATE INDEX IF NOT EXISTS transfers_agenda_idx ON scheduled_transfers(status,scheduled_date,scheduled_time)")
        database.execute("CREATE INDEX IF NOT EXISTS transfers_task_idx ON scheduled_transfers(lower(task_number),scheduled_date)")
        if not database.execute("SELECT 1 FROM schema_migrations WHERE key=%s", ("transfer_workflow_v1",)).fetchone():
            database.execute("""INSERT INTO transfer_events(transfer_id,event_type,actor,new_status,note,created_at)
                SELECT id,'CREADO',planner,status,'Registro existente incorporado al historial',created_at
                FROM scheduled_transfers""")
            database.execute("INSERT INTO schema_migrations(key,applied_at,checksum) VALUES(%s,%s,%s)",
                ("transfer_workflow_v1",now(),hashlib.sha256(TRANSFER_EVENTS_SCHEMA.encode("utf-8")).hexdigest()))
        database.execute("ALTER TABLE app_sessions ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ")
        database.execute("UPDATE app_sessions SET last_seen_at=created_at WHERE last_seen_at IS NULL")
        database.execute("ALTER TABLE app_sessions ALTER COLUMN last_seen_at SET NOT NULL")
        database.execute("ALTER TABLE delay_zones ADD COLUMN IF NOT EXISTS normalized_by TEXT")
        database.execute("ALTER TABLE delay_zones ADD COLUMN IF NOT EXISTS resolution_note TEXT")
        database.execute("ALTER TABLE delay_zones ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMPTZ")
        database.execute("ALTER TABLE delay_zones ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ")
        database.execute("ALTER TABLE delay_zones ADD COLUMN IF NOT EXISTS last_verified_by TEXT")
        database.execute("UPDATE delay_zones SET last_verified_at=created_at WHERE last_verified_at IS NULL")
        database.execute("CREATE INDEX IF NOT EXISTS delay_zones_status_created_idx ON delay_zones(status,created_at DESC)")
        database.execute("CREATE INDEX IF NOT EXISTS delay_zones_location_idx ON delay_zones(department,service)")
        database.execute("ALTER TABLE arrival_standards ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'PROVISIONAL'")
        database.execute("ALTER TABLE arrival_standards ADD COLUMN IF NOT EXISTS source TEXT")
        database.execute("ALTER TABLE arrival_standards ADD COLUMN IF NOT EXISTS reviewed_by TEXT")
        database.execute("ALTER TABLE arrival_standards ADD COLUMN IF NOT EXISTS effective_from DATE")
        database.execute("ALTER TABLE arrival_standards ADD COLUMN IF NOT EXISTS review_due_at DATE")
        database.execute("ALTER TABLE arrival_standards ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE")
        database.execute("ALTER TABLE arrival_standards ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ")
        database.execute("ALTER TABLE arrival_standards ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ")
        database.execute("ALTER TABLE arrival_standards ADD COLUMN IF NOT EXISTS owner TEXT NOT NULL DEFAULT 'Supervisión'")
        database.execute("ALTER TABLE arrival_standards ADD COLUMN IF NOT EXISTS review_interval_days INTEGER NOT NULL DEFAULT 90")
        database.execute("ALTER TABLE arrival_standards ADD COLUMN IF NOT EXISTS approval_status TEXT NOT NULL DEFAULT 'APPROVED'")
        database.execute("ALTER TABLE arrival_standards ADD COLUMN IF NOT EXISTS submitted_by TEXT")
        database.execute("ALTER TABLE arrival_standards ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ")
        database.execute("ALTER TABLE arrival_standards ADD COLUMN IF NOT EXISTS approved_by TEXT")
        database.execute("ALTER TABLE arrival_standards ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ")
        database.execute("ALTER TABLE arrival_standards ADD COLUMN IF NOT EXISTS approval_note TEXT")
        database.execute("UPDATE arrival_standards SET created_at=COALESCE(created_at,%s),updated_at=COALESCE(updated_at,%s)", (now(), now()))
        database.execute("ALTER TABLE arrival_standards ALTER COLUMN created_at SET NOT NULL")
        database.execute("ALTER TABLE arrival_standards ALTER COLUMN updated_at SET NOT NULL")
        database.execute("CREATE INDEX IF NOT EXISTS arrival_standards_lookup_idx ON arrival_standards(active,department,service)")
        database.execute("""CREATE TABLE IF NOT EXISTS operational_zones(
            id BIGSERIAL PRIMARY KEY,department TEXT NOT NULL,name TEXT NOT NULL,normalized_name TEXT NOT NULL,
            active BOOLEAN NOT NULL DEFAULT TRUE,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,
            UNIQUE(department,normalized_name))""")
        database.execute("ALTER TABLE operational_zones ADD COLUMN IF NOT EXISTS owner TEXT NOT NULL DEFAULT 'Supervisión'")
        database.execute("ALTER TABLE operational_zones ADD COLUMN IF NOT EXISTS expected_services TEXT NOT NULL DEFAULT '[]'")
        database.execute("""CREATE TABLE IF NOT EXISTS arrival_standard_zones(
            standard_id BIGINT NOT NULL REFERENCES arrival_standards(id) ON DELETE CASCADE,
            zone_id BIGINT NOT NULL REFERENCES operational_zones(id),PRIMARY KEY(standard_id,zone_id))""")
        database.execute("ALTER TABLE delay_zones ADD COLUMN IF NOT EXISTS zone_id BIGINT REFERENCES operational_zones(id)")
        database.execute("""CREATE TABLE IF NOT EXISTS delay_events(
            id BIGSERIAL PRIMARY KEY,delay_id BIGINT NOT NULL REFERENCES delay_zones(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,actor TEXT NOT NULL,note TEXT,review_due_at TIMESTAMPTZ,created_at TIMESTAMPTZ NOT NULL)""")
        database.execute("CREATE INDEX IF NOT EXISTS delay_events_delay_idx ON delay_events(delay_id,created_at DESC)")
        database.execute("""CREATE TABLE IF NOT EXISTS standard_versions(
            id BIGSERIAL PRIMARY KEY,standard_id BIGINT NOT NULL REFERENCES arrival_standards(id) ON DELETE CASCADE,
            version INTEGER NOT NULL,action TEXT NOT NULL,actor TEXT NOT NULL,reason TEXT,snapshot TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,UNIQUE(standard_id,version))""")
        database.execute("CREATE INDEX IF NOT EXISTS standard_versions_standard_idx ON standard_versions(standard_id,version DESC)")
        database.execute("INSERT INTO app_settings(key,value) VALUES('google_client_id','') ON CONFLICT(key) DO NOTHING")
        database.execute(
            "INSERT INTO app_settings(key,value) VALUES('google_allowed_domain',%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
            (ALLOWED_GOOGLE_DOMAIN,),
        )
        role_ids = {}
        for name, permissions in DEFAULT_ROLES.items():
            role = database.execute("SELECT id FROM roles WHERE name=%s", (name,)).fetchone()
            created = role is None
            if not role:
                role = database.execute(
                    "INSERT INTO roles(name,description) VALUES(%s,%s) RETURNING id", (name, f"Rol {name}")
                ).fetchone()
            role_ids[name] = role["id"]
            # Los permisos predeterminados son solo la configuración inicial.
            # Una vez creado el rol, la selección del administrador es la fuente
            # de verdad y debe sobrevivir a reinicios posteriores.
            if created and name != "Administrador":
                execute_many(database,
                    "INSERT INTO role_permissions(role_id,permission) VALUES(%s,%s)",
                    [(role["id"], permission) for permission in permissions],
                )
        if not database.execute("SELECT 1 FROM schema_migrations WHERE key=%s", ("notice_permissions_v1",)).fetchone():
            legacy_roles = database.execute("SELECT DISTINCT role_id FROM role_permissions WHERE permission=%s", ("notices.manage",)).fetchall()
            for legacy in legacy_roles:
                role_id = legacy["role_id"]
                role_name = database.execute("SELECT name FROM roles WHERE id=%s", (role_id,)).fetchone()
                if role_name and role_name["name"] != "Administrador":
                    execute_many(database,
                        "INSERT INTO role_permissions(role_id,permission) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                        [(role_id, permission) for permission in NOTICE_MANAGE_PERMISSIONS],
                    )
                    database.execute("DELETE FROM role_permissions WHERE role_id=%s AND permission=%s", (role_id, "notices.manage"))
            database.execute("INSERT INTO schema_migrations(key,applied_at,checksum) VALUES(%s,%s,%s)", ("notice_permissions_v1", now(), hashlib.sha256(b"notice_permissions_v1").hexdigest()))
        if not database.execute("SELECT 1 FROM schema_migrations WHERE key=%s", ("standards_workflow_v1",)).fetchone():
            for role_name in ("Supervisor","Planificador","Telefonista"):
                role=database.execute("SELECT id FROM roles WHERE name=%s",(role_name,)).fetchone()
                if role:database.execute("INSERT INTO role_permissions(role_id,permission) VALUES(%s,%s) ON CONFLICT DO NOTHING",(role["id"],"standards.propose"))
            supervisor=database.execute("SELECT id FROM roles WHERE name=%s",("Supervisor",)).fetchone()
            if supervisor:database.execute("INSERT INTO role_permissions(role_id,permission) VALUES(%s,%s) ON CONFLICT DO NOTHING",(supervisor["id"],"standards.approve"))
            database.execute("INSERT INTO schema_migrations(key,applied_at,checksum) VALUES(%s,%s,%s)",( "standards_workflow_v1",now(),hashlib.sha256(b"standards_workflow_v1").hexdigest()))
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
            standard_stamp = now()
            execute_many(database,
                """INSERT INTO arrival_standards(
                department,zone,service,minutes_min,minutes_max,note,status,source,reviewed_by,
                effective_from,review_due_at,active,created_at,updated_at)
                VALUES(%s,%s,%s,%s,%s,%s,'PROVISIONAL','Configuración inicial','Sistema',%s,NULL,TRUE,%s,%s)""",
                [
                    (*item, date.today(), standard_stamp, standard_stamp)
                    for item in [
                        ("MONTEVIDEO", "Centro, Parque Rodó, Pocitos, Punta Carretas, Tres Cruces, Buceo", "ML", None, 30, None),
                        ("MONTEVIDEO", "Nuevo París, Cerro, Colón, Casavalle, Peñarol, La Teja, Manga", "ML", None, 45, None),
                        ("MONTEVIDEO", "Ciudad", "GRÚA", None, 45, None),
                        ("CANELONES", "Ciudad de la Costa", "ML", None, 45, None),
                        ("ARTIGAS", "Artigas", "ML", None, 45, None),
                        ("ARTIGAS", "Artigas", "GRÚA", None, 60, None),
                        ("MALDONADO", "Maldonado Ciudad, Piriápolis", "ML", 30, 45, None),
                        ("INTERIOR", "Zona no listada", "ML", None, None, "A confirmar"),
                    ]
                ],
            )
        for standard in database.execute("SELECT id,department,zone FROM arrival_standards").fetchall():
            sync_standard_zones(database,standard["id"],standard["department"],standard["zone"])
            if not database.execute("SELECT 1 FROM standard_versions WHERE standard_id=%s",(standard["id"],)).fetchone():record_standard_version(database,standard["id"],"BASELINE","Sistema","Versión inicial conservada")
        for delay in database.execute("SELECT id,department,zone FROM delay_zones WHERE zone_id IS NULL").fetchall():
            zone_id=ensure_operational_zone(database,delay["department"],delay["zone"])
            database.execute("UPDATE delay_zones SET zone_id=%s WHERE id=%s",(zone_id,delay["id"]))
        reconcile_migration_checksums(database, {
            "audit_contract_v2": "audit_contract_v2",
            "notice_events_v1": NOTICE_EVENTS_SCHEMA,
            "transfer_workflow_v1": TRANSFER_EVENTS_SCHEMA,
            "notice_permissions_v1": "notice_permissions_v1",
            "standards_workflow_v1": "standards_workflow_v1",
        }, placeholder="%s")


def ensure_operational_zone(database,department,name):
    clean_name=" ".join(str(name or "").split());key=normalized_key(clean_name);stamp=now()
    item=database.execute("""INSERT INTO operational_zones(department,name,normalized_name,created_at,updated_at)
        VALUES(%s,%s,%s,%s,%s) ON CONFLICT(department,normalized_name)
        DO UPDATE SET name=EXCLUDED.name,active=TRUE,updated_at=EXCLUDED.updated_at RETURNING id""",
        (department,clean_name,key,stamp,stamp)).fetchone()
    return item["id"]


def sync_standard_zones(database,standard_id,department,zone_text):
    database.execute("DELETE FROM arrival_standard_zones WHERE standard_id=%s",(standard_id,))
    for name in split_zones(zone_text):
        zone_id=ensure_operational_zone(database,department,name)
        database.execute("INSERT INTO arrival_standard_zones(standard_id,zone_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",(standard_id,zone_id))


def record_delay_event(database,delay_id,event_type,actor,note=None,review_due_at=None):
    database.execute("INSERT INTO delay_events(delay_id,event_type,actor,note,review_due_at,created_at) VALUES(%s,%s,%s,%s,%s,%s)",(delay_id,event_type,actor,note,review_due_at,now()))


def record_standard_version(database,standard_id,action,actor,reason=None):
    item=database.execute("SELECT * FROM arrival_standards WHERE id=%s",(standard_id,)).fetchone()
    version=database.execute("SELECT COALESCE(max(version),0)+1 next_version FROM standard_versions WHERE standard_id=%s",(standard_id,)).fetchone()["next_version"]
    snapshot=json.dumps(dict(item),ensure_ascii=False,default=str,sort_keys=True)
    database.execute("INSERT INTO standard_versions(standard_id,version,action,actor,reason,snapshot,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s)",(standard_id,version,action,actor,reason,snapshot,now()))


def expected_services(value):
    try:items=json.loads(value or "[]") if isinstance(value,str) else list(value or [])
    except (TypeError,ValueError):items=[]
    return [service for service in STANDARD_SERVICES if service in items]


def dashboard_snapshot(database,days=30,current_time=None):
    as_of=current_time or now();cutoff=as_of-timedelta(days=days)
    notice_counts=rows(database,"SELECT status,count(*) total FROM notices GROUP BY status")
    active_delays=rows(database,"SELECT * FROM delay_zones WHERE status='VIGENTE'")
    transfer_counts=rows(database,"SELECT status,count(*) total FROM scheduled_transfers GROUP BY status")
    period_delays=rows(database,"SELECT * FROM delay_zones WHERE (created_at>=%s AND created_at<=%s) OR (normalized_at>=%s AND normalized_at<=%s)",(cutoff,as_of,cutoff,as_of))
    verification_events=database.execute("SELECT count(*) total FROM delay_events WHERE event_type='VERIFICADO' AND created_at>=%s AND created_at<=%s",(cutoff,as_of)).fetchone()["total"]
    standards=rows(database,"SELECT * FROM arrival_standards WHERE active=TRUE")
    zones=rows(database,"SELECT expected_services FROM operational_zones WHERE active=TRUE")
    return build_dashboard_payload(
        notice_status_counts=notice_counts,active_delays=active_delays,
        transfer_status_counts=transfer_counts,period_delays=period_delays,
        verification_events=verification_events,standards=standards,
        expected_zone_services=sum(len(expected_services(zone.get("expected_services"))) for zone in zones),
        days=days,current_time=as_of,
    )


def token_from(request: Request):
    return request.cookies.get(SESSION_COOKIE_NAME, "")


def token_hash(token):
    return hmac.new(APP_SECRET.encode(), token.encode(), hashlib.sha256).hexdigest()


def request_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    try:
        return str(ipaddress.ip_address(peer))
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
    # Evita que intentos simultáneos lean el mismo contador y pierdan incrementos.
    database.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (key,))
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
    # Serializa altas, bajas y cambios de rol relevantes. Sin este bloqueo, dos
    # administradores podrían degradarse a la vez y ambos ver al otro todavía
    # activo antes de confirmar sus transacciones.
    database.execute("SELECT pg_advisory_xact_lock(73139020)")
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
                event = 'SOLICITUD_WFM_CANCELADA' if data.get('operation') == 'cancel' else {'APROBAR': 'SOLICITUD_WFM_APROBADA', 'RECHAZAR': 'SOLICITUD_WFM_RECHAZADA'}.get(decision, 'SOLICITUD_WFM_CREADA')
                detail = f"{result.get('request_id', '')} · {result.get('requested_date', '')} · {result.get('request_type', '')}"
            elif action == 'publish-week':
                event = 'SEMANA_WFM_PUBLICADA'; detail = f"{result.get('week', '')} · {result.get('team', '')} · {result.get('published_count', 0)} días"
            else:
                event = 'WFM_ACTUALIZADO'; detail = request.query_params.get('team', '')
            audit(database,'wfm',0,event,actor['display_name'],detail,actor_id=actor['id'])
            return result
    except WfmError as error:
        raise HTTPException(error.status, str(error)) from None
    except Exception:
        LOGGER.exception("Error inesperado al actualizar WFM: %s", action)
        raise HTTPException(500, "No se pudo actualizar la planificación. Reintentá después de actualizar el servicio.") from None
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)


def request_is_https(request: Request) -> bool:
    return request.url.scheme == "https"


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
    if request_is_https(request):
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
    required_tables = {
        "users", "roles", "role_permissions", "app_sessions", "quote_rules",
        "wfm_revisions", "wfm_published_plans", "wfm_published_shifts",
    }
    try:
        with connect() as database:
            database.execute("SELECT 1")
            tables = {
                row["table_name"]
                for row in database.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name = ANY(%s)",
                    (list(required_tables),),
                ).fetchall()
            }
        missing = sorted(required_tables - tables)
        if missing:
            raise RuntimeError(f"faltan tablas requeridas: {', '.join(missing)}")
        from .wfm import weekly_template
        template = weekly_template("Telefonista")
        if not isinstance(template, dict):
            raise RuntimeError("la plantilla WFM no tiene un formato válido")
        return {"status": "ok", "checks": {"database": "ok", "schema": "ok", "wfm": "ok"}}
    except Exception as error:
        LOGGER.exception("Comprobación de salud fallida")
        raise HTTPException(503, "El servicio no está listo") from error


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
                audit(database,"session",user["id"] if user else 0,"INGRESO_BLOQUEADO" if retry else "INGRESO_FALLIDO","Autenticación",f"huella={key[:16]}",actor_id=user["id"] if user else None)
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
        audit(database,"session",user["id"],"INGRESO_PASSWORD",user["display_name"],f"huella={key[:16]}",actor_id=user["id"])
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
                audit(database,"session",user["id"],"SALIDA",user["display_name"],actor_id=user["id"])
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
        audit(database,"session",user["id"],"INGRESO_GOOGLE",user["display_name"],f"huella={key[:16]}",actor_id=user["id"])
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
            audit(database,"role",item["id"],"CREADO",actor["display_name"],name,actor_id=actor["id"])
    except psycopg.errors.UniqueViolation as exc: raise HTTPException(400, "Ya existe un rol con ese nombre") from exc
    return {"id": item["id"], "name": name, "permissions": []}


@app.patch("/api/roles/{role_id}/permissions")
def update_permissions(role_id: int, request: Request, data: PermissionsIn = Body(...)):
    data = data.model_dump()
    actor = authorized(request, "settings.manage")
    valid = list(dict.fromkeys(item for item in data.get("permissions", []) if item in PERMISSIONS))
    with connect() as database:
        role = database.execute("SELECT name FROM roles WHERE id=%s", (role_id,)).fetchone()
        if not role: raise HTTPException(404, "Rol inexistente")
        if role["name"] == "Administrador": raise HTTPException(400, "Los permisos del Administrador son obligatorios y no se pueden modificar")
        before=_audit_snapshot(database,"role",role_id)
        database.execute("DELETE FROM role_permissions WHERE role_id=%s", (role_id,))
        execute_many(database, "INSERT INTO role_permissions(role_id,permission) VALUES(%s,%s)", [(role_id, item) for item in valid])
        audit(database,"role",role_id,"PERMISOS_ACTUALIZADOS",actor["display_name"],", ".join(valid),actor_id=actor["id"],before=before)
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
    username = str(data.get("username") or "").strip().lower() or email.split("@", 1)[0]
    password = data.get("password") or secrets.token_urlsafe(32)
    try:
        with connect() as database:
            item = database.execute("INSERT INTO users(username,email,display_name,password_hash,role_id,active) VALUES(%s,%s,%s,%s,%s,TRUE) RETURNING id", (username, email, data["display_name"], hash_password(password), int(data["role_id"]))).fetchone()
            audit(database,"user",item["id"],"CREADO",actor["display_name"],email,actor_id=actor["id"])
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
            previous = database.execute("SELECT * FROM users WHERE id=%s", (user_id,)).fetchone()
            if not previous: raise HTTPException(404, "Usuario inexistente")
            ensure_active_admin_survives(database, user_id, int(data["role_id"]), bool(data.get("active", True)))
            google_sub = None if str(previous["email"] or "").lower() != email else database.execute("SELECT google_sub FROM users WHERE id=%s", (user_id,)).fetchone()["google_sub"]
            if data.get("password"):
                database.execute("UPDATE users SET display_name=%s,email=%s,role_id=%s,active=%s,password_hash=%s,google_sub=%s WHERE id=%s", (data["display_name"], email, int(data["role_id"]), bool(data.get("active", True)), hash_password(data["password"]), google_sub, user_id))
            else:
                database.execute("UPDATE users SET display_name=%s,email=%s,role_id=%s,active=%s,google_sub=%s WHERE id=%s", (data["display_name"], email, int(data["role_id"]), bool(data.get("active", True)), google_sub, user_id))
            security_identity_changed = (
                bool(data.get("password"))
                or not bool(data.get("active", True))
                or int(previous["role_id"]) != int(data["role_id"])
                or str(previous["email"] or "").lower() != email
            )
            if security_identity_changed:
                database.execute("DELETE FROM app_sessions WHERE user_id=%s", (user_id,))
            audit(database,"user",user_id,"ACTUALIZADO",actor["display_name"],email,actor_id=actor["id"],before=previous)
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
        previous=database.execute("SELECT value FROM app_settings WHERE key='google_client_id'").fetchone()
        database.execute("INSERT INTO app_settings(key,value) VALUES('google_client_id',%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value", (client_id,))
        audit(database,"settings",1,"GOOGLE_ACTUALIZADO",actor["display_name"],"Activado" if client_id else "Desactivado",actor_id=actor["id"],before={"enabled":bool(previous and previous["value"])},after={"enabled":bool(client_id)})
    return {"ok": True, "enabled": bool(client_id)}


@app.get("/api/settings/version")
def version(request: Request):
    authorized(request, "settings.manage")
    return current_release_payload()

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
    from .wfm import _published_schedules
    actor=authorized(request, "reports.export")
    if actor['role_name'] not in ('Supervisor','Administrador'):employee_id=actor['id']
    try:
        if week: week=schedule_week_start(week).isoformat()
        if date_from: datetime.strptime(date_from,"%Y-%m-%d")
        if date_to: datetime.strptime(date_to,"%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(400, "El período indicado no es válido") from exc
    params={"week":week,"date_from":date_from,"date_to":date_to,"role":role,"q":q}
    if employee_id is not None:params["employee_id"]=str(employee_id)
    with connect() as database:
        def query(sql,args=()):return database.execute(sql.replace('?', '%s'),args)
        result=_published_schedules(query,params,True)
        audit(database,"report",0,"EXPORTADO",actor["display_name"],json.dumps({"kind":"schedules","filters":params,"rows":len(result)},ensure_ascii=False,sort_keys=True),actor_id=actor["id"],after={"kind":"schedules","filters":params,"rows":len(result)})
        content=report_csv_bytes("schedules",result)
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
            validate_quote_rule_values(fields, values)
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(400, "Las tarifas y kilómetros deben ser numéricos y estar dentro del rango permitido") from exc
        assignments = ",".join(f"{field}=%s" for field in fields)
        database.execute(f"UPDATE quote_rules SET {assignments},updated_at=%s WHERE id=1", values + [now()])
        audit(database,"quote_rules",1,"ACTUALIZADO",actor["display_name"],actor_id=actor["id"],before=current)
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
        audit(database,'toll',item['id'],'CREADO',actor['display_name'],data['name'].strip(),actor_id=actor['id'])
    return {'ok':True}


@app.patch("/api/settings/tolls/{item_id}")
def update_toll(item_id: int, request: Request, data: TollIn = Body(...)):
    data=data.model_dump(); actor=authorized(request, "settings.manage")
    with connect() as database:
        current=database.execute("SELECT * FROM toll_catalog WHERE id=%s",(item_id,)).fetchone()
        if not current:raise HTTPException(404,'Peaje inexistente')
        item=database.execute("UPDATE toll_catalog SET name=%s,latitude=%s,longitude=%s,price=%s,active=%s,updated_at=%s WHERE id=%s RETURNING id",(data['name'].strip(),data['latitude'],data['longitude'],data['price'],data['active'],now(),item_id)).fetchone()
        audit(database,'toll',item_id,'ACTUALIZADO',actor['display_name'],data['name'].strip(),actor_id=actor['id'],before=current)
    return {'ok':True}


@app.delete("/api/settings/tolls/{item_id}")
def delete_toll(item_id: int, request: Request):
    actor=authorized(request, "settings.manage")
    with connect() as database:
        item=database.execute("DELETE FROM toll_catalog WHERE id=%s RETURNING name",(item_id,)).fetchone()
        if not item:raise HTTPException(404,'Peaje inexistente')
        audit(database,'toll',item_id,'ELIMINADO',actor['display_name'],item['name'],actor_id=actor['id'],before=item)
    return {'ok':True}


def standard_is_overdue(item):
    due = item.get("review_due_at")
    return bool(due and (due if isinstance(due, date) else date.fromisoformat(str(due))) < date.today())


def enrich_standard(item):
    result=dict(item);result["availability"]=standard_availability(result)
    approval=result.get("approval_status") or "APPROVED"
    if approval!="APPROVED":result["availability"]="PENDING_APPROVAL" if approval=="PENDING" else "REJECTED"
    result["is_overdue"]=result["availability"]=="REVIEW_DUE"
    result["is_usable"]=result["availability"]=="CURRENT" and approval=="APPROVED"
    return result


def standard_duplicate(database, data, exclude_id=None):
    query = """SELECT id FROM arrival_standards
        WHERE active=TRUE AND lower(department)=lower(%s) AND lower(service)=lower(%s)
        AND lower(zone)=lower(%s)"""
    values = [data["department"], data["service"], data["zone"]]
    if exclude_id is not None:
        query += " AND id<>%s"; values.append(exclude_id)
    return database.execute(query, values).fetchone()


@app.get("/api/settings/standards")
def managed_standards(request: Request):
    authorized(request, "settings.manage")
    with connect() as database:
        items = rows(database, "SELECT * FROM arrival_standards ORDER BY active DESC,department,service,zone")
    return [enrich_standard(item) for item in items]


@app.post("/api/settings/standards", status_code=201)
def create_standard(request: Request, data: ArrivalStandardIn = Body(...)):
    actor = authorized(request, "settings.manage")
    values = validated_business_data(clean_standard, data.model_dump())
    stamp = now()
    with connect() as database:
        database.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (
            f"standard|{normalized_key(values['department'])}|{normalized_key(values['service'])}|{normalized_key(values['zone'])}",
        ))
        if values["active"] and standard_duplicate(database, values):
            raise HTTPException(409, "Ya existe una referencia activa para esa prestación y zona")
        item = database.execute(
            """INSERT INTO arrival_standards(
            department,zone,service,minutes_min,minutes_max,note,status,source,reviewed_by,
            effective_from,review_due_at,owner,review_interval_days,active,created_at,updated_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (values["department"],values["zone"],values["service"],values.get("minutes_min"),
             values.get("minutes_max"),values.get("note"),values["status"],values.get("source"),
             actor["display_name"],values.get("effective_from"),values.get("review_due_at"),
             values["owner"],values["review_interval_days"],values["active"],stamp,stamp),
        ).fetchone()
        item=database.execute("UPDATE arrival_standards SET approval_status='APPROVED',submitted_by=%s,submitted_at=%s,approved_by=%s,approved_at=%s,approval_note=%s WHERE id=%s RETURNING *",(actor["display_name"],stamp,actor["display_name"],stamp,"Alta administrativa",item["id"])).fetchone()
        sync_standard_zones(database,item["id"],values["department"],values["zone"])
        record_standard_version(database,item["id"],"CREATED",actor["display_name"],"Alta administrativa")
        audit(database,"arrival_standard",item["id"],"CREADO",actor["display_name"],f"{values['department']} · {values['service']} · {values['zone']}",actor_id=actor["id"])
    return enrich_standard(item)


@app.patch("/api/settings/standards/{item_id}")
def update_standard(item_id: int, request: Request, data: ArrivalStandardIn = Body(...)):
    actor = authorized(request, "settings.manage")
    values = validated_business_data(clean_standard, data.model_dump())
    with connect() as database:
        current = database.execute("SELECT * FROM arrival_standards WHERE id=%s FOR UPDATE",(item_id,)).fetchone()
        if not current: raise HTTPException(404,"Referencia inexistente")
        if values["active"] and standard_duplicate(database, values, item_id):
            raise HTTPException(409, "Ya existe una referencia activa para esa prestación y zona")
        item = database.execute(
            """UPDATE arrival_standards SET department=%s,zone=%s,service=%s,minutes_min=%s,
            minutes_max=%s,note=%s,status=%s,source=%s,reviewed_by=%s,effective_from=%s,
            review_due_at=%s,owner=%s,review_interval_days=%s,active=%s,updated_at=%s WHERE id=%s RETURNING *""",
            (values["department"],values["zone"],values["service"],values.get("minutes_min"),
             values.get("minutes_max"),values.get("note"),values["status"],values.get("source"),
             actor["display_name"],values.get("effective_from"),values.get("review_due_at"),
             values["owner"],values["review_interval_days"],values["active"],now(),item_id),
        ).fetchone()
        sync_standard_zones(database,item_id,values["department"],values["zone"])
        record_standard_version(database,item_id,"UPDATED",actor["display_name"],"Edición administrativa")
        audit(database,"arrival_standard",item_id,"ACTUALIZADO",actor["display_name"],f"{values['department']} · {values['service']} · {values['zone']}",actor_id=actor["id"],before=current,after=item)
    return enrich_standard(item)


@app.delete("/api/settings/standards/{item_id}")
def deactivate_standard(item_id: int, request: Request):
    actor = authorized(request, "settings.manage")
    with connect() as database:
        current=database.execute("SELECT * FROM arrival_standards WHERE id=%s AND active=TRUE",(item_id,)).fetchone()
        if not current:raise HTTPException(404,"Referencia activa inexistente")
        item = database.execute("UPDATE arrival_standards SET active=FALSE,updated_at=%s WHERE id=%s AND active=TRUE RETURNING *",(now(),item_id)).fetchone()
        record_standard_version(database,item_id,"DEACTIVATED",actor["display_name"],"Referencia desactivada")
        audit(database,"arrival_standard",item_id,"DESACTIVADO",actor["display_name"],f"{item['department']} · {item['service']} · {item['zone']}",actor_id=actor["id"],before=current,after=item)
    return {"ok":True}


@app.post("/api/standards/proposals",status_code=201)
def propose_standard(request:Request,data:ArrivalStandardIn=Body(...)):
    actor=authorized(request,"standards.propose");values=validated_business_data(clean_standard,data.model_dump());stamp=now()
    with connect() as database:
        if standard_duplicate(database,values):raise HTTPException(409,"Ya existe una referencia activa para esa prestación y zona")
        item=database.execute("""INSERT INTO arrival_standards(department,zone,service,minutes_min,minutes_max,note,status,source,reviewed_by,effective_from,review_due_at,owner,review_interval_days,approval_status,submitted_by,submitted_at,active,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING',%s,%s,TRUE,%s,%s) RETURNING *""",(values["department"],values["zone"],values["service"],values.get("minutes_min"),values.get("minutes_max"),values.get("note"),values["status"],values.get("source"),actor["display_name"],values.get("effective_from"),values.get("review_due_at"),values["owner"],values["review_interval_days"],actor["display_name"],stamp,stamp,stamp)).fetchone()
        sync_standard_zones(database,item["id"],values["department"],values["zone"]);record_standard_version(database,item["id"],"SUBMITTED",actor["display_name"],"Propuesta enviada")
        audit(database,"arrival_standard",item["id"],"PROPUESTO",actor["display_name"],f"{values['department']} · {values['service']} · {values['zone']}",actor_id=actor["id"])
    return enrich_standard(item)


@app.patch("/api/settings/standards/{item_id}/decision")
def decide_standard(item_id:int,request:Request,data:StandardDecisionIn=Body(...)):
    actor=authorized(request,"standards.approve");stamp=now()
    with connect() as database:
        current=database.execute("SELECT * FROM arrival_standards WHERE id=%s FOR UPDATE",(item_id,)).fetchone()
        if not current:raise HTTPException(404,"Referencia inexistente")
        if current["approval_status"]!="PENDING":raise HTTPException(409,"La propuesta ya fue resuelta")
        item=database.execute("UPDATE arrival_standards SET approval_status=%s,approved_by=%s,approved_at=%s,approval_note=%s,active=%s,updated_at=%s WHERE id=%s RETURNING *",(data.decision,actor["display_name"],stamp,data.note.strip(),data.decision=="APPROVED",stamp,item_id)).fetchone()
        record_standard_version(database,item_id,data.decision,actor["display_name"],data.note.strip());audit(database,"arrival_standard",item_id,data.decision,actor["display_name"],data.note.strip(),actor_id=actor["id"])
    return enrich_standard(item)


@app.get("/api/settings/standards/{item_id}/versions")
def standard_version_history(item_id:int,request:Request):
    authorized(request,"standards.view")
    with connect() as database:
        if not database.execute("SELECT 1 FROM arrival_standards WHERE id=%s",(item_id,)).fetchone():raise HTTPException(404,"Referencia inexistente")
        items=rows(database,"SELECT * FROM standard_versions WHERE standard_id=%s ORDER BY version DESC",(item_id,))
    for item in items:item["snapshot"]=json.loads(item["snapshot"])
    return items


@app.get("/api/zones")
def operational_zones(request: Request, department: str = ""):
    authorized(request,"standards.view")
    with connect() as database:
        query="""SELECT z.*,count(DISTINCT sz.standard_id) reference_count,
            count(DISTINCT d.id) delay_count FROM operational_zones z
            LEFT JOIN arrival_standard_zones sz ON sz.zone_id=z.id
            LEFT JOIN delay_zones d ON d.zone_id=z.id WHERE z.active=TRUE""";values=[]
        if department:query+=" AND lower(z.department)=lower(%s)";values.append(department)
        query+=" GROUP BY z.id ORDER BY z.department,z.name"
        items=rows(database,query,values)
    for item in items:item["expected_services"]=expected_services(item.get("expected_services"))
    return items


@app.post("/api/settings/zones")
def configure_zone(request:Request,data:ZoneCoverageIn=Body(...)):
    actor=authorized(request,"standards.approve");department=" ".join(data.department.split()).upper();name=" ".join(data.name.split());key=normalized_key(name);stamp=now()
    if department not in set(DEPARTMENTS)|{"INTERIOR"}:raise HTTPException(422,"Departamento inválido")
    services=[service for service in STANDARD_SERVICES if service in data.expected_services]
    with connect() as database:
        item=database.execute("""INSERT INTO operational_zones(department,name,normalized_name,owner,expected_services,active,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,TRUE,%s,%s) ON CONFLICT(department,normalized_name) DO UPDATE SET name=EXCLUDED.name,owner=EXCLUDED.owner,expected_services=EXCLUDED.expected_services,active=TRUE,updated_at=EXCLUDED.updated_at RETURNING *""",(department,name,key,data.owner.strip(),json.dumps(services,ensure_ascii=False),stamp,stamp)).fetchone()
        audit(database,"operational_zone",item["id"],"COBERTURA_CONFIGURADA",actor["display_name"],f"{department} · {name} · {', '.join(services) or 'sin prestaciones esperadas'}",actor_id=actor["id"])
    result=dict(item);result["expected_services"]=services;return result


@app.get("/api/zones-coverage")
def zones_coverage(request:Request,department:str=""):
    authorized(request,"standards.view")
    with connect() as database:
        zone_query="SELECT * FROM operational_zones WHERE active=TRUE";params=[]
        if department:zone_query+=" AND lower(department)=lower(%s)";params.append(department)
        zone_query+=" ORDER BY department,name";zones=rows(database,zone_query,params)
        standards=rows(database,"""SELECT sz.zone_id,s.* FROM arrival_standard_zones sz JOIN arrival_standards s ON s.id=sz.standard_id WHERE s.active=TRUE AND s.approval_status='APPROVED'""")
    result=[]
    for zone in zones:
        for service in expected_services(zone.get("expected_services")):
            matching=[enrich_standard(item) for item in standards if item["zone_id"]==zone["id"] and item["service"]==service]
            result.append({"zone_id":zone["id"],"department":zone["department"],"zone":zone["name"],"service":service,"owner":zone["owner"],"references":len(matching),"usable":sum(1 for item in matching if item["is_usable"]),"coverage":"CURRENT" if any(item["is_usable"] for item in matching) else "PENDING"})
    return result


@app.get("/api/settings/standards-coverage")
def standard_coverage(request: Request):
    authorized(request,"settings.manage")
    with connect() as database:items=[enrich_standard(item) for item in rows(database,"SELECT * FROM arrival_standards WHERE active=TRUE")]
    result=[]
    for department in DEPARTMENTS:
        for service in STANDARD_SERVICES:
            matching=[item for item in items if item["department"]==department and item["service"]==service]
            result.append({"department":department,"service":service,"references":len(matching),"usable":sum(1 for item in matching if item["is_usable"]),"needs_review":sum(1 for item in matching if item["availability"]=="REVIEW_DUE"),"coverage":"CURRENT" if any(item["is_usable"] for item in matching) else "PENDING"})
    return result


@app.get("/api/delay-metrics")
def delay_metrics(request: Request, days: int = 30):
    authorized(request,"delays.view");days=max(1,min(days,365))
    with connect() as database:return dashboard_snapshot(database,days)["delay_metrics"]


@app.get("/api/operational-alerts")
def operational_alerts(request:Request,owner:str=""):
    authorized(request,"delays.view");authorized(request,"standards.view");today=date.today();soon=today+timedelta(days=14)
    with connect() as database:
        delays=[enrich_delay(item) for item in rows(database,"SELECT * FROM delay_zones WHERE status='VIGENTE'")]
        standards=[enrich_standard(item) for item in rows(database,"SELECT * FROM arrival_standards WHERE active=TRUE")]
    alerts=[]
    for item in delays:
        responsible=item.get("last_verified_by") or item.get("agent") or "Sin responsable"
        if item["needs_review"] or item["expiring_soon"]:alerts.append({"kind":"DELAY","severity":"OVERDUE" if item["needs_review"] else "SOON","responsible":responsible,"title":f"{item['service']} · {item['department']} · {item['zone']}","due_at":item.get("review_due_at"),"entity_id":item["id"]})
    for item in standards:
        due=item.get("review_due_at");due_date=due if isinstance(due,date) else date.fromisoformat(str(due)) if due else None;responsible=item.get("owner") or "Sin responsable"
        if item.get("approval_status")=="PENDING":alerts.append({"kind":"STANDARD_APPROVAL","severity":"OVERDUE","responsible":responsible,"title":f"Propuesta {item['service']} · {item['department']} · {item['zone']}","due_at":item.get("submitted_at"),"entity_id":item["id"]})
        elif due_date and due_date<=soon:alerts.append({"kind":"STANDARD_REVIEW","severity":"OVERDUE" if due_date<today else "SOON","responsible":responsible,"title":f"Referencia {item['service']} · {item['department']} · {item['zone']}","due_at":due,"entity_id":item["id"]})
    if owner:alerts=[item for item in alerts if normalized_key(item["responsible"])==normalized_key(owner)]
    return sorted(alerts,key=lambda item:(item["severity"]!="OVERDUE",str(item.get("due_at") or "")))


@app.get("/api/arrival-guidance")
def arrival_guidance(request: Request, department: str, service: str = "", zone: str = ""):
    authorized(request,"standards.view"); authorized(request,"delays.view")
    department_key=normalized_key(department);service_key=normalized_key(service)
    if service and service_key not in {normalized_key(item) for item in STANDARD_SERVICES}:
        raise HTTPException(422,"Prestación inválida")
    with connect() as database:
        standard_items=rows(database,"SELECT * FROM arrival_standards WHERE active=TRUE ORDER BY department,service,zone")
        delay_items=rows(database,"SELECT * FROM delay_zones WHERE status='VIGENTE' ORDER BY created_at DESC")
    standards=[enrich_standard(item) for item in standard_items if normalized_key(item["department"])==department_key and (not service_key or normalized_key(item["service"])==service_key) and zone_matches(item["zone"],zone)]
    matching_delays=[enrich_delay(item) for item in delay_items if normalized_key(item["department"])==department_key and (not service_key or normalized_key(item["service"]) in {service_key,normalized_key("TODAS")}) and zone_matches(item["zone"],zone)]
    delays=[item for item in matching_delays if item["is_current"]]
    stale_delays=[item for item in matching_delays if item["needs_review"]]
    recommended=[item for item in standards if item["is_usable"]]
    return {
        "department": department,
        "service": service or None,
        "zone": zone or None,
        "precedence": "ACTIVE_DELAY" if delays else "REVIEW_REQUIRED" if stale_delays else "STANDARD" if recommended else "NO_CONFIRMED_REFERENCE",
        "operator_message": "Comunicá la demora vigente; reemplaza temporalmente la referencia habitual." if delays else "Hay una demora sin revisión vigente; verificá su estado antes de informar un tiempo." if stale_delays else "No hay una demora vigente para esta consulta; usá una referencia confirmada y vigente." if recommended else "No hay una referencia confirmada y vigente; informá que el arribo debe confirmarse.",
        "active_delays": delays,
        "delays_needing_review": stale_delays,
        "recommended_standards": recommended,
        "standards": standards,
    }


@app.get("/api/standards")
def arrival_standards(request: Request):
    authorized(request,"standards.view")
    with connect() as database:
        items=rows(database,"SELECT * FROM arrival_standards WHERE active=TRUE ORDER BY department,service,zone")
    return [enrich_standard(item) for item in items]


LISTS = {
    "delays": ("delays.view", "SELECT * FROM delay_zones ORDER BY created_at DESC LIMIT 5000"),
    "transfers": ("transfers.view", "SELECT * FROM scheduled_transfers ORDER BY scheduled_date,scheduled_time LIMIT 5000"),
    "quotes": ("quotes.view", "SELECT * FROM quotes ORDER BY created_at DESC LIMIT 1000"),
    "audit": ("audit.view", "SELECT * FROM audit_events ORDER BY created_at DESC LIMIT 500"),
}


def filtered_notices(database, date_from="", date_to="", status="", task="", contact="", q="", scope="", managed_by="", limit=None):
    query = "SELECT * FROM notices WHERE TRUE"; values = []
    if date_from: query += " AND created_at >= %s::date"; values.append(date_from)
    if date_to: query += " AND created_at < (%s::date + interval '1 day')"; values.append(date_to)
    if status: query += " AND status=%s"; values.append(status)
    if task: query += " AND COALESCE(task_number,'') ILIKE %s"; values.append(f"%{task}%")
    if contact: query += " AND COALESCE(phone,'') ILIKE %s"; values.append(f"%{contact}%")
    if q:
        query += " AND concat_ws(' ',task_number,phone,notice_type,detail,managed_by,communicated_by,comments) ILIKE %s"; values.append(f"%{q}%")
    if scope in ("open", "unassigned", "mine", "waiting"):
        query += " AND status NOT IN ('RESUELTO','CANCELADO')"
    if scope == "unassigned":
        query += " AND COALESCE(BTRIM(managed_by),'')=''"
    if scope == "mine":
        query += " AND managed_by=%s"; values.append(managed_by)
    if scope == "waiting":
        query += " AND status='ESPERANDO_RESPUESTA'"
    query += " ORDER BY created_at DESC"
    if limit: query += f" LIMIT {int(limit)}"
    return rows(database, query, values)


@app.get("/api/notices")
def notices(request: Request, date_from: str = "", date_to: str = "", status: str = "", task: str = "", contact: str = "", q: str = "", scope: str = "", managed_by: str = ""):
    actor=authorized(request, "notices.view")
    filters={"date_from":date_from,"date_to":date_to,"status":status,"task":task,"contact":contact,"q":q,"scope":scope}
    with connect() as database:return filtered_operational_records(database,"notices",filters,actor["display_name"])


@app.get("/api/notices/assignees")
def notice_assignees(request: Request):
    authorized(request, "notices.assign")
    with connect() as database:
        return rows(database, """SELECT DISTINCT u.id,u.display_name,r.name role_name
            FROM users u JOIN roles r ON r.id=u.role_id
            JOIN role_permissions rp ON rp.role_id=r.id AND rp.permission='notices.view'
            WHERE u.active=TRUE ORDER BY u.display_name""")


@app.get("/api/notices/duplicates")
def notice_duplicate_candidates(request: Request, task_number: str = "", phone: str = "", notice_type: str = ""):
    authorized(request, "notices.create")
    with connect() as database:
        return notice_duplicates(database, {"task_number": task_number, "phone": phone, "notice_type": notice_type})


@app.get("/api/notices/{item_id}/history")
def notice_history(item_id: int, request: Request):
    authorized(request, "notices.view")
    with connect() as database:
        if not database.execute("SELECT 1 FROM notices WHERE id=%s", (item_id,)).fetchone():
            raise HTTPException(404, "Aviso inexistente")
        return rows(database, "SELECT * FROM notice_events WHERE notice_id=%s ORDER BY created_at DESC,id DESC", (item_id,))


@app.get("/api/reports/notices.csv")
def notices_report(request: Request, date_from: str = "", date_to: str = "", status: str = "", task: str = "", contact: str = "", q: str = "", scope: str = "", managed_by: str = ""):
    actor=authorized(request, "reports.export")
    filters={"date_from":date_from,"date_to":date_to,"status":status,"task":task,"contact":contact,"q":q,"scope":scope}
    with connect() as database:
        result=filtered_operational_records(database,"notices",filters,actor["display_name"])
        applied=normalized_report_filters("notices",filters,managed_by=actor["display_name"])
        audit(database,"report",0,"EXPORTADO",actor["display_name"],json.dumps({"kind":"notices","filters":applied,"rows":len(result)},ensure_ascii=False,sort_keys=True),actor_id=actor["id"],after={"kind":"notices","filters":applied,"rows":len(result)})
        content=notice_csv_bytes(result)
    return Response(content=content, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="reporte_avisos.csv"'})


@app.get("/api/quotes/history")
def quote_history(request: Request, q: str = "", coverage: str = "", mode: str = "", created_by: str = "", date_from: str = "", date_to: str = "", limit: int = 50, offset: int = 0):
    authorized(request, "quotes.view")
    limit=max(1,min(int(limit),100));offset=max(0,int(offset))
    filters={"q":q,"coverage":coverage,"mode":mode,"created_by":created_by,"date_from":date_from,"date_to":date_to}
    with connect() as database:
        result=filtered_operational_records(database,"quotes",filters)
    return {"items":result[offset:offset+limit],"total":len(result),"limit":limit,"offset":offset}


def filtered_report_rows(database, kind, date_from="", date_to="", status="", task="", department="", service="", provider="", responsible="", transfer_type="", created_by="", q=""):
    config = {
        "delays": ("delay_zones", "created_at", ("service", "department", "zone", "message", "agent")),
        "transfers": ("scheduled_transfers", "scheduled_date", ("task_number", "transfer_type", "origin", "destination", "provider", "responsible", "planner", "comments")),
        "quotes": ("quotes", "created_at", ("task_number", "origin_input", "destination_input", "mobile_input", "created_by")),
        "audit": ("audit_events", "created_at", ("entity", "action", "actor", "detail")),
    }
    if kind not in config: raise HTTPException(404, "Reporte inexistente")
    table, date_field, search_fields = config[kind]; query = f"SELECT * FROM {table} WHERE TRUE"; values = []
    if date_from: query += f" AND {date_field} >= %s::date"; values.append(date_from)
    if date_to: query += f" AND {date_field} < (%s::date + interval '1 day')"; values.append(date_to)
    allowed_fields = set(search_fields)
    if kind in ("delays", "transfers"): allowed_fields.add("status")
    for field, value in (("status", status), ("task_number", task), ("department", department), ("service", service), ("provider", provider), ("responsible", responsible), ("transfer_type", transfer_type), ("created_by", created_by)):
        if not value or field not in allowed_fields:continue
        if field=="status" and value.upper()=="ACTIVE":query+=" AND status IN ('SIN_ASIGNAR','ASIGNADO','EN_CURSO')"
        else:query += f" AND COALESCE({field},'') ILIKE %s"; values.append(f"%{value}%")
    if q:
        query += " AND concat_ws(' '," + ",".join(search_fields) + ") ILIKE %s"; values.append(f"%{q}%")
    query += f" ORDER BY {date_field} DESC"
    return rows(database, query, values)


@app.get("/api/reports/{kind}.csv")
def operational_report(kind: str, request: Request, date_from: str = "", date_to: str = "", status: str = "", scope: str = "", task: str = "", department: str = "", service: str = "", provider: str = "", responsible: str = "", transfer_type: str = "", created_by: str = "", coverage: str = "", mode: str = "", entity: str = "", entity_id: str = "", action: str = "", actor_id: str = "", q: str = ""):
    actor=authorized(request, "reports.export")
    if kind == "audit": authorized(request, "audit.view")
    names = {"delays": "demoras", "transfers": "programados", "quotes": "cotizaciones", "audit": "auditoria"}
    if kind not in names: raise HTTPException(404, "Reporte inexistente")
    filters={"date_from":date_from,"date_to":date_to,"status":status,"scope":scope,"task":task,"department":department,"service":service,"provider":provider,"responsible":responsible,"transfer_type":transfer_type,"created_by":created_by,"coverage":coverage,"mode":mode,"entity":entity,"entity_id":entity_id,"action":action,"actor_id":actor_id,"q":q}
    with connect() as database:
        result=filtered_operational_records(database,kind,filters,actor["display_name"])
        applied=normalized_report_filters(kind,filters,managed_by=actor["display_name"])
        audit(database,"report",0,"EXPORTADO",actor["display_name"],json.dumps({"kind":kind,"filters":applied,"rows":len(result)},ensure_ascii=False,sort_keys=True),actor_id=actor["id"],after={"kind":kind,"filters":applied,"rows":len(result)})
        content=report_csv_bytes(kind,result)
    return Response(content=content, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="reporte_{names[kind]}.csv"'})


@app.get("/api/dashboard")
def dashboard(request: Request):
    authorized(request, "dashboard.view")
    with connect() as database:return dashboard_snapshot(database)


@app.get("/api/transfers/duplicates")
def transfer_duplicates(request: Request, task_number: str, transfer_type: str, scheduled_date: date, scheduled_time: str = "", origin: str = "", destination: str = ""):
    authorized(request,"transfers.view")
    data=validated_business_data(clean_transfer,{"task_number":task_number,"transfer_type":transfer_type,"scheduled_date":scheduled_date,"scheduled_time":scheduled_time or None,"origin":origin,"destination":destination})
    with connect() as database:
        duplicate=transfer_duplicate(database,data)
    return [] if not duplicate else [dict(duplicate)]


@app.get("/api/transfers/responsibles")
def transfer_responsibles(request: Request):
    authorized(request,"transfers.view")
    with connect() as database:
        return rows(database,"""SELECT DISTINCT u.display_name,r.name role_name FROM users u JOIN roles r ON r.id=u.role_id
            JOIN role_permissions rp ON rp.role_id=u.role_id WHERE u.active=TRUE AND rp.permission='transfers.view' ORDER BY u.display_name""")


@app.get("/api/transfers/{item_id}/events")
def transfer_event_history(item_id:int,request:Request):
    authorized(request,"transfers.view")
    with connect() as database:
        if not database.execute("SELECT 1 FROM scheduled_transfers WHERE id=%s",(item_id,)).fetchone():raise HTTPException(404,"Programado inexistente")
        return rows(database,"SELECT * FROM transfer_events WHERE transfer_id=%s ORDER BY created_at DESC,id DESC",(item_id,))


@app.get("/api/{kind}")
def list_items(kind: str, request: Request, date_from: str = "", date_to: str = "", status: str = "", scope: str = "", transfer_type: str = "", provider: str = "", responsible: str = "", task: str = "", department: str = "", service: str = "", entity: str = "", entity_id: str = "", action: str = "", actor_id: str = "", q: str = ""):
    if kind not in LISTS: raise HTTPException(404, "Ruta inexistente")
    permission, query = LISTS[kind]; actor=authorized(request, permission)
    filters={"date_from":date_from,"date_to":date_to,"status":status,"scope":scope,"transfer_type":transfer_type,"provider":provider,"responsible":responsible,"task":task,"department":department,"service":service,"entity":entity,"entity_id":entity_id,"action":action,"actor_id":actor_id,"q":q}
    with connect() as database:
        items=filtered_operational_records(database,kind,filters,actor["display_name"])
    return items


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
        if copied or skipped:audit(database,"schedule_week",int(target_week.strftime("%Y%m%d")),"COPIA_SEMANAL",actor["display_name"],f"{source_week.isoformat()} → {target_week.isoformat()}; copiados={copied}; omitidos={skipped}",actor_id=actor["id"])
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
        created=schedule_item(database,item["id"])
        audit(database,"schedule",item["id"],"CREADO",actor["display_name"],f"{schedule_date.isoformat()} · {person['role_name']}",actor_id=actor["id"],after=created)
        return created


CREATE_CONFIG = {
    "notices": ("notices.create", "notices", ["task_number", "phone", "notice_type", "audience", "detail", "communicated_by", "managed_by", "status", "comments"], "notice"),
    "delays": ("delays.create", "delay_zones", ["service", "department", "zone", "message", "minutes", "status", "agent"], "delay"),
    "transfers": ("transfers.create", "scheduled_transfers", ["task_number", "transfer_type", "scheduled_date", "scheduled_time", "origin", "destination", "provider", "responsible", "planner", "status", "comments"], "transfer"),
}


@app.post("/api/{kind}", status_code=201)
def create_item(kind: str, request: Request, data: dict = Body(...)):
    if kind not in CREATE_CONFIG: raise HTTPException(404, "Ruta inexistente")
    permission, table, fields, entity = CREATE_CONFIG[kind]; user = authorized(request, permission)
    data = validated_body({"notices": NoticeIn, "delays": DelayIn, "transfers": TransferIn}[kind], data)
    allow_duplicate = bool(data.pop("allow_duplicate", False)) if kind in {"notices","transfers"} else False
    if kind == "notices":
        data["status"] = "PENDIENTE"
        if data.get("managed_by") and "notices.assign" not in user["permissions"]:
            raise HTTPException(403, "Su rol no tiene permiso para asignar avisos")
    elif kind == "delays":
        data = validated_business_data(clean_delay, data)
    elif kind == "transfers":
        data = validated_business_data(clean_transfer, data);data.pop("allow_duplicate",None);data["status"]="SIN_ASIGNAR"
    actor_field = {"notices": "communicated_by", "delays": "agent", "transfers": "planner"}[kind]; data[actor_field] = user["display_name"]
    defaults = {"audience": "TODOS", "status": "PENDIENTE", "service": "TODAS", "message": "Margen de"}
    values = [data.get(field, defaults.get(field)) for field in fields]; stamp = now()
    if table == "notices":extra=["created_at","updated_at"];extra_values=[stamp,stamp]
    elif table == "delay_zones":extra=["created_at","last_verified_at","expires_at","last_verified_by"];extra_values=[stamp,stamp,stamp+timedelta(minutes=data["review_minutes"]),user["display_name"]]
    elif table == "scheduled_transfers":extra=["created_at","updated_at","updated_by"];extra_values=[stamp,stamp,user["display_name"]]
    else:extra=["created_at"];extra_values=[stamp]
    columns = fields + extra; values += extra_values; placeholders = ",".join(["%s"] * len(columns))
    with connect() as database:
        if kind == "notices" and data.get("managed_by"):
            assignee = database.execute("""SELECT 1 FROM users u
                JOIN role_permissions rp ON rp.role_id=u.role_id AND rp.permission='notices.view'
                WHERE u.active=TRUE AND u.display_name=%s LIMIT 1""", (data["managed_by"],)).fetchone()
            if not assignee:
                raise HTTPException(400, "El responsable debe ser un usuario activo con acceso a Avisos")
        if kind == "notices" and not allow_duplicate:
            duplicates = notice_duplicates(database, data)
            if duplicates:
                raise HTTPException(409, {"message": "Ya existe un aviso abierto con esos datos", "duplicate": duplicates[0]})
        if kind == "delays":
            delay_key=f"delay|{normalized_key(data['department'])}|{normalized_key(data['service'])}|{normalized_key(data['zone'])}"
            database.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",(delay_key,))
            duplicate=database.execute("""SELECT id FROM delay_zones WHERE status='VIGENTE'
                AND lower(department)=lower(%s) AND lower(service)=lower(%s) AND lower(zone)=lower(%s)""",
                (data["department"],data["service"],data["zone"])).fetchone()
            if duplicate: raise HTTPException(409,"Ya existe una demora vigente para esa prestación y zona")
        if kind == "transfers":
            ensure_transfer_responsible(database,data.get("responsible"))
            duplicate_key="|".join((data["task_number"],str(data["scheduled_date"]),str(data.get("scheduled_time")),data["origin"],data["destination"]))
            database.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",(duplicate_key,))
            duplicate=transfer_duplicate(database,data)
            if duplicate and not allow_duplicate:
                raise HTTPException(409,{"message":"Ya existe un programado con la misma tarea, fecha, hora y recorrido","duplicate":transfer_duplicate_payload(duplicate)})
        item = database.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders}) RETURNING *", values).fetchone()
        if kind=="delays":
            zone_id=ensure_operational_zone(database,data["department"],data["zone"])
            item=database.execute("UPDATE delay_zones SET zone_id=%s WHERE id=%s RETURNING *",(zone_id,item["id"])).fetchone()
            record_delay_event(database,item["id"],"CREADO",user["display_name"],data["message"],item["expires_at"])
        audit(database,entity,item["id"],"CREADO",user["display_name"],"Alta confirmada pese a coincidencia abierta" if kind=="notices" and allow_duplicate else "",actor_id=user["id"],after=item)
        if kind == "notices":
            record_notice_event(database,item["id"],"CREADO",user["display_name"],f"{data['notice_type']} · {data.get('audience') or 'TODOS'}",new_value="PENDIENTE",comment=data.get("comments"))
            if data.get("managed_by"):
                record_notice_event(database,item["id"],"ASIGNACION",user["display_name"],"Responsable definido al crear",new_value=data["managed_by"])
        elif kind == "transfers":
            record_transfer_event(database,item["id"],"CREADO",user["display_name"],new_status="SIN_ASIGNAR",note="Alta confirmada pese a coincidencia" if allow_duplicate else None)
    return enrich_delay(item) if kind=="delays" else item


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
            trip_km,mobile_km = validate_manual_distances(data.get("manual_trip_km"),data.get("manual_mobile_km") if data.get("include_mobile") else 0,bool(data.get("include_mobile")))
            manual_toll_count = validate_manual_toll_count(data.get("manual_toll_count"),bool(data.get("include_tolls")))
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
                toll_price=round_currency(manual_toll_count*toll_rate)
                toll_passes=[] if not manual_toll_count else [{"name":f"Peajes manuales ({manual_toll_count})","segment":"Cantidad ingresada manualmente","price":toll_price}]
                toll_count=manual_toll_count
            else:
                catalog=rows(database,"SELECT * FROM toll_catalog WHERE active=TRUE")
                toll_passes=detect_toll_passes(segments,catalog,toll_rate);toll_price=round_currency(sum(item['price'] for item in toll_passes));toll_count=len(toll_passes)
            total_km = round_distance(trip_km + mobile_km); extra_km = calculate_extra_km(total_km, rule["included_km"]); extra_price = round_currency(extra_km * rate); total_price = round_currency(base + extra_price + toll_price); pricing_snapshot = json.dumps({"schema_version":1,"coverage":"uninsured" if uninsured else "insured","category":"gavilan" if gavilan else "special" if special else "normal","included_km":rule["included_km"],"base_price":base,"extra_rate":rate,"toll_rate":toll_rate,"mode":"manual" if manual else "automatic"},ensure_ascii=False,sort_keys=True); created_at = now(); task = str(data.get("task_number") or "").strip()
            item = database.execute("""INSERT INTO quotes(task_number,origin_input,destination_input,mobile_input,uninsured,special,gavilan,trip_km,mobile_km,total_km,included_km,extra_km,base_price,extra_price,toll_count,toll_details,toll_price,total_price,pricing_snapshot,created_by,created_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""", (task or None, data.get("origin") or "Cotización manual", data.get("destination") or "Cotización manual", data.get("mobile_origin"), uninsured, special, gavilan, trip_km, mobile_km, total_km, rule["included_km"], extra_km, base, extra_price,toll_count,json.dumps(toll_passes,ensure_ascii=False),toll_price,total_price,pricing_snapshot,user["display_name"],created_at)).fetchone()
            audit(database,"quote",item["id"],"COTIZADO",user["display_name"],f"${total_price:.0f}; peajes={toll_count}",actor_id=user["id"])
        customer_type = ("No asegurado" if uninsured else "Asegurado") + (" · Gavilán" if gavilan else " · Especial" if special else "")
        return {"id": item["id"], "task_number": task, "created_at": created_at, "origin_input": data.get("origin") or "Cotización manual", "destination_input": data.get("destination") or "Cotización manual", "mobile_input": data.get("mobile_origin"), "uninsured": uninsured, "special": special, "gavilan": gavilan, "mode": "manual" if manual else "automatic", "trip_km": trip_km, "mobile_km": mobile_km, "total_km": total_km, "included_km": rule["included_km"], "extra_km": extra_km, "base_price": base, "extra_rate": rate, "extra_price": extra_price, "toll_count":toll_count,"toll_details":toll_passes,"toll_price":toll_price,"total_price": total_price, "pricing_snapshot":json.loads(pricing_snapshot), "route_segments": segments, "customer_type": customer_type}
    except ValueError as exc: raise HTTPException(400, str(exc)) from exc


@app.patch("/api/notices/{item_id}/status")
def notice_status(item_id: int, request: Request, data: NoticeUpdateIn = Body(...)):
    data = data.model_dump(exclude_unset=True)
    if not any(key in data for key in ("status", "managed_by", "comments")):
        raise HTTPException(400, "Indique un estado, responsable o comentario")
    user = current_user(request)
    with connect() as database:
        current = database.execute("SELECT * FROM notices WHERE id=%s FOR UPDATE", (item_id,)).fetchone()
        if not current:
            raise HTTPException(404, "Aviso inexistente")
        try:
            required = notice_update_permissions(current, data)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        missing = sorted(required - set(user["permissions"]))
        if missing:
            raise HTTPException(403, "Su rol no tiene permiso para realizar esta acción")
        if "notices.assign" in required and data.get("managed_by"):
            assignee = database.execute("""SELECT 1 FROM users u
                JOIN role_permissions rp ON rp.role_id=u.role_id AND rp.permission='notices.view'
                WHERE u.active=TRUE AND u.display_name=%s LIMIT 1""", (data["managed_by"],)).fetchone()
            if not assignee:
                raise HTTPException(400, "El responsable debe ser un usuario activo con acceso a Avisos")
        next_status = data.get("status", current["status"])
        if next_status not in NOTICE_STATUSES:
            raise HTTPException(400, "Estado de aviso inválido")
        if next_status in NOTICE_CLOSED_STATUSES and next_status != current["status"] and not str(data.get("comments") or "").strip():
            raise HTTPException(400, "Indique el resultado o motivo del cierre")
        managed_by = data["managed_by"] if "managed_by" in data else current["managed_by"]
        comments = data["comments"] if "comments" in data else current["comments"]
        item = database.execute(
            "UPDATE notices SET status=%s,managed_by=%s,comments=%s,updated_at=%s WHERE id=%s RETURNING *",
            (next_status, managed_by, comments, now(), item_id),
        ).fetchone()
        changes = []
        if next_status != current["status"]:
            changes.append(f"estado: {current['status']} → {next_status}")
            record_notice_event(database,item_id,"ESTADO",user["display_name"],"Cambio de estado",current["status"],next_status)
        if managed_by != current["managed_by"]:
            changes.append(f"responsable: {managed_by or 'sin asignar'}")
            record_notice_event(database,item_id,"ASIGNACION",user["display_name"],"Cambio de responsable",current["managed_by"],managed_by)
        if comments != current["comments"]:
            changes.append("comentario actualizado")
            record_notice_event(database,item_id,"COMENTARIO",user["display_name"],"Comentario eliminado" if comments in (None,"") else "Seguimiento agregado",comment=comments)
        audit(database,"notice",item_id,"AVISO_ACTUALIZADO",user["display_name"]," · ".join(changes),actor_id=user["id"],before=current,after=item)
    return item


@app.get("/api/delays/{item_id}/events")
def delay_event_history(item_id:int,request:Request):
    authorized(request,"delays.view")
    with connect() as database:
        if not database.execute("SELECT 1 FROM delay_zones WHERE id=%s",(item_id,)).fetchone():raise HTTPException(404,"Demora inexistente")
        return rows(database,"SELECT * FROM delay_events WHERE delay_id=%s ORDER BY created_at DESC,id DESC",(item_id,))


@app.patch("/api/delays/{item_id}/verify")
def verify_delay(item_id: int, request: Request, data: DelayVerifyIn = Body(...)):
    user=authorized(request,"delays.normalize");stamp=now()
    with connect() as database:
        current=database.execute("SELECT * FROM delay_zones WHERE id=%s FOR UPDATE",(item_id,)).fetchone()
        if not current:raise HTTPException(404,"Demora inexistente")
        if current["status"]!="VIGENTE":raise HTTPException(409,"La demora ya no está vigente")
        item=database.execute("UPDATE delay_zones SET last_verified_at=%s,expires_at=%s,last_verified_by=%s WHERE id=%s RETURNING *",(stamp,stamp+timedelta(minutes=data.review_minutes),user["display_name"],item_id)).fetchone()
        record_delay_event(database,item_id,"VERIFICADO",user["display_name"],data.verification_note.strip(),item["expires_at"])
        audit(database,"delay",item_id,"VERIFICADO",user["display_name"],data.verification_note.strip(),actor_id=user["id"],before=current,after=item)
    return enrich_delay(item)


@app.patch("/api/delays/{item_id}/normalize")
def normalize_delay(item_id: int, request: Request, data: DelayNormalizeIn = Body(...)):
    data = data.model_dump()
    user = authorized(request, "delays.normalize")
    with connect() as database:
        current=database.execute("SELECT * FROM delay_zones WHERE id=%s FOR UPDATE",(item_id,)).fetchone()
        if not current: raise HTTPException(404, "Demora inexistente")
        if current["status"] != "VIGENTE": raise HTTPException(409,"La demora ya no está vigente")
        stamp=now();item = database.execute("""UPDATE delay_zones SET status='NORMALIZADO',normalized_at=%s,
            normalized_by=%s,resolution_note=%s,last_verified_at=%s,last_verified_by=%s WHERE id=%s RETURNING *""",
            (stamp,user["display_name"],data["resolution_note"].strip(),stamp,user["display_name"],item_id)).fetchone()
        record_delay_event(database,item_id,"NORMALIZADO",user["display_name"],data["resolution_note"].strip())
        audit(database,"delay",item_id,"NORMALIZADO",user["display_name"],data["resolution_note"].strip(),actor_id=user["id"],before=current,after=item)
    return enrich_delay(item)


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
        current=database.execute("SELECT * FROM work_schedules WHERE id=%s FOR UPDATE",(item_id,)).fetchone()
        if not current: raise HTTPException(404,"Horario inexistente")
        lock_schedule_slot(database,data["user_id"],schedule_date)
        conflict=postgres_schedule_conflict(database,data["user_id"],schedule_date,shift_name,data.get("start_time"),data.get("end_time"),item_id)
        if conflict:raise HTTPException(409,schedule_conflict_message(conflict))
        database.execute("""UPDATE work_schedules SET user_id=%s,schedule_date=%s,week_start=%s,role_name=%s,shift_name=%s,start_time=%s,end_time=%s,notes=%s,updated_at=%s WHERE id=%s""",(data["user_id"],schedule_date,schedule_week_start(schedule_date),person["role_name"],shift_name,data.get("start_time"),data.get("end_time"),data.get("notes"),now(),item_id))
        item=schedule_item(database,item_id)
        audit(database,"schedule",item_id,"EDITADO",actor["display_name"],f"{schedule_date.isoformat()} · {person['role_name']}",actor_id=actor["id"],before=current,after=item)
        return item

@app.delete("/api/schedules/{item_id}")
def delete_schedule(item_id: int, request: Request):
    actor=authorized(request,"schedules.manage")
    with connect() as database:
        item=database.execute("SELECT * FROM work_schedules WHERE id=%s",(item_id,)).fetchone()
        if not item: raise HTTPException(404,"Horario inexistente")
        database.execute("DELETE FROM work_schedules WHERE id=%s",(item_id,));audit(database,"schedule",item_id,"ELIMINADO",actor["display_name"],f"{item['schedule_date']} · {item['shift_name']}",actor_id=actor["id"],before=item)
    return {"ok":True}


@app.patch("/api/transfers/{item_id}/status")
def transfer_status(item_id: int, request: Request, data: TransferStatusIn = Body(...)):
    data = data.model_dump(exclude_unset=True)
    user = authorized(request, "transfers.manage")
    with connect() as database:
        current = database.execute("SELECT * FROM scheduled_transfers WHERE id=%s FOR UPDATE",(item_id,)).fetchone()
        if not current: raise HTTPException(404, "Programado inexistente")
        try:change=validate_transition(dict(current),data)
        except ValueError as exc:raise HTTPException(409 if "No se puede" in str(exc) or "ya se encuentra" in str(exc) else 400,str(exc)) from exc
        ensure_transfer_responsible(database,change["responsible"])
        stamp=now();target=change["status"]
        assigned_at=current["assigned_at"]
        started_at=current["started_at"]
        completed_at=current["completed_at"]
        cancelled_at=current["cancelled_at"]
        completion_note=current["completion_note"]
        cancellation_reason=current["cancellation_reason"]
        responsible=change["responsible"]
        if target=="SIN_ASIGNAR":assigned_at=None;responsible=None
        elif target=="ASIGNADO":assigned_at=assigned_at or stamp
        elif target=="EN_CURSO":started_at=started_at or stamp
        elif target=="FINALIZADO":completed_at=stamp;completion_note=change["note"]
        elif target=="CANCELADO":cancelled_at=stamp;cancellation_reason=change["note"]
        item=database.execute("""UPDATE scheduled_transfers SET status=%s,provider=%s,responsible=%s,assigned_at=%s,
            started_at=%s,completed_at=%s,cancelled_at=%s,completion_note=%s,cancellation_reason=%s,
            updated_at=%s,updated_by=%s WHERE id=%s RETURNING *""",
            (target,change["provider"],responsible,assigned_at,started_at,completed_at,cancelled_at,completion_note,cancellation_reason,stamp,user["display_name"],item_id)).fetchone()
        record_transfer_event(database,item_id,"ESTADO",user["display_name"],change["previous_status"],target,change["note"])
        audit(database,"transfer",item_id,"CAMBIO_ESTADO",user["display_name"],f"{change['previous_status']} → {target}",actor_id=user["id"],before=current,after=item)
    return item


@app.patch("/api/transfers/{item_id}")
def edit_transfer(item_id: int, request: Request, data: TransferEdit = Body(...)):
    data=validated_business_data(clean_transfer,data.model_dump());allow_duplicate=data.pop("allow_duplicate",False)
    user = authorized(request, "transfers.manage"); fields = ["task_number", "transfer_type", "scheduled_date", "scheduled_time", "origin", "destination", "provider", "responsible", "comments"]
    with connect() as database:
        current=database.execute("SELECT * FROM scheduled_transfers WHERE id=%s FOR UPDATE",(item_id,)).fetchone()
        if not current: raise HTTPException(404, "Registro inexistente")
        if normalized_status(current["status"]) in {"FINALIZADO","CANCELADO"}:raise HTTPException(409,"Un traslado finalizado o cancelado ya no puede editarse")
        ensure_transfer_responsible(database,data.get("responsible"))
        if normalized_status(current["status"]) in {"ASIGNADO","EN_CURSO"} and (not data.get("provider") or not data.get("responsible")):
            raise HTTPException(400,"El traslado asignado requiere prestador y responsable")
        duplicate=transfer_duplicate(database,data,item_id)
        if duplicate and not allow_duplicate:raise HTTPException(409,{"message":"Ya existe un programado con la misma tarea, fecha, hora y recorrido","duplicate":transfer_duplicate_payload(duplicate)})
        stamp=now();item = database.execute(f"UPDATE scheduled_transfers SET {','.join(field+'=%s' for field in fields)},updated_at=%s,updated_by=%s WHERE id=%s RETURNING *", [data.get(field) for field in fields] + [stamp,user["display_name"],item_id]).fetchone()
        record_transfer_event(database,item_id,"EDITADO",user["display_name"],current["status"],current["status"],"Datos operativos actualizados")
        audit(database,"transfer",item_id,"EDITADO",user["display_name"],data.get("task_number", ""),actor_id=user["id"],before=current,after=item)
    return item


@app.delete("/api/transfers/{item_id}")
def delete_transfer(item_id: int, request: Request):
    authorized(request, "transfers.manage")
    raise HTTPException(405,"Los programados se conservan. Utilice el estado Cancelado e indique el motivo")
