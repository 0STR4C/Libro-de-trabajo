"""Modo local: servidor HTTP con SQLite y autenticación corporativa."""
import hmac, json, math, re, secrets, sqlite3, time
from contextlib import closing, contextmanager
from datetime import date, datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse
try:
    from . import wfm
    from .application import APP_VERSION, DEFAULT_ROLES, NOTICE_MANAGE_PERMISSIONS, PERMISSIONS, SCHEDULE_ROLES, current_release_payload
    from .delays import DEPARTMENTS, DELAY_SERVICES, STANDARD_SERVICES, clean_delay, clean_standard, enrich_delay, normalized_key, split_zones, standard_availability, zone_matches
    from .dashboard import build_dashboard_payload
    from .identity import ALLOWED_GOOGLE_DOMAIN, parse_coordinates, route_data, route_km, valid_corporate_email, verify_google_id_token
    from .migrations import ensure_sqlite_migration_registry, reconcile_migration_checksums
    from .notices import NOTICE_AUDIENCES, NOTICE_CLOSED_STATUSES, NOTICE_STATUSES, notice_duplicate_reason, notice_duplicates, notice_update_permissions
    from .quotes import QUOTE_RULE_EXTRA_COLUMNS, QUOTE_RULE_LEGACY_COPIES, calculate_extra_km, round_currency, round_distance, validate_manual_distances, validate_manual_toll_count, validate_quote_rule_values
    from .tolls import detect_toll_passes
    from .reporting import filter_report_records, normalized_report_filters, notice_csv_bytes, report_csv_bytes
    from .scheduling import find_schedule_conflict, schedule_conflict_message, schedule_date_value, schedule_time_text
    from .security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME, csrf_token_for_session, hash_password, password_needs_rehash, verify_password
    from .transfers import TRANSFER_STATUSES, clean_transfer, normalized_status, validate_transition
except ImportError:
    import wfm
    from application import APP_VERSION, DEFAULT_ROLES, NOTICE_MANAGE_PERMISSIONS, PERMISSIONS, SCHEDULE_ROLES, current_release_payload
    from delays import DEPARTMENTS, DELAY_SERVICES, STANDARD_SERVICES, clean_delay, clean_standard, enrich_delay, normalized_key, split_zones, standard_availability, zone_matches
    from dashboard import build_dashboard_payload
    from identity import ALLOWED_GOOGLE_DOMAIN, parse_coordinates, route_data, route_km, valid_corporate_email, verify_google_id_token
    from migrations import ensure_sqlite_migration_registry, reconcile_migration_checksums
    from notices import NOTICE_AUDIENCES, NOTICE_CLOSED_STATUSES, NOTICE_STATUSES, notice_duplicate_reason, notice_duplicates, notice_update_permissions
    from quotes import QUOTE_RULE_EXTRA_COLUMNS, QUOTE_RULE_LEGACY_COPIES, calculate_extra_km, round_currency, round_distance, validate_manual_distances, validate_manual_toll_count, validate_quote_rule_values
    from tolls import detect_toll_passes
    from reporting import filter_report_records, normalized_report_filters, notice_csv_bytes, report_csv_bytes
    from scheduling import find_schedule_conflict, schedule_conflict_message, schedule_date_value, schedule_time_text
    from security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME, csrf_token_for_session, hash_password, password_needs_rehash, verify_password
    from transfers import TRANSFER_STATUSES, clean_transfer, normalized_status, validate_transition

ROOT=Path(__file__).resolve().parent; STATIC=ROOT/"static"; DB_PATH=ROOT.parent/"centro_operativo.db"; BACKUP_DIR=ROOT.parent/"backups"; HOST="127.0.0.1"; PORT=8000
SCHEMA="""
CREATE TABLE IF NOT EXISTS notices(id INTEGER PRIMARY KEY AUTOINCREMENT,task_number TEXT,phone TEXT,notice_type TEXT NOT NULL,audience TEXT NOT NULL DEFAULT 'TODOS',detail TEXT NOT NULL,communicated_by TEXT NOT NULL,managed_by TEXT,status TEXT NOT NULL DEFAULT 'PENDIENTE',comments TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS delay_zones(id INTEGER PRIMARY KEY AUTOINCREMENT,service TEXT NOT NULL,department TEXT NOT NULL,zone TEXT NOT NULL,message TEXT NOT NULL,minutes INTEGER,status TEXT NOT NULL,agent TEXT NOT NULL,created_at TEXT NOT NULL,normalized_at TEXT);
CREATE TABLE IF NOT EXISTS scheduled_transfers(id INTEGER PRIMARY KEY AUTOINCREMENT,task_number TEXT NOT NULL,transfer_type TEXT NOT NULL,scheduled_date TEXT NOT NULL,scheduled_time TEXT,origin TEXT NOT NULL,destination TEXT NOT NULL,provider TEXT,responsible TEXT,planner TEXT NOT NULL,status TEXT NOT NULL,comments TEXT,completion_note TEXT,cancellation_reason TEXT,assigned_at TEXT,started_at TEXT,completed_at TEXT,cancelled_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,updated_by TEXT);
CREATE TABLE IF NOT EXISTS work_schedules(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,schedule_date TEXT NOT NULL,week_start TEXT NOT NULL,role_name TEXT NOT NULL,shift_name TEXT NOT NULL,start_time TEXT,end_time TEXT,notes TEXT,created_by TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id));
CREATE INDEX IF NOT EXISTS work_schedules_date_idx ON work_schedules(schedule_date,week_start);
CREATE INDEX IF NOT EXISTS work_schedules_user_idx ON work_schedules(user_id,schedule_date);
CREATE TABLE IF NOT EXISTS arrival_standards(id INTEGER PRIMARY KEY AUTOINCREMENT,department TEXT NOT NULL,zone TEXT NOT NULL,service TEXT NOT NULL,minutes_min INTEGER,minutes_max INTEGER,note TEXT);
CREATE TABLE IF NOT EXISTS audit_events(id INTEGER PRIMARY KEY AUTOINCREMENT,entity TEXT NOT NULL,entity_id INTEGER NOT NULL,action TEXT NOT NULL,actor TEXT NOT NULL,detail TEXT,created_at TEXT NOT NULL,actor_id INTEGER,actor_name TEXT,before_data TEXT,after_data TEXT,correlation_id TEXT,source TEXT NOT NULL DEFAULT 'web');
CREATE TABLE IF NOT EXISTS roles(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL UNIQUE,description TEXT);
CREATE TABLE IF NOT EXISTS role_permissions(role_id INTEGER NOT NULL,permission TEXT NOT NULL,PRIMARY KEY(role_id,permission),FOREIGN KEY(role_id) REFERENCES roles(id));
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT NOT NULL UNIQUE,email TEXT UNIQUE,google_sub TEXT UNIQUE,display_name TEXT NOT NULL,password_hash TEXT NOT NULL,role_id INTEGER NOT NULL,active INTEGER NOT NULL DEFAULT 1,FOREIGN KEY(role_id) REFERENCES roles(id));
CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS schema_migrations(key TEXT PRIMARY KEY,applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS quote_rules(
 id INTEGER PRIMARY KEY CHECK(id=1),insured_base REAL NOT NULL,uninsured_base REAL NOT NULL,
 special_insured_base REAL NOT NULL,special_uninsured_base REAL NOT NULL,gavilan_base REAL NOT NULL,
 included_km REAL NOT NULL,extra_km_rate REAL NOT NULL,special_extra_km_rate REAL NOT NULL,
 gavilan_insured_base REAL NOT NULL DEFAULT 2140,gavilan_uninsured_base REAL NOT NULL DEFAULT 2140,
 transfer_insured_base REAL NOT NULL DEFAULT 2550,transfer_uninsured_base REAL NOT NULL DEFAULT 2850,
 transfer_special_insured_base REAL NOT NULL DEFAULT 4050,transfer_special_uninsured_base REAL NOT NULL DEFAULT 4470,
 locksmith_mvd_insured_base REAL NOT NULL DEFAULT 1785,locksmith_mvd_uninsured_base REAL NOT NULL DEFAULT 1930,
 locksmith_coast_insured_base REAL NOT NULL DEFAULT 2720,locksmith_coast_uninsured_base REAL NOT NULL DEFAULT 2950,
 locksmith_mvd_after22_insured_base REAL NOT NULL DEFAULT 0,locksmith_mvd_after22_uninsured_base REAL NOT NULL DEFAULT 0,
 locksmith_coast_after22_insured_base REAL NOT NULL DEFAULT 0,locksmith_coast_after22_uninsured_base REAL NOT NULL DEFAULT 0,
 extra_km_insured_rate REAL NOT NULL DEFAULT 120,extra_km_uninsured_rate REAL NOT NULL DEFAULT 90,
 special_extra_km_insured_rate REAL NOT NULL DEFAULT 120,special_extra_km_uninsured_rate REAL NOT NULL DEFAULT 110,
 toll_insured REAL NOT NULL DEFAULT 416,toll_uninsured REAL NOT NULL DEFAULT 416,
 waiting_hour_insured REAL NOT NULL DEFAULT 820,waiting_hour_uninsured REAL NOT NULL DEFAULT 820,
 rescue_hour_insured REAL NOT NULL DEFAULT 900,rescue_hour_uninsured REAL NOT NULL DEFAULT 900,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS toll_catalog(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,latitude REAL NOT NULL,longitude REAL NOT NULL,price REAL,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS quotes(id INTEGER PRIMARY KEY AUTOINCREMENT,task_number TEXT,origin_input TEXT NOT NULL,destination_input TEXT NOT NULL,mobile_input TEXT,uninsured INTEGER NOT NULL,special INTEGER NOT NULL,gavilan INTEGER NOT NULL,trip_km REAL NOT NULL,mobile_km REAL NOT NULL,total_km REAL NOT NULL,included_km REAL NOT NULL,extra_km REAL NOT NULL,base_price REAL NOT NULL,extra_price REAL NOT NULL,toll_count INTEGER NOT NULL DEFAULT 0,toll_details TEXT NOT NULL DEFAULT '[]',toll_price REAL NOT NULL DEFAULT 0,total_price REAL NOT NULL,pricing_snapshot TEXT NOT NULL DEFAULT '{}',created_by TEXT NOT NULL,created_at TEXT NOT NULL);
"""
NOTICE_EVENTS_SCHEMA="""
CREATE TABLE IF NOT EXISTS notice_events(id INTEGER PRIMARY KEY AUTOINCREMENT,notice_id INTEGER NOT NULL,event_type TEXT NOT NULL,actor TEXT NOT NULL,detail TEXT,previous_value TEXT,new_value TEXT,comment TEXT,created_at TEXT NOT NULL,FOREIGN KEY(notice_id) REFERENCES notices(id) ON DELETE CASCADE);
CREATE INDEX IF NOT EXISTS notice_events_notice_idx ON notice_events(notice_id,created_at DESC,id DESC);
"""
TRANSFER_EVENTS_SCHEMA="""
CREATE TABLE IF NOT EXISTS transfer_events(id INTEGER PRIMARY KEY AUTOINCREMENT,transfer_id INTEGER NOT NULL,event_type TEXT NOT NULL,actor TEXT NOT NULL,previous_status TEXT,new_status TEXT,note TEXT,created_at TEXT NOT NULL,FOREIGN KEY(transfer_id) REFERENCES scheduled_transfers(id) ON DELETE CASCADE);
CREATE INDEX IF NOT EXISTS transfer_events_transfer_idx ON transfer_events(transfer_id,created_at DESC,id DESC);
"""
SESSIONS={}
LOGIN_ATTEMPTS={}
LOCAL_SESSION_SECONDS=43200
LOCAL_SESSION_IDLE_SECONDS=1800
MAX_BODY_BYTES=1024*1024
LOCAL_APP_SECRET=secrets.token_urlsafe(32)
GOOGLE_NONCES={}
def now(): return datetime.now(timezone.utc).isoformat()

def schedule_week_start(value):
    parsed=datetime.strptime(str(value),"%Y-%m-%d").date()
    return (parsed-timedelta(days=parsed.weekday())).isoformat()
def schedule_time(value):
    text=str(value or "").strip()
    if not text:return None
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d",text):raise ValueError("La hora debe tener formato HH:MM")
    return text
def schedule_people(db):
    return rows(db,"SELECT u.id,u.display_name,u.role_id,r.name role_name FROM users u JOIN roles r ON r.id=u.role_id WHERE u.active=1 AND r.name IN ('Telefonista','Planificador','Supervisor') ORDER BY CASE r.name WHEN 'Supervisor' THEN 1 WHEN 'Planificador' THEN 2 ELSE 3 END,u.display_name")
def schedule_record(db,item_id):
    return db.execute("SELECT s.*,u.display_name,COALESCE(NULLIF(s.role_name,''),r.name) role_name FROM work_schedules s LEFT JOIN users u ON u.id=s.user_id LEFT JOIN roles r ON r.id=u.role_id WHERE s.id=?",(item_id,)).fetchone()
def local_schedule_conflict(db,user_id,schedule_date,shift_name,start_time,end_time,exclude_id=None):
    day=schedule_date_value(schedule_date)
    candidates=db.execute("SELECT id,schedule_date,shift_name,start_time,end_time FROM work_schedules WHERE user_id=? AND schedule_date BETWEEN ? AND ?",(user_id,(day-timedelta(days=1)).isoformat(),(day+timedelta(days=1)).isoformat())).fetchall()
    return find_schedule_conflict(candidates,day,shift_name,start_time,end_time,exclude_id)
def create_daily_backup():
    """Crea como máximo una copia consistente por día sin reemplazar copias previas."""
    if not DB_PATH.exists(): return None
    BACKUP_DIR.mkdir(parents=True,exist_ok=True)
    destination=BACKUP_DIR/f"centro_operativo_{datetime.now().strftime('%Y-%m-%d')}.db"
    if destination.exists(): return destination
    partial=BACKUP_DIR/f".{destination.name}.{secrets.token_hex(6)}.partial"
    try:
        with closing(sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro",uri=True)) as source, closing(sqlite3.connect(partial)) as target:
            source.backup(target)
            if target.execute("PRAGMA quick_check").fetchone()[0]!="ok":raise sqlite3.DatabaseError("La copia no superó la verificación de integridad")
        if destination.exists():
            partial.unlink(missing_ok=True)
        else:
            partial.replace(destination)
        return destination
    except Exception:
        partial.unlink(missing_ok=True)
        raise

@contextmanager
def connect():
    db=sqlite3.connect(DB_PATH); db.row_factory=sqlite3.Row
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
def initialize():
    with connect() as db:
        db.executescript(SCHEMA)
        ensure_sqlite_migration_registry(db)
        db.executescript(NOTICE_EVENTS_SCHEMA)
        db.executescript(TRANSFER_EVENTS_SCHEMA)
        audit_columns={r[1] for r in db.execute("PRAGMA table_info(audit_events)").fetchall()}
        for column,definition in {"actor_id":"INTEGER","actor_name":"TEXT","before_data":"TEXT","after_data":"TEXT","correlation_id":"TEXT","source":"TEXT NOT NULL DEFAULT 'web'"}.items():
            if column not in audit_columns:db.execute(f"ALTER TABLE audit_events ADD COLUMN {column} {definition}")
        if not db.execute("SELECT 1 FROM schema_migrations WHERE key='audit_contract_v2'").fetchone():
            db.execute("UPDATE audit_events SET actor_name=COALESCE(actor_name,actor),source=CASE WHEN correlation_id IS NULL THEN 'migration' ELSE COALESCE(source,'web') END,correlation_id=COALESCE(correlation_id,'legacy-'||id)")
            db.execute("UPDATE audit_events SET actor_id=(SELECT min(id) FROM users WHERE display_name=audit_events.actor_name) WHERE actor_id IS NULL")
            db.execute("INSERT INTO schema_migrations(key,applied_at) VALUES('audit_contract_v2',?)",(now(),))
        db.execute("CREATE INDEX IF NOT EXISTS audit_entity_record_idx ON audit_events(entity,entity_id,created_at DESC,id DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS audit_actor_idx ON audit_events(actor_id,created_at DESC,id DESC)")
        db.executescript("""CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT,'El registro de auditoría es inmutable'); END;
            CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT,'El registro de auditoría es inmutable'); END;""")
        if not db.execute("SELECT 1 FROM schema_migrations WHERE key='notice_events_v1'").fetchone():
            db.execute("""INSERT INTO notice_events(notice_id,event_type,actor,detail,created_at)
                SELECT entity_id,action,actor,detail,created_at FROM audit_events WHERE entity='notice' ORDER BY id""")
            db.execute("""INSERT INTO notice_events(notice_id,event_type,actor,detail,new_value,comment,created_at)
                SELECT n.id,'CREADO',n.communicated_by,n.notice_type||' · '||n.audience,n.status,n.comments,n.created_at
                FROM notices n WHERE NOT EXISTS(SELECT 1 FROM notice_events e WHERE e.notice_id=n.id)""")
            db.execute("INSERT INTO schema_migrations(key,applied_at) VALUES('notice_events_v1',?)",(now(),))
        db.executescript(wfm.SCHEMA)
        wfm.ensure_schema(db)
        transfer_columns={r[1] for r in db.execute("PRAGMA table_info(scheduled_transfers)").fetchall()}
        for column,definition in {
            "responsible":"TEXT", "completion_note":"TEXT", "cancellation_reason":"TEXT",
            "assigned_at":"TEXT", "started_at":"TEXT", "completed_at":"TEXT", "cancelled_at":"TEXT",
            "updated_at":"TEXT", "updated_by":"TEXT",
        }.items():
            if column not in transfer_columns:db.execute(f"ALTER TABLE scheduled_transfers ADD COLUMN {column} {definition}")
        db.execute("UPDATE scheduled_transfers SET status='SIN_ASIGNAR' WHERE status='PENDIENTE'")
        db.execute("UPDATE scheduled_transfers SET status='ASIGNADO' WHERE status='CONFIRMADO'")
        db.execute("UPDATE scheduled_transfers SET status='FINALIZADO' WHERE status='COMPLETADO'")
        db.execute("UPDATE scheduled_transfers SET updated_at=created_at WHERE updated_at IS NULL")
        db.execute("CREATE INDEX IF NOT EXISTS transfers_agenda_idx ON scheduled_transfers(status,scheduled_date,scheduled_time)")
        db.execute("CREATE INDEX IF NOT EXISTS transfers_task_idx ON scheduled_transfers(task_number,scheduled_date)")
        if not db.execute("SELECT 1 FROM schema_migrations WHERE key='transfer_workflow_v1'").fetchone():
            db.execute("""INSERT INTO transfer_events(transfer_id,event_type,actor,new_status,note,created_at)
                SELECT id,'CREADO',planner,status,'Registro existente incorporado al historial',created_at
                FROM scheduled_transfers""")
            db.execute("INSERT INTO schema_migrations(key,applied_at) VALUES('transfer_workflow_v1',?)",(now(),))
        delay_columns={r[1] for r in db.execute("PRAGMA table_info(delay_zones)").fetchall()}
        for column,definition in {
            "normalized_by":"TEXT", "resolution_note":"TEXT", "last_verified_at":"TEXT", "expires_at":"TEXT", "last_verified_by":"TEXT", "zone_id":"INTEGER"
        }.items():
            if column not in delay_columns:db.execute(f"ALTER TABLE delay_zones ADD COLUMN {column} {definition}")
        db.execute("UPDATE delay_zones SET last_verified_at=created_at WHERE last_verified_at IS NULL")
        db.execute("CREATE INDEX IF NOT EXISTS delay_active_lookup_idx ON delay_zones(status,department,service,zone)")
        standard_columns={r[1] for r in db.execute("PRAGMA table_info(arrival_standards)").fetchall()}
        for column,definition in {
            "status":"TEXT NOT NULL DEFAULT 'PROVISIONAL'", "source":"TEXT", "reviewed_by":"TEXT",
            "effective_from":"TEXT", "review_due_at":"TEXT", "active":"INTEGER NOT NULL DEFAULT 1",
            "created_at":"TEXT", "updated_at":"TEXT", "owner":"TEXT NOT NULL DEFAULT 'Supervisión'", "review_interval_days":"INTEGER NOT NULL DEFAULT 90",
            "approval_status":"TEXT NOT NULL DEFAULT 'APPROVED'", "submitted_by":"TEXT", "submitted_at":"TEXT", "approved_by":"TEXT", "approved_at":"TEXT", "approval_note":"TEXT"
        }.items():
            if column not in standard_columns:db.execute(f"ALTER TABLE arrival_standards ADD COLUMN {column} {definition}")
        db.execute("UPDATE arrival_standards SET created_at=COALESCE(created_at,?),updated_at=COALESCE(updated_at,?)",(now(),now()))
        db.execute("CREATE INDEX IF NOT EXISTS arrival_standard_lookup_idx ON arrival_standards(active,department,service,zone)")
        db.executescript("""CREATE TABLE IF NOT EXISTS operational_zones(
            id INTEGER PRIMARY KEY AUTOINCREMENT,department TEXT NOT NULL,name TEXT NOT NULL,normalized_name TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
            UNIQUE(department,normalized_name));
            CREATE TABLE IF NOT EXISTS arrival_standard_zones(
            standard_id INTEGER NOT NULL REFERENCES arrival_standards(id) ON DELETE CASCADE,
            zone_id INTEGER NOT NULL REFERENCES operational_zones(id),PRIMARY KEY(standard_id,zone_id));
            CREATE TABLE IF NOT EXISTS delay_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,delay_id INTEGER NOT NULL REFERENCES delay_zones(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,actor TEXT NOT NULL,note TEXT,review_due_at TEXT,created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS delay_events_delay_idx ON delay_events(delay_id,created_at DESC);
            CREATE TABLE IF NOT EXISTS standard_versions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,standard_id INTEGER NOT NULL REFERENCES arrival_standards(id) ON DELETE CASCADE,
            version INTEGER NOT NULL,action TEXT NOT NULL,actor TEXT NOT NULL,reason TEXT,snapshot TEXT NOT NULL,created_at TEXT NOT NULL,
            UNIQUE(standard_id,version));
            CREATE INDEX IF NOT EXISTS standard_versions_standard_idx ON standard_versions(standard_id,version DESC);""")
        zone_columns={r[1] for r in db.execute("PRAGMA table_info(operational_zones)").fetchall()}
        for column,definition in {"owner":"TEXT NOT NULL DEFAULT 'Supervisión'","expected_services":"TEXT NOT NULL DEFAULT '[]'"}.items():
            if column not in zone_columns:db.execute(f"ALTER TABLE operational_zones ADD COLUMN {column} {definition}")
        user_columns={r[1] for r in db.execute("PRAGMA table_info(users)").fetchall()}
        if "email" not in user_columns:db.execute("ALTER TABLE users ADD COLUMN email TEXT")
        if "google_sub" not in user_columns:db.execute("ALTER TABLE users ADD COLUMN google_sub TEXT")
        quote_rule_columns={r[1] for r in db.execute("PRAGMA table_info(quote_rules)").fetchall()}
        added_quote_rule_columns=[]
        for column,default in QUOTE_RULE_EXTRA_COLUMNS.items():
            if column not in quote_rule_columns:
                db.execute(f"ALTER TABLE quote_rules ADD COLUMN {column} REAL NOT NULL DEFAULT {float(default)}")
                added_quote_rule_columns.append(column)
        quote_columns={r[1] for r in db.execute("PRAGMA table_info(quotes)").fetchall()}
        if "task_number" not in quote_columns:db.execute("ALTER TABLE quotes ADD COLUMN task_number TEXT")
        for column,definition in {"toll_count":"INTEGER NOT NULL DEFAULT 0","toll_details":"TEXT NOT NULL DEFAULT '[]'","toll_price":"REAL NOT NULL DEFAULT 0","pricing_snapshot":"TEXT NOT NULL DEFAULT '{}'"}.items():
            if column not in quote_columns:db.execute(f"ALTER TABLE quotes ADD COLUMN {column} {definition}")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique ON users(lower(email)) WHERE email IS NOT NULL")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_google_sub_unique ON users(google_sub) WHERE google_sub IS NOT NULL")
        db.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES('google_client_id','')")
        db.execute("INSERT OR REPLACE INTO app_settings(key,value) VALUES('google_allowed_domain',?)",(ALLOWED_GOOGLE_DOMAIN,))
        for role_name,permissions in DEFAULT_ROLES.items():
            role=db.execute("SELECT id FROM roles WHERE name=?",(role_name,)).fetchone()
            if not role:
                role_id=db.execute("INSERT INTO roles(name,description) VALUES(?,?)",(role_name,f"Rol {role_name}")).lastrowid
                db.executemany("INSERT INTO role_permissions(role_id,permission) VALUES(?,?)",[(role_id,p) for p in permissions])
        if not db.execute("SELECT 1 FROM schema_migrations WHERE key='notice_permissions_v1'").fetchone():
            legacy_roles=db.execute("SELECT DISTINCT role_id FROM role_permissions WHERE permission='notices.manage'").fetchall()
            for (role_id,) in legacy_roles:
                role_name=db.execute("SELECT name FROM roles WHERE id=?",(role_id,)).fetchone()
                if role_name and role_name[0] != "Administrador":
                    db.executemany("INSERT OR IGNORE INTO role_permissions(role_id,permission) VALUES(?,?)",[(role_id,p) for p in NOTICE_MANAGE_PERMISSIONS])
                    db.execute("DELETE FROM role_permissions WHERE role_id=? AND permission='notices.manage'",(role_id,))
            db.execute("INSERT INTO schema_migrations(key,applied_at) VALUES('notice_permissions_v1',?)",(now(),))
        if not db.execute("SELECT 1 FROM schema_migrations WHERE key='quotes_permissions_v1'").fetchone():
            for role_name in ("Administrador","Supervisor","Planificador","Telefonista"):
                role_id=db.execute("SELECT id FROM roles WHERE name=?",(role_name,)).fetchone()[0]
                db.executemany("INSERT OR IGNORE INTO role_permissions(role_id,permission) VALUES(?,?)",[(role_id,"quotes.view"),(role_id,"quotes.create")])
            db.execute("INSERT INTO schema_migrations(key,applied_at) VALUES('quotes_permissions_v1',?)",(now(),))
        if not db.execute("SELECT 1 FROM schema_migrations WHERE key='standards_workflow_v1'").fetchone():
            for role_name in ("Supervisor","Planificador","Telefonista"):
                role=db.execute("SELECT id FROM roles WHERE name=?",(role_name,)).fetchone()
                if role:db.execute("INSERT OR IGNORE INTO role_permissions(role_id,permission) VALUES(?,?)",(role[0],"standards.propose"))
            supervisor=db.execute("SELECT id FROM roles WHERE name='Supervisor'").fetchone()
            if supervisor:db.execute("INSERT OR IGNORE INTO role_permissions(role_id,permission) VALUES(?,?)",(supervisor[0],"standards.approve"))
            db.execute("INSERT INTO schema_migrations(key,applied_at) VALUES('standards_workflow_v1',?)",(now(),))
        admin_role=db.execute("SELECT id FROM roles WHERE name='Administrador'").fetchone()[0]
        db.execute("DELETE FROM role_permissions WHERE role_id=?",(admin_role,))
        db.executemany("INSERT INTO role_permissions(role_id,permission) VALUES(?,?)",[(admin_role,p) for p in PERMISSIONS])
        if not db.execute("SELECT 1 FROM schema_migrations WHERE key='audit_admin_only_v1'").fetchone():
            db.execute("DELETE FROM role_permissions WHERE permission='audit.view' AND role_id<>?",(admin_role,))
            db.execute("INSERT INTO schema_migrations(key,applied_at) VALUES('audit_admin_only_v1',?)",(now(),))
        if not db.execute("SELECT 1 FROM schema_migrations WHERE key='reports_export_v1'").fetchone():
            supervisor=db.execute("SELECT id FROM roles WHERE name='Supervisor'").fetchone()
            if supervisor:db.execute("INSERT OR IGNORE INTO role_permissions(role_id,permission) VALUES(?,?)",(supervisor[0],"reports.export"))
            db.execute("INSERT INTO schema_migrations(key,applied_at) VALUES('reports_export_v1',?)",(now(),))
        if not db.execute("SELECT 1 FROM schema_migrations WHERE key='schedules_permissions_v1'").fetchone():
            for role_name in ("Supervisor","Planificador"):
                role=db.execute("SELECT id FROM roles WHERE name=?",(role_name,)).fetchone()
                if role:db.executemany("INSERT OR IGNORE INTO role_permissions(role_id,permission) VALUES(?,?)",[(role[0],"schedules.view"),(role[0],"schedules.manage")])
            phone=db.execute("SELECT id FROM roles WHERE name='Telefonista'").fetchone()
            if phone:db.execute("INSERT OR IGNORE INTO role_permissions(role_id,permission) VALUES(?,?)",(phone[0],"schedules.view"))
            db.execute("INSERT INTO schema_migrations(key,applied_at) VALUES('schedules_permissions_v1',?)",(now(),))
        if not db.execute("SELECT 1 FROM users LIMIT 1").fetchone(): db.execute("INSERT INTO users(username,display_name,password_hash,role_id,active) VALUES(?,?,?,?,1)",("admin","Administrador",hash_password("admin1234"),admin_role))
        db.execute("INSERT OR IGNORE INTO quote_rules(id,insured_base,uninsured_base,special_insured_base,special_uninsured_base,gavilan_base,included_km,extra_km_rate,special_extra_km_rate,updated_at) VALUES(1,2140,2750,4050,4470,2140,25,120,120,?)",(now(),))
        if added_quote_rule_columns:
            assignments=[f"{column}={QUOTE_RULE_LEGACY_COPIES[column]}" for column in added_quote_rule_columns if column in QUOTE_RULE_LEGACY_COPIES]
            if assignments:db.execute(f"UPDATE quote_rules SET {','.join(assignments)} WHERE id=1")
        if not db.execute("SELECT 1 FROM arrival_standards LIMIT 1").fetchone():
            standard_stamp=now()
            db.executemany("INSERT INTO arrival_standards(department,zone,service,minutes_min,minutes_max,note,status,source,reviewed_by,effective_from,active,created_at,updated_at) VALUES(?,?,?,?,?,?,'PROVISIONAL','Configuración inicial','Sistema',?,1,?,?)",[(*item,date.today().isoformat(),standard_stamp,standard_stamp) for item in [("MONTEVIDEO","Centro, Parque Rodó, Pocitos, Punta Carretas, Tres Cruces, Buceo","ML",None,30,None),("MONTEVIDEO","Nuevo París, Cerro, Colón, Casavalle, Peñarol, La Teja, Manga","ML",None,45,None),("MONTEVIDEO","Ciudad","GRÚA",None,45,None),("CANELONES","Ciudad de la Costa","ML",None,45,None),("ARTIGAS","Artigas","ML",None,45,None),("ARTIGAS","Artigas","GRÚA",None,60,None),("MALDONADO","Maldonado Ciudad, Piriápolis","ML",30,45,None),("INTERIOR","Zona no listada","ML",None,None,"A confirmar")]])
        for standard in db.execute("SELECT id,department,zone FROM arrival_standards").fetchall():
            sync_standard_zones(db,standard["id"],standard["department"],standard["zone"])
            if not db.execute("SELECT 1 FROM standard_versions WHERE standard_id=?",(standard["id"],)).fetchone():record_standard_version(db,standard["id"],"BASELINE","Sistema","Versión inicial conservada")
        for delay in db.execute("SELECT id,department,zone FROM delay_zones WHERE zone_id IS NULL").fetchall():db.execute("UPDATE delay_zones SET zone_id=? WHERE id=?",(ensure_operational_zone(db,delay["department"],delay["zone"]),delay["id"]))
        reconcile_migration_checksums(db, {
            "audit_contract_v2": "audit_contract_v2",
            "notice_events_v1": NOTICE_EVENTS_SCHEMA,
            "transfer_workflow_v1": TRANSFER_EVENTS_SCHEMA,
            "notice_permissions_v1": "notice_permissions_v1",
            "quotes_permissions_v1": "quotes_permissions_v1",
            "standards_workflow_v1": "standards_workflow_v1",
            "audit_admin_only_v1": "audit_admin_only_v1",
            "reports_export_v1": "reports_export_v1",
            "schedules_permissions_v1": "schedules_permissions_v1",
        })
def rows(db,sql,p=()): return [dict(r) for r in db.execute(sql,p).fetchall()]

def ensure_operational_zone(db,department,name):
    clean_name=" ".join(str(name or "").split());key=normalized_key(clean_name);stamp=now()
    db.execute("INSERT INTO operational_zones(department,name,normalized_name,created_at,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(department,normalized_name) DO UPDATE SET name=excluded.name,active=1,updated_at=excluded.updated_at",(department,clean_name,key,stamp,stamp))
    return db.execute("SELECT id FROM operational_zones WHERE department=? AND normalized_name=?",(department,key)).fetchone()[0]

def sync_standard_zones(db,standard_id,department,zone_text):
    db.execute("DELETE FROM arrival_standard_zones WHERE standard_id=?",(standard_id,))
    for name in split_zones(zone_text):db.execute("INSERT OR IGNORE INTO arrival_standard_zones(standard_id,zone_id) VALUES(?,?)",(standard_id,ensure_operational_zone(db,department,name)))

def record_delay_event(db,delay_id,event_type,actor,note=None,review_due_at=None):db.execute("INSERT INTO delay_events(delay_id,event_type,actor,note,review_due_at,created_at) VALUES(?,?,?,?,?,?)",(delay_id,event_type,actor,note,review_due_at,now()))

def record_standard_version(db,standard_id,action,actor,reason=None):
    item=dict(db.execute("SELECT * FROM arrival_standards WHERE id=?",(standard_id,)).fetchone());version=db.execute("SELECT COALESCE(max(version),0)+1 FROM standard_versions WHERE standard_id=?",(standard_id,)).fetchone()[0]
    db.execute("INSERT INTO standard_versions(standard_id,version,action,actor,reason,snapshot,created_at) VALUES(?,?,?,?,?,?,?)",(standard_id,version,action,actor,reason,json.dumps(item,ensure_ascii=False,sort_keys=True),now()))

def expected_services(value):
    try:items=json.loads(value or "[]") if isinstance(value,str) else list(value or [])
    except (TypeError,ValueError):items=[]
    return [service for service in STANDARD_SERVICES if service in items]

def dashboard_snapshot(db,days=30,current_time=None):
    as_of=current_time or datetime.now(timezone.utc);cutoff=(as_of-timedelta(days=days)).isoformat()
    notice_counts=rows(db,"SELECT status,count(*) total FROM notices GROUP BY status")
    active_delays=rows(db,"SELECT * FROM delay_zones WHERE status='VIGENTE'")
    transfer_counts=rows(db,"SELECT status,count(*) total FROM scheduled_transfers GROUP BY status")
    period_delays=rows(db,"SELECT * FROM delay_zones WHERE (created_at>=? AND created_at<=?) OR (normalized_at>=? AND normalized_at<=?)",(cutoff,as_of.isoformat(),cutoff,as_of.isoformat()))
    verification_events=db.execute("SELECT count(*) FROM delay_events WHERE event_type='VERIFICADO' AND created_at>=? AND created_at<=?",(cutoff,as_of.isoformat())).fetchone()[0]
    standards=rows(db,"SELECT * FROM arrival_standards WHERE active=1")
    zones=rows(db,"SELECT expected_services FROM operational_zones WHERE active=1")
    return build_dashboard_payload(
        notice_status_counts=notice_counts,active_delays=active_delays,
        transfer_status_counts=transfer_counts,period_delays=period_delays,
        verification_events=verification_events,standards=standards,
        expected_zone_services=sum(len(expected_services(zone.get("expected_services"))) for zone in zones),
        days=days,current_time=as_of,
    )

def _audit_json(value):
    if value is None:return None
    blocked=("password","token","secret","cookie","google_sub")
    cleaned={key:item for key,item in dict(value).items() if not any(marker in key.casefold() for marker in blocked)} if hasattr(value,"keys") else value
    return json.dumps(cleaned,ensure_ascii=False,sort_keys=True,default=str)

def _audit_snapshot(db,entity,entity_id):
    tables={"notice":"notices","delay":"delay_zones","transfer":"scheduled_transfers","schedule":"work_schedules","quote":"quotes","quote_rules":"quote_rules","toll":"toll_catalog","arrival_standard":"arrival_standards","operational_zone":"operational_zones","user":"users","role":"roles"}
    table=tables.get(entity)
    if not table or not entity_id:return None
    row=db.execute(f"SELECT * FROM {table} WHERE id=?",(entity_id,)).fetchone()
    if not row:return None
    result=dict(row)
    if entity=="role":result["permissions"]=[item[0] for item in db.execute("SELECT permission FROM role_permissions WHERE role_id=? ORDER BY permission",(entity_id,)).fetchall()]
    return result

def audit(db,e,i,a,actor,d="",*,actor_id=None,before=None,after=None,correlation_id=None,source="web"):
    if actor_id is None and actor not in {"Autenticación","Sistema"}:
        match=db.execute("SELECT id FROM users WHERE display_name=? ORDER BY active DESC,id LIMIT 1",(actor,)).fetchone()
        actor_id=match[0] if match else None
    if before is None:
        previous=db.execute("SELECT after_data FROM audit_events WHERE entity=? AND entity_id=? AND after_data IS NOT NULL ORDER BY id DESC LIMIT 1",(e,i)).fetchone()
        if previous:
            try:before=json.loads(previous[0])
            except (TypeError,ValueError):before=None
    if after is None:after=_audit_snapshot(db,e,i)
    db.execute("""INSERT INTO audit_events(entity,entity_id,action,actor,detail,created_at,actor_id,actor_name,before_data,after_data,correlation_id,source)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",(e,i,a,actor,d,now(),actor_id,actor,_audit_json(before),_audit_json(after),correlation_id or secrets.token_hex(12),source))
def record_notice_event(db,notice_id,event_type,actor,detail="",previous_value=None,new_value=None,comment=None):
    db.execute("""INSERT INTO notice_events(notice_id,event_type,actor,detail,previous_value,new_value,comment,created_at)
        VALUES(?,?,?,?,?,?,?,?)""",(notice_id,event_type,actor,detail,previous_value,new_value,comment,now()))

def record_transfer_event(db,transfer_id,event_type,actor,previous_status=None,new_status=None,note=None):
    db.execute("INSERT INTO transfer_events(transfer_id,event_type,actor,previous_status,new_status,note,created_at) VALUES(?,?,?,?,?,?,?)",(transfer_id,event_type,actor,previous_status,new_status,note,now()))

def transfer_duplicate(db,data,exclude_id=None):
    query="""SELECT * FROM scheduled_transfers WHERE status<>'CANCELADO'
        AND lower(trim(task_number))=lower(trim(?)) AND scheduled_date=?
        AND scheduled_time IS ? AND lower(trim(origin))=lower(trim(?))
        AND lower(trim(destination))=lower(trim(?))"""
    scheduled_date=data["scheduled_date"].isoformat() if isinstance(data["scheduled_date"],date) else data["scheduled_date"]
    scheduled_time=data.get("scheduled_time");scheduled_time=scheduled_time.strftime("%H:%M") if hasattr(scheduled_time,"strftime") else scheduled_time
    values=[data["task_number"],scheduled_date,scheduled_time,data["origin"],data["destination"]]
    if exclude_id is not None:query+=" AND id<>?";values.append(exclude_id)
    return db.execute(query+" ORDER BY id LIMIT 1",values).fetchone()

def ensure_transfer_responsible(db,responsible):
    if not responsible:return
    item=db.execute("""SELECT 1 FROM users u JOIN role_permissions rp ON rp.role_id=u.role_id
        WHERE u.active=1 AND rp.permission='transfers.view' AND u.display_name=? LIMIT 1""",(responsible,)).fetchone()
    if not item:raise ValueError("El responsable debe ser un usuario activo con acceso a Programados")

def filtered_transfers(db,params):
    query="SELECT * FROM scheduled_transfers WHERE 1=1";values=[]
    def one(name):return params.get(name,[""])[0]
    if one("date_from"):query+=" AND scheduled_date>=?";values.append(one("date_from"))
    if one("date_to"):query+=" AND scheduled_date<=?";values.append(one("date_to"))
    if one("status"):
        if one("status").upper()=="ACTIVE":query+=" AND status IN ('SIN_ASIGNAR','ASIGNADO','EN_CURSO')"
        else:query+=" AND status=?";values.append(normalized_status(one("status")))
    if one("transfer_type"):query+=" AND transfer_type=?";values.append(one("transfer_type"))
    for column,name in (("provider","provider"),("responsible","responsible"),("task_number","task")):
        if one(name):query+=f" AND lower(COALESCE({column},'')) LIKE lower(?)";values.append(f"%{one(name)}%")
    if one("q"):
        query+=" AND lower(COALESCE(task_number,'')||' '||COALESCE(transfer_type,'')||' '||COALESCE(origin,'')||' '||COALESCE(destination,'')||' '||COALESCE(provider,'')||' '||COALESCE(responsible,'')||' '||COALESCE(planner,'')||' '||COALESCE(comments,'')) LIKE lower(?)";values.append(f"%{one('q')}%")
    return rows(db,query+" ORDER BY scheduled_date,scheduled_time,id LIMIT 20000",values)

def request_filters(params):
    return {key:str(values[0]).strip() for key,values in params.items() if values and str(values[0]).strip()}

def filtered_operational_records(db,kind,params,managed_by=""):
    table={"notices":"notices","delays":"delay_zones","transfers":"scheduled_transfers","quotes":"quotes","audit":"audit_events"}[kind]
    items=rows(db,f"SELECT * FROM {table}")
    if kind=="delays":items=[enrich_delay(item) for item in items]
    return filter_report_records(kind,items,request_filters(params),managed_by=managed_by)

def standard_is_overdue(item):
    due=item.get("review_due_at")
    return bool(due and str(due)<date.today().isoformat())

def enrich_standard(item):
    result=dict(item);result["availability"]=standard_availability(result)
    approval=result.get("approval_status") or "APPROVED"
    if approval!="APPROVED":result["availability"]="PENDING_APPROVAL" if approval=="PENDING" else "REJECTED"
    result["is_overdue"]=result["availability"]=="REVIEW_DUE";result["is_usable"]=result["availability"]=="CURRENT" and approval=="APPROVED"
    return result

def normalized_business_data(cleaner,data):
    try:return cleaner(data)
    except (TypeError,ValueError) as exc:raise ValueError(str(exc)) from exc

def setting(db,key,default=""):
    row=db.execute("SELECT value FROM app_settings WHERE key=?",(key,)).fetchone()
    return row[0] if row else default


def login_attempt_key(identifier, source_ip):
    return hmac.new(LOCAL_APP_SECRET.encode(), f"{str(identifier).strip().lower()}|{source_ip}".encode(), "sha256").hexdigest()


def login_limit(key):
    stamp=time.time(); item=LOGIN_ATTEMPTS.get(key)
    if not item or item["window"]<=stamp-900:
        LOGIN_ATTEMPTS[key]={"failures":0,"window":stamp,"blocked":0};return 0
    return max(0,int(item["blocked"]-stamp))


def register_login_failure(key):
    stamp=time.time();item=LOGIN_ATTEMPTS.get(key)
    if not item or item["window"]<=stamp-900:item={"failures":0,"window":stamp,"blocked":0}
    item["failures"]+=1
    if item["failures"]>=5:item["blocked"]=stamp+min(60*2**(item["failures"]-5),900)
    LOGIN_ATTEMPTS[key]=item
    return max(0,int(item["blocked"]-stamp))


def clear_login_failures(key):LOGIN_ATTEMPTS.pop(key,None)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=str(STATIC),**kw)
    def log_message(self,*a): pass
    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' https://accounts.google.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://*.tile.openstreetmap.org; font-src 'self'; connect-src 'self' https://accounts.google.com; frame-src https://accounts.google.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'")
        if self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()
    def send_json(self,v,status=200,extra_headers=()):
        b=json.dumps(v,ensure_ascii=False).encode(); self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(b)))
        for name,value in extra_headers:self.send_header(name,value)
        self.end_headers(); self.wfile.write(b)
    def send_bytes(self,value,content_type,filename):
        self.send_response(200);self.send_header("Content-Type",content_type);self.send_header("Content-Disposition",f'attachment; filename="{filename}"');self.send_header("Content-Length",str(len(value)));self.end_headers();self.wfile.write(value)
    def payload(self): return json.loads(self.rfile.read(int(self.headers.get("Content-Length",0))) or b"{}")
    def cookie_value(self,name):
        cookie=SimpleCookie();cookie.load(self.headers.get("Cookie",""));item=cookie.get(name);return item.value if item else ""
    def session_token(self):return self.cookie_value(SESSION_COOKIE_NAME)
    def auth_cookie_headers(self,token):
        csrf=csrf_token_for_session(token,LOCAL_APP_SECRET);base=f"SameSite=Strict; Path=/; Max-Age={LOCAL_SESSION_SECONDS}"
        return (("Set-Cookie",f"{SESSION_COOKIE_NAME}={token}; HttpOnly; {base}"),("Set-Cookie",f"{CSRF_COOKIE_NAME}={csrf}; {base}"))
    def clear_cookie_headers(self):
        return (("Set-Cookie",f"{SESSION_COOKIE_NAME}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"),("Set-Cookie",f"{CSRF_COOKIE_NAME}=; SameSite=Strict; Path=/; Max-Age=0"))
    def csrf_guard(self):
        origin=self.headers.get("Origin","").rstrip("/")
        if origin and origin not in {"http://127.0.0.1:8000","http://localhost:8000"}:self.send_json({"detail":"Origen no autorizado"},403);return False
        token=self.session_token()
        if not token:self.send_json({"detail":"Debe iniciar sesión"},401);return False
        supplied=self.headers.get(CSRF_HEADER_NAME,"");cookie=self.cookie_value(CSRF_COOKIE_NAME);expected=csrf_token_for_session(token,LOCAL_APP_SECRET)
        if not supplied or not hmac.compare_digest(supplied,cookie) or not hmac.compare_digest(supplied,expected):self.send_json({"detail":"La validación de seguridad de la solicitud falló"},403);return False
        return True
    def body_size_guard(self):
        try:size=int(self.headers.get("Content-Length",0))
        except ValueError:size=MAX_BODY_BYTES+1
        if size>MAX_BODY_BYTES:self.send_json({"detail":"El cuerpo de la solicitud es demasiado grande"},413);return False
        return True
    def current_user(self):
        token=self.session_token();session=SESSIONS.get(token);stamp=time.time()
        if not session or session["expires"]<=stamp or session["last_seen"]<=stamp-LOCAL_SESSION_IDLE_SECONDS:
            SESSIONS.pop(token,None);return None
        session["last_seen"]=stamp;user_id=session["user_id"]
        with connect() as db:
            row=db.execute("SELECT u.id,u.username,u.email,u.display_name,u.active,r.id role_id,r.name role_name FROM users u JOIN roles r ON r.id=u.role_id WHERE u.id=? AND u.active=1",(user_id,)).fetchone()
            if not row: return None
            user=dict(row); user["permissions"]=[r[0] for r in db.execute("SELECT permission FROM role_permissions WHERE role_id=?",(user["role_id"],)).fetchall()]; return user
    def require(self,permission):
        user=self.current_user()
        if not user: self.send_json({"detail":"Debe iniciar sesión"},401); return None
        if permission == 'schedules.manage' and not wfm.manager(user):self.send_json({'detail':'Solo Supervisor o Administrador puede gestionar horarios'},403);return None
        if permission not in user["permissions"]: self.send_json({"detail":"Su rol no tiene permiso para realizar esta acción"},403); return None
        return user
    def wfm_request(self, method, data=None):
        actor=self.require('schedules.view')
        if not actor:return
        parsed=urlparse(self.path)
        params={k:v[0] for k,v in parse_qs(parsed.query).items()}
        try:
            with connect() as db:
                result=wfm.dispatch(db,actor,method,parsed.path.rsplit('/',1)[-1],params,data)
                if method == 'POST':
                    action_name=parsed.path.rsplit('/',1)[-1]
                    if action_name == 'plan':
                        operation=(data or {}).get('operation','save')
                        event={'save':'BORRADOR_GUARDADO','optimize':'DESCANSOS_SUGERIDOS','publish':'HORARIOS_PUBLICADOS'}.get(operation,'PLAN_ACTUALIZADO')
                        detail=f"{params.get('date','')} · {params.get('team','')} · revisión {result.get('revision',0)}"
                    elif action_name == 'requirements':
                        event='REQUERIMIENTOS_ACTUALIZADOS';detail=f"Equipo {params.get('team','')}"
                    elif action_name == 'settings':
                        event='CONFIGURACION_WFM_ACTUALIZADA';detail=f"Turno {result.get('shift_minutes',0)} min · descanso {result.get('break_minutes',0)} min"
                    elif action_name == 'requests':
                        decision=(data or {}).get('decision')
                        operation=(data or {}).get('operation')
                        event='SOLICITUD_WFM_CANCELADA' if operation=='cancel' else {'APROBAR':'SOLICITUD_WFM_APROBADA','RECHAZAR':'SOLICITUD_WFM_RECHAZADA'}.get(decision,'SOLICITUD_WFM_CREADA')
                        detail=f"{result.get('request_id','')} · {result.get('requested_date','')} · {result.get('request_type','')}"
                    elif action_name == 'publish-week':
                        event='SEMANA_WFM_PUBLICADA';detail=f"{result.get('week','')} · {result.get('team','')} · {result.get('published_count',0)} días"
                    else:
                        event='WFM_ACTUALIZADO';detail=params.get('team','')
                    audit(db,'wfm',0,event,actor['display_name'],detail,actor_id=actor['id'])
            return self.send_json(result)
        except wfm.WfmError as error:
            return self.send_json({'detail':str(error)},error.status)
        except Exception:
            return self.send_json({'detail':'No se pudo completar la operación WFM. Reiniciá el servicio y volvé a intentar.'},500)
    def do_GET(self):
        parsed=urlparse(self.path);path=parsed.path;params=parse_qs(parsed.query)
        if path.startswith('/api/wfm/'):return self.wfm_request('GET')
        if path=="/health": return self.send_json({"status":"ok"})
        if not path.startswith("/api/"):
            if path=="/": self.path="/index.html"
            elif path.startswith("/static/"): self.path=path.removeprefix("/static")
            return super().do_GET()
        if path=="/api/auth/me":
            user=self.current_user(); return self.send_json(user if user else {"detail":"Debe iniciar sesión"},200 if user else 401)
        if path=="/api/auth/google-config":
            stamp=time.time()
            for nonce,expires in list(GOOGLE_NONCES.items()):
                if expires<stamp:GOOGLE_NONCES.pop(nonce,None)
            nonce=secrets.token_urlsafe(24); GOOGLE_NONCES[nonce]=stamp+3600
            with connect() as db:client_id=setting(db,"google_client_id")
            return self.send_json({"enabled":bool(client_id),"client_id":client_id,"allowed_domain":ALLOWED_GOOGLE_DOMAIN,"nonce":nonce})
        if path=="/api/settings/permissions":
            if not self.require("settings.manage"): return
            return self.send_json([{"key":k,"label":v} for k,v in PERMISSIONS.items()])
        if path=="/api/settings/roles":
            if not self.require("settings.manage"): return
            with connect() as db:
                result=[]
                for role in rows(db,"SELECT * FROM roles ORDER BY name"):
                    role["permissions"]=[r[0] for r in db.execute("SELECT permission FROM role_permissions WHERE role_id=? ORDER BY permission",(role["id"],)).fetchall()]; result.append(role)
            return self.send_json(result)
        if path=="/api/settings/users":
            if not self.require("settings.manage"): return
            with connect() as db: return self.send_json(rows(db,"SELECT u.id,u.username,u.email,u.google_sub IS NOT NULL google_linked,u.display_name,u.active,u.role_id,r.name role_name FROM users u JOIN roles r ON r.id=u.role_id ORDER BY u.display_name"))
        if path=="/api/settings/google-access":
            if not self.require("settings.manage"):return
            with connect() as db:return self.send_json({"client_id":setting(db,"google_client_id"),"allowed_domain":ALLOWED_GOOGLE_DOMAIN,"enabled":bool(setting(db,"google_client_id"))})
        if path=="/api/settings/quote-rules":
            if not self.require("settings.manage"):return
            with connect() as db:return self.send_json(dict(db.execute("SELECT * FROM quote_rules WHERE id=1").fetchone()))
        if path=="/api/settings/tolls":
            if not self.require("settings.manage"):return
            with connect() as db:return self.send_json(rows(db,"SELECT * FROM toll_catalog ORDER BY name"))
        if path=="/api/settings/version":
            if not self.require("settings.manage"):return
            return self.send_json(current_release_payload())
        if path=="/api/schedules/people":
            actor=self.require('schedules.view')
            if not actor:return
            with connect() as db:return self.send_json([p for p in schedule_people(db) if wfm.manager(actor) or p['id']==actor['id']])
        if path in ("/api/schedules","/api/reports/schedules.csv"):
            permission="reports.export" if path.startswith("/api/reports/") else "schedules.view"
            actor=self.require(permission)
            if not actor:return
            def value(name):return str(params.get(name,[""])[0]).strip()
            try:
                week=schedule_week_start(value("week")) if value("week") else ""
                date_from=datetime.strptime(value("date_from"),"%Y-%m-%d").date().isoformat() if value("date_from") else ""
                date_to=datetime.strptime(value("date_to"),"%Y-%m-%d").date().isoformat() if value("date_to") else ""
                employee_id=int(value("employee_id")) if value("employee_id") else None
            except (ValueError,TypeError):return self.send_json({"detail":"El período o la persona indicada no es válido"},400)
            if not wfm.manager(actor):employee_id=actor['id']
            if path.startswith("/api/reports/"):
                report_params={"week":week.isoformat() if hasattr(week,'isoformat') else week,"date_from":date_from,"date_to":date_to,"role":value("role"),"q":value("q")}
                if employee_id is not None:report_params["employee_id"]=str(employee_id)
                with connect() as db:
                    result=wfm._published_schedules(db.execute,report_params,False)
                    audit(db,"report",0,"EXPORTADO",actor["display_name"],json.dumps({"kind":"schedules","filters":report_params,"rows":len(result)},ensure_ascii=False,sort_keys=True),actor_id=actor["id"],after={"kind":"schedules","filters":report_params,"rows":len(result)})
                return self.send_bytes(report_csv_bytes("schedules",result),"text/csv; charset=utf-8","reporte_horarios.csv")
            query="SELECT s.id,s.user_id,s.schedule_date,s.week_start,COALESCE(NULLIF(s.role_name,''),r.name,'') role_name,s.shift_name,s.start_time,s.end_time,s.notes,s.created_by,s.created_at,s.updated_at,COALESCE(u.display_name,'Usuario no disponible') display_name FROM work_schedules s LEFT JOIN users u ON u.id=s.user_id LEFT JOIN roles r ON r.id=u.role_id WHERE 1=1";values=[]
            if week:query+=" AND s.week_start=?";values.append(week)
            else:
                if date_from:query+=" AND s.schedule_date>=?";values.append(date_from)
                if date_to:query+=" AND s.schedule_date<=?";values.append(date_to)
            if employee_id is not None:query+=" AND s.user_id=?";values.append(employee_id)
            if value("role"):query+=" AND COALESCE(NULLIF(s.role_name,''),r.name)=?";values.append(value("role"))
            if value("q"):
                query+=" AND lower(COALESCE(u.display_name,'')||' '||COALESCE(s.role_name,'')||' '||COALESCE(s.shift_name,'')||' '||COALESCE(s.notes,'')) LIKE lower(?)";values.append(f"%{value('q')}%")
            query+=" ORDER BY s.schedule_date,s.start_time,display_name LIMIT 20000"
            with connect() as db:result=rows(db,query,values)
            return self.send_json(result)
        notice_history_match=re.fullmatch(r"/api/notices/(\d+)/history",path)
        if notice_history_match:
            if not self.require("notices.view"):return
            item_id=int(notice_history_match.group(1))
            with connect() as db:
                if not db.execute("SELECT 1 FROM notices WHERE id=?",(item_id,)).fetchone():return self.send_json({"detail":"Aviso inexistente"},404)
                return self.send_json(rows(db,"SELECT * FROM notice_events WHERE notice_id=? ORDER BY created_at DESC,id DESC",(item_id,)))
        if path=="/api/notices/duplicates":
            if not self.require("notices.create"):return
            def duplicate_value(name):return str(params.get(name,[""])[0]).strip()
            with connect() as db:
                return self.send_json(notice_duplicates(db,{"task_number":duplicate_value("task_number"),"phone":duplicate_value("phone"),"notice_type":duplicate_value("notice_type")}))
        if path=="/api/notices/assignees":
            if not self.require("notices.assign"):return
            with connect() as db:
                return self.send_json(rows(db,"""SELECT DISTINCT u.id,u.display_name,r.name role_name
                    FROM users u JOIN roles r ON r.id=u.role_id
                    JOIN role_permissions rp ON rp.role_id=r.id AND rp.permission='notices.view'
                    WHERE u.active=1 ORDER BY u.display_name"""))
        if path in ("/api/notices","/api/reports/notices.csv"):
            permission="reports.export" if path.startswith("/api/reports/") else "notices.view"
            actor=self.require(permission)
            if not actor:return
            with connect() as db:
                result=filtered_operational_records(db,"notices",params,actor["display_name"])
                if path.startswith("/api/reports/"):
                    applied=normalized_report_filters("notices",request_filters(params),managed_by=actor["display_name"])
                    audit(db,"report",0,"EXPORTADO",actor["display_name"],json.dumps({"kind":"notices","filters":applied,"rows":len(result)},ensure_ascii=False,sort_keys=True),actor_id=actor["id"],after={"kind":"notices","filters":applied,"rows":len(result)})
            if path.startswith("/api/reports/"):return self.send_bytes(notice_csv_bytes(result),"text/csv; charset=utf-8","reporte_avisos.csv")
            return self.send_json(result)
        if path=="/api/quotes/history":
            if not self.require("quotes.view"):return
            def value(name):return str(params.get(name,[""])[0]).strip()
            try:
                limit=max(1,min(100,int(value("limit") or 50)));offset=max(0,int(value("offset") or 0))
            except (TypeError,ValueError):return self.send_json({"detail":"La paginación indicada no es válida"},400)
            with connect() as db:
                result=filtered_operational_records(db,"quotes",params)
            return self.send_json({"items":result[offset:offset+limit],"total":len(result),"limit":limit,"offset":offset})
        report_paths={"/api/reports/delays.csv":("delays","delay_zones","created_at",["service","department","zone","message","agent"],"demoras"),"/api/reports/transfers.csv":("transfers","scheduled_transfers","scheduled_date",["task_number","transfer_type","origin","destination","provider","responsible","planner","comments"],"programados"),"/api/reports/quotes.csv":("quotes","quotes","created_at",["task_number","origin_input","destination_input","mobile_input","created_by"],"cotizaciones"),"/api/reports/audit.csv":("audit","audit_events","created_at",["entity","action","actor","detail"],"auditoria")}
        if path in report_paths:
            if report_paths[path][0]=="audit" and not self.require("audit.view"):return
            actor=self.require("reports.export")
            if not actor:return
            kind,table,date_field,search_fields,filename=report_paths[path]
            with connect() as db:
                result=filtered_operational_records(db,kind,params,actor["display_name"])
                applied=normalized_report_filters(kind,request_filters(params),managed_by=actor["display_name"])
                audit(db,"report",0,"EXPORTADO",actor["display_name"],json.dumps({"kind":kind,"filters":applied,"rows":len(result)},ensure_ascii=False,sort_keys=True),actor_id=actor["id"],after={"kind":kind,"filters":applied,"rows":len(result)})
            return self.send_bytes(report_csv_bytes(kind,result),"text/csv; charset=utf-8",f"reporte_{filename}.csv")
        if path=="/api/settings/standards":
            if not self.require("settings.manage"):return
            with connect() as db:result=rows(db,"SELECT * FROM arrival_standards ORDER BY active DESC,department,service,zone")
            return self.send_json([enrich_standard(item) for item in result])
        if path=="/api/settings/standards-coverage":
            if not self.require("settings.manage"):return
            with connect() as db:items=[enrich_standard(item) for item in rows(db,"SELECT * FROM arrival_standards WHERE active=1")]
            result=[]
            for department in DEPARTMENTS:
                for service in STANDARD_SERVICES:
                    matching=[item for item in items if item["department"]==department and item["service"]==service]
                    result.append({"department":department,"service":service,"references":len(matching),"usable":sum(1 for item in matching if item["is_usable"]),"needs_review":sum(1 for item in matching if item["availability"]=="REVIEW_DUE"),"coverage":"CURRENT" if any(item["is_usable"] for item in matching) else "PENDING"})
            return self.send_json(result)
        if path=="/api/zones":
            if not self.require("standards.view"):return
            department=str(params.get("department",[""])[0]).strip();query="""SELECT z.*,count(DISTINCT sz.standard_id) reference_count,count(DISTINCT d.id) delay_count FROM operational_zones z LEFT JOIN arrival_standard_zones sz ON sz.zone_id=z.id LEFT JOIN delay_zones d ON d.zone_id=z.id WHERE z.active=1""";values=[]
            if department:query+=" AND lower(z.department)=lower(?)";values.append(department)
            query+=" GROUP BY z.id ORDER BY z.department,z.name"
            with connect() as db:items=rows(db,query,values)
            for item in items:item["expected_services"]=expected_services(item.get("expected_services"))
            return self.send_json(items)
        if path=="/api/zones-coverage":
            if not self.require("standards.view"):return
            department=str(params.get("department",[""])[0]).strip();query="SELECT * FROM operational_zones WHERE active=1";values=[]
            if department:query+=" AND lower(department)=lower(?)";values.append(department)
            query+=" ORDER BY department,name"
            with connect() as db:
                zones=rows(db,query,values);standards=rows(db,"SELECT sz.zone_id,s.* FROM arrival_standard_zones sz JOIN arrival_standards s ON s.id=sz.standard_id WHERE s.active=1 AND s.approval_status='APPROVED'")
            result=[]
            for zone in zones:
                for service in expected_services(zone.get("expected_services")):
                    matching=[enrich_standard(item) for item in standards if item["zone_id"]==zone["id"] and item["service"]==service]
                    result.append({"zone_id":zone["id"],"department":zone["department"],"zone":zone["name"],"service":service,"owner":zone["owner"],"references":len(matching),"usable":sum(1 for item in matching if item["is_usable"]),"coverage":"CURRENT" if any(item["is_usable"] for item in matching) else "PENDING"})
            return self.send_json(result)
        if path.startswith("/api/delays/") and path.endswith("/events"):
            if not self.require("delays.view"):return
            try:item_id=int(path.split("/")[3])
            except ValueError:return self.send_json({"detail":"Demora inválida"},400)
            with connect() as db:
                if not db.execute("SELECT 1 FROM delay_zones WHERE id=?",(item_id,)).fetchone():return self.send_json({"detail":"Demora inexistente"},404)
                return self.send_json(rows(db,"SELECT * FROM delay_events WHERE delay_id=? ORDER BY created_at DESC,id DESC",(item_id,)))
        if path.startswith("/api/settings/standards/") and path.endswith("/versions"):
            if not self.require("standards.view"):return
            try:item_id=int(path.split("/")[4])
            except ValueError:return self.send_json({"detail":"Referencia inválida"},400)
            with connect() as db:
                if not db.execute("SELECT 1 FROM arrival_standards WHERE id=?",(item_id,)).fetchone():return self.send_json({"detail":"Referencia inexistente"},404)
                items=rows(db,"SELECT * FROM standard_versions WHERE standard_id=? ORDER BY version DESC",(item_id,))
            for item in items:item["snapshot"]=json.loads(item["snapshot"])
            return self.send_json(items)
        if path=="/api/delay-metrics":
            if not self.require("delays.view"):return
            try:days=max(1,min(int(params.get("days",["30"])[0]),365))
            except (TypeError,ValueError):return self.send_json({"detail":"El período no es válido"},400)
            with connect() as db:return self.send_json(dashboard_snapshot(db,days)["delay_metrics"])
        if path=="/api/operational-alerts":
            if not self.require("delays.view") or not self.require("standards.view"):return
            owner=str(params.get("owner",[""])[0]).strip();today=date.today();soon=today+timedelta(days=14)
            with connect() as db:delays=[enrich_delay(item) for item in rows(db,"SELECT * FROM delay_zones WHERE status='VIGENTE'")];standards=[enrich_standard(item) for item in rows(db,"SELECT * FROM arrival_standards WHERE active=1")]
            alerts=[]
            for item in delays:
                responsible=item.get("last_verified_by") or item.get("agent") or "Sin responsable"
                if item["needs_review"] or item["expiring_soon"]:alerts.append({"kind":"DELAY","severity":"OVERDUE" if item["needs_review"] else "SOON","responsible":responsible,"title":f"{item['service']} · {item['department']} · {item['zone']}","due_at":item.get("review_due_at"),"entity_id":item["id"]})
            for item in standards:
                due=item.get("review_due_at");due_date=date.fromisoformat(str(due)[:10]) if due else None;responsible=item.get("owner") or "Sin responsable"
                if item.get("approval_status")=="PENDING":alerts.append({"kind":"STANDARD_APPROVAL","severity":"OVERDUE","responsible":responsible,"title":f"Propuesta {item['service']} · {item['department']} · {item['zone']}","due_at":item.get("submitted_at"),"entity_id":item["id"]})
                elif due_date and due_date<=soon:alerts.append({"kind":"STANDARD_REVIEW","severity":"OVERDUE" if due_date<today else "SOON","responsible":responsible,"title":f"Referencia {item['service']} · {item['department']} · {item['zone']}","due_at":due,"entity_id":item["id"]})
            if owner:alerts=[item for item in alerts if normalized_key(item["responsible"])==normalized_key(owner)]
            return self.send_json(sorted(alerts,key=lambda item:(item["severity"]!="OVERDUE",str(item.get("due_at") or ""))))
        if path=="/api/arrival-guidance":
            if not self.require("standards.view"):return
            if not self.require("delays.view"):return
            department=str(params.get("department",[""])[0]).strip()
            service=str(params.get("service",[""])[0]).strip()
            zone=str(params.get("zone",[""])[0]).strip()
            if not department:return self.send_json({"detail":"Indique el departamento"},400)
            with connect() as db:
                standard_items=rows(db,"SELECT * FROM arrival_standards WHERE active=1 ORDER BY department,service,zone")
                delay_items=rows(db,"SELECT * FROM delay_zones WHERE status='VIGENTE' ORDER BY created_at DESC")
            standards=[enrich_standard(item) for item in standard_items if normalized_key(item["department"])==normalized_key(department) and (not service or normalized_key(item["service"])==normalized_key(service)) and zone_matches(item["zone"],zone)]
            matching_delays=[enrich_delay(item) for item in delay_items if normalized_key(item["department"])==normalized_key(department) and (normalized_key(item["service"])=="todas" or not service or normalized_key(item["service"])==normalized_key(service)) and zone_matches(item["zone"],zone)]
            active_delays=[item for item in matching_delays if item["is_current"]];stale_delays=[item for item in matching_delays if item["needs_review"]];recommended=[item for item in standards if item["is_usable"]]
            message="Comunicá la demora vigente; reemplaza temporalmente la referencia habitual." if active_delays else "Hay una demora sin revisión vigente; verificá su estado antes de informar un tiempo." if stale_delays else "No hay una demora vigente para esta consulta; usá una referencia confirmada y vigente." if recommended else "No hay una referencia confirmada y vigente; informá que el arribo debe confirmarse."
            return self.send_json({"department":department,"service":service or None,"zone":zone or None,"precedence":"ACTIVE_DELAY" if active_delays else "REVIEW_REQUIRED" if stale_delays else "STANDARD" if recommended else "NO_CONFIRMED_REFERENCE","operator_message":message,"active_delays":active_delays,"delays_needing_review":stale_delays,"recommended_standards":recommended,"standards":standards})
        transfer_history_match=re.fullmatch(r"/api/transfers/(\d+)/events",path)
        if transfer_history_match:
            if not self.require("transfers.view"):return
            item_id=int(transfer_history_match.group(1))
            with connect() as db:
                if not db.execute("SELECT 1 FROM scheduled_transfers WHERE id=?",(item_id,)).fetchone():return self.send_json({"detail":"Programado inexistente"},404)
                return self.send_json(rows(db,"SELECT * FROM transfer_events WHERE transfer_id=? ORDER BY created_at DESC,id DESC",(item_id,)))
        if path=="/api/transfers/responsibles":
            if not self.require("transfers.view"):return
            with connect() as db:return self.send_json(rows(db,"""SELECT DISTINCT u.display_name,r.name role_name FROM users u JOIN roles r ON r.id=u.role_id JOIN role_permissions rp ON rp.role_id=u.role_id WHERE u.active=1 AND rp.permission='transfers.view' ORDER BY u.display_name"""))
        if path=="/api/transfers/duplicates":
            if not self.require("transfers.view"):return
            def transfer_value(name):return str(params.get(name,[""])[0]).strip()
            try:data=clean_transfer({"task_number":transfer_value("task_number"),"transfer_type":transfer_value("transfer_type"),"scheduled_date":transfer_value("scheduled_date"),"scheduled_time":transfer_value("scheduled_time") or None,"origin":transfer_value("origin"),"destination":transfer_value("destination")})
            except ValueError as exc:return self.send_json({"detail":str(exc)},422)
            with connect() as db:duplicate=transfer_duplicate(db,data)
            return self.send_json([] if not duplicate else [dict(duplicate)])
        view_permissions={"/api/dashboard":"dashboard.view","/api/notices":"notices.view","/api/delays":"delays.view","/api/transfers":"transfers.view","/api/quotes":"quotes.view","/api/standards":"standards.view","/api/audit":"audit.view"}
        actor=self.require(view_permissions[path]) if path in view_permissions else None
        if path in view_permissions and not actor:return
        with connect() as db:
            if path=="/api/dashboard":
                return self.send_json(dashboard_snapshot(db))
            q={"/api/delays":"SELECT * FROM delay_zones ORDER BY created_at DESC LIMIT 5000","/api/transfers":"SELECT * FROM scheduled_transfers ORDER BY scheduled_date,scheduled_time LIMIT 5000","/api/quotes":"SELECT * FROM quotes ORDER BY created_at DESC LIMIT 1000","/api/standards":"SELECT * FROM arrival_standards WHERE active=1 ORDER BY department,zone","/api/audit":"SELECT * FROM audit_events ORDER BY created_at DESC LIMIT 500"}
            if path in q:
                kind=path.removeprefix("/api/")
                result=filtered_operational_records(db,kind,params,actor["display_name"]) if kind in {"delays","transfers","quotes","audit"} else rows(db,q[path])
                if path=="/api/standards":result=[enrich_standard(item) for item in result]
                return self.send_json(result)
        self.send_json({"detail":"Ruta inexistente"},404)
    def do_POST(self):
        if not self.body_size_guard():return
        path=urlparse(self.path).path; d=self.payload(); stamp=now(); cfg={"/api/notices":("notices",["task_number","phone","notice_type","audience","detail","communicated_by","managed_by","status","comments"],"notice",d.get("communicated_by","Operador")),"/api/delays":("delay_zones",["service","department","zone","message","minutes","status","agent"],"delay",d.get("agent","Operador")),"/api/transfers":("scheduled_transfers",["task_number","transfer_type","scheduled_date","scheduled_time","origin","destination","provider","planner","status","comments"],"transfer",d.get("planner","Operador"))}
        if path not in ("/api/auth/login","/api/auth/google") and not self.csrf_guard():return
        if path=="/api/settings/zones":
            actor=self.require("standards.approve")
            if not actor:return
            department=" ".join(str(d.get("department") or "").split()).upper();name=" ".join(str(d.get("name") or "").split());owner=" ".join(str(d.get("owner") or "Supervisión").split());services=[service for service in STANDARD_SERVICES if service in (d.get("expected_services") or [])]
            if department not in set(DEPARTMENTS)|{"INTERIOR"}:return self.send_json({"detail":"Departamento inválido"},422)
            if len(name)<2 or len(owner)<2:return self.send_json({"detail":"Indique zona y responsable"},422)
            stamp=now()
            with connect() as db:
                db.execute("INSERT INTO operational_zones(department,name,normalized_name,owner,expected_services,active,created_at,updated_at) VALUES(?,?,?,?,?,1,?,?) ON CONFLICT(department,normalized_name) DO UPDATE SET name=excluded.name,owner=excluded.owner,expected_services=excluded.expected_services,active=1,updated_at=excluded.updated_at",(department,name,normalized_key(name),owner,json.dumps(services,ensure_ascii=False),stamp,stamp));item=dict(db.execute("SELECT * FROM operational_zones WHERE department=? AND normalized_name=?",(department,normalized_key(name))).fetchone());audit(db,"operational_zone",item["id"],"COBERTURA_CONFIGURADA",actor["display_name"],f"{department} · {name} · {', '.join(services) or 'sin prestaciones esperadas'}",actor_id=actor["id"])
            item["expected_services"]=services;return self.send_json(item,201)
        if path=="/api/standards/proposals":
            actor=self.require("standards.propose")
            if not actor:return
            try:item=normalized_business_data(clean_standard,d)
            except ValueError as exc:return self.send_json({"detail":str(exc)},422)
            stamp=now()
            with connect() as db:
                duplicate=db.execute("SELECT id FROM arrival_standards WHERE active=1 AND lower(department)=lower(?) AND lower(service)=lower(?) AND lower(zone)=lower(?)",(item["department"],item["service"],item["zone"])).fetchone()
                if duplicate:return self.send_json({"detail":"Ya existe una referencia activa para esa prestación y zona"},409)
                cur=db.execute("INSERT INTO arrival_standards(department,zone,service,minutes_min,minutes_max,note,status,source,reviewed_by,effective_from,review_due_at,owner,review_interval_days,approval_status,submitted_by,submitted_at,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'PENDING',?,?,1,?,?)",(item["department"],item["zone"],item["service"],item["minutes_min"],item["minutes_max"],item["note"],item["status"],item["source"],actor["display_name"],item["effective_from"].isoformat() if item["effective_from"] else None,item["review_due_at"].isoformat() if item["review_due_at"] else None,item["owner"],item["review_interval_days"],actor["display_name"],stamp,stamp,stamp));sync_standard_zones(db,cur.lastrowid,item["department"],item["zone"]);record_standard_version(db,cur.lastrowid,"SUBMITTED",actor["display_name"],"Propuesta enviada");audit(db,"arrival_standard",cur.lastrowid,"PROPUESTO",actor["display_name"],f"{item['department']} · {item['service']} · {item['zone']}",actor_id=actor["id"]);created=dict(db.execute("SELECT * FROM arrival_standards WHERE id=?",(cur.lastrowid,)).fetchone())
            return self.send_json(enrich_standard(created),201)
        if path.startswith('/api/wfm/'):return self.wfm_request('POST',d)
        if path=="/api/auth/login":
            login=str(d.get("username","")).strip()
            key=login_attempt_key(login,self.client_address[0]);retry=login_limit(key)
            if retry:
                with connect() as db:audit(db,"session",0,"INGRESO_BLOQUEADO","Autenticación",f"huella={key[:16]}")
                return self.send_json({"detail":"Demasiados intentos. Intente nuevamente más tarde."},429,(('Retry-After',str(retry)),))
            with connect() as db:
                row=db.execute("SELECT * FROM users WHERE (lower(username)=lower(?) OR lower(email)=lower(?)) AND active=1",(login,login)).fetchone()
                valid=bool(row and verify_password(d.get("password",""),row["password_hash"]))
                if valid and password_needs_rehash(row["password_hash"]):db.execute("UPDATE users SET password_hash=? WHERE id=?",(hash_password(d.get("password","")),row["id"]))
                if not valid:
                    retry=register_login_failure(key);audit(db,"session",row["id"] if row else 0,"INGRESO_BLOQUEADO" if retry else "INGRESO_FALLIDO","Autenticación",f"huella={key[:16]}")
            if not valid:
                if retry:return self.send_json({"detail":"Demasiados intentos. Intente nuevamente más tarde."},429,(('Retry-After',str(retry)),))
                return self.send_json({"detail":"Usuario o contraseña incorrectos"},401)
            clear_login_failures(key)
            SESSIONS.pop(self.session_token(),None);token=secrets.token_urlsafe(32);stamp=time.time();SESSIONS[token]={"user_id":row["id"],"expires":stamp+LOCAL_SESSION_SECONDS,"last_seen":stamp};return self.send_json({"ok":True},extra_headers=self.auth_cookie_headers(token))
        if path=="/api/auth/google":
            google_key=login_attempt_key("google",self.client_address[0]);retry=login_limit(google_key)
            if retry:
                with connect() as db:audit(db,"session",0,"INGRESO_BLOQUEADO","Autenticación",f"huella={google_key[:16]}")
                return self.send_json({"detail":"Demasiados intentos. Intente nuevamente más tarde."},429,(('Retry-After',str(retry)),))
            nonce=str(d.get("nonce") or ""); expires=GOOGLE_NONCES.get(nonce,0)
            if expires<time.time():
                retry=register_login_failure(google_key)
                with connect() as db:audit(db,"session",0,"INGRESO_BLOQUEADO" if retry else "INGRESO_FALLIDO","Autenticación",f"huella={google_key[:16]}")
                return self.send_json({"detail":"No se pudo completar la autenticación"},429 if retry else 401,(('Retry-After',str(retry)),) if retry else ())
            with connect() as db:client_id=setting(db,"google_client_id")
            if not client_id:return self.send_json({"detail":"El ingreso con Google todavía no está configurado"},503)
            try:identity=verify_google_id_token(str(d.get("credential") or ""),client_id,nonce)
            except ValueError:
                retry=register_login_failure(google_key)
                with connect() as db:audit(db,"session",0,"INGRESO_BLOQUEADO" if retry else "INGRESO_FALLIDO","Autenticación",f"huella={google_key[:16]}")
                return self.send_json({"detail":"No se pudo completar la autenticación"},429 if retry else 401,(('Retry-After',str(retry)),) if retry else ())
            with connect() as db:
                row=db.execute("SELECT * FROM users WHERE lower(email)=? AND active=1",(identity["email"],)).fetchone()
                if not row or (row["google_sub"] and row["google_sub"]!=identity["sub"]):
                    retry=register_login_failure(google_key);audit(db,"session",row["id"] if row else 0,"INGRESO_BLOQUEADO" if retry else "INGRESO_FALLIDO","Autenticación",f"huella={google_key[:16]}")
                    return self.send_json({"detail":"No se pudo completar la autenticación"},429 if retry else 401,(('Retry-After',str(retry)),) if retry else ())
                try:db.execute("UPDATE users SET google_sub=? WHERE id=?",(identity["sub"],row["id"]));audit(db,"user",row["id"],"INGRESO_GOOGLE",row["display_name"],identity["email"],actor_id=row["id"])
                except sqlite3.IntegrityError:return self.send_json({"detail":"Esta cuenta de Google ya está vinculada a otro usuario"},403)
            clear_login_failures(google_key)
            SESSIONS.pop(self.session_token(),None);token=secrets.token_urlsafe(32);stamp=time.time();SESSIONS[token]={"user_id":row["id"],"expires":stamp+LOCAL_SESSION_SECONDS,"last_seen":stamp};return self.send_json({"ok":True},extra_headers=self.auth_cookie_headers(token))
        if path=="/api/auth/logout":
            session=SESSIONS.pop(self.session_token(),None)
            if session:
                with connect() as db:
                    user=db.execute("SELECT id,display_name FROM users WHERE id=?",(session["user_id"],)).fetchone()
                    if user:audit(db,"session",user["id"],"SALIDA",user["display_name"],actor_id=user["id"])
            return self.send_json({"ok":True},extra_headers=self.clear_cookie_headers())
        if path=="/api/schedules/copy-week":
            actor=self.require("schedules.manage")
            if not actor:return
            try:
                source_week=schedule_week_start(str(d.get("source_week") or ""));target_week=schedule_week_start(str(d.get("target_week") or ""))
                raw_employee=d.get("employee_id");employee_id=int(raw_employee) if raw_employee not in (None,"") else None
            except (TypeError,ValueError):return self.send_json({"detail":"Las semanas o la persona indicadas no son válidas"},400)
            role=str(d.get("role") or "").strip()
            if employee_id is not None and employee_id<=0:return self.send_json({"detail":"La persona indicada no es válida"},400)
            if source_week==target_week:return self.send_json({"detail":"La semana de origen y destino deben ser diferentes"},400)
            if role and role not in SCHEDULE_ROLES:return self.send_json({"detail":"El rol indicado no pertenece al equipo operativo"},400)
            source_day=schedule_date_value(source_week);target_day=schedule_date_value(target_week)
            with connect() as db:
                db.execute("BEGIN IMMEDIATE")
                query="""SELECT s.*,r.name current_role FROM work_schedules s JOIN users u ON u.id=s.user_id JOIN roles r ON r.id=u.role_id
                    WHERE s.week_start=? AND s.schedule_date BETWEEN ? AND ? AND u.active=1 AND r.name IN ('Telefonista','Planificador','Supervisor')""";values=[source_week,source_week,(source_day+timedelta(days=6)).isoformat()]
                if employee_id is not None:query+=" AND s.user_id=?";values.append(employee_id)
                if role:query+=" AND r.name=?";values.append(role)
                query+=" ORDER BY s.user_id,s.schedule_date,s.start_time,s.id"
                source_rows=db.execute(query,values).fetchall();copied=0;skipped=0
                for source in source_rows:
                    target_date=(target_day+timedelta(days=(schedule_date_value(source["schedule_date"])-source_day).days)).isoformat()
                    start_time=schedule_time_text(source["start_time"]);end_time=schedule_time_text(source["end_time"])
                    if start_time is not None and start_time==end_time:
                        skipped+=1;continue
                    if local_schedule_conflict(db,source["user_id"],target_date,source["shift_name"],start_time,end_time):
                        skipped+=1;continue
                    db.execute("INSERT INTO work_schedules(user_id,schedule_date,week_start,role_name,shift_name,start_time,end_time,notes,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(source["user_id"],target_date,target_week,source["current_role"],source["shift_name"],start_time,end_time,source["notes"],actor["display_name"],stamp,stamp));copied+=1
                if copied or skipped:audit(db,"schedule_week",int(target_week.replace("-","")),"COPIA_SEMANAL",actor["display_name"],f"{source_week} → {target_week}; copiados={copied}; omitidos={skipped}",actor_id=actor["id"])
            return self.send_json({"copied":copied,"skipped":skipped,"source_week":source_week,"target_week":target_week})
        if path=="/api/schedules":
            actor=self.require("schedules.manage")
            if not actor:return
            try:
                user_id=int(d.get("user_id")); schedule_date=datetime.strptime(str(d.get("schedule_date") or ""),"%Y-%m-%d").date().isoformat(); start_time=schedule_time(d.get("start_time")); end_time=schedule_time(d.get("end_time"))
            except (TypeError,ValueError):return self.send_json({"detail":"La persona, fecha u hora del horario no es válida"},400)
            if (start_time is None)!=(end_time is None):return self.send_json({"detail":"Complete ambas horas o deje ambas vacías"},400)
            if start_time is not None and start_time==end_time:return self.send_json({"detail":"La hora de inicio y fin no pueden ser iguales"},400)
            shift_name=str(d.get("shift_name") or "").strip(); notes=str(d.get("notes") or "").strip()
            if len(shift_name)<2 or len(shift_name)>80:return self.send_json({"detail":"Indique el turno del horario"},400)
            if len(notes)>2000:return self.send_json({"detail":"Las notas no pueden superar 2000 caracteres"},400)
            with connect() as db:
                db.execute("BEGIN IMMEDIATE")
                person=db.execute("SELECT u.id,r.name role_name FROM users u JOIN roles r ON r.id=u.role_id WHERE u.id=? AND u.active=1 AND r.name IN ('Telefonista','Planificador','Supervisor')",(user_id,)).fetchone()
                if not person:return self.send_json({"detail":"La persona debe ser un usuario activo del equipo operativo"},400)
                conflict=local_schedule_conflict(db,user_id,schedule_date,shift_name,start_time,end_time)
                if conflict:return self.send_json({"detail":schedule_conflict_message(conflict)},409)
                cur=db.execute("INSERT INTO work_schedules(user_id,schedule_date,week_start,role_name,shift_name,start_time,end_time,notes,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(user_id,schedule_date,schedule_week_start(schedule_date),person["role_name"],shift_name,start_time,end_time,notes or None,actor["display_name"],stamp,stamp));item=schedule_record(db,cur.lastrowid);audit(db,"schedule",cur.lastrowid,"CREADO",actor["display_name"],f"{schedule_date} · {person['role_name']}",actor_id=actor["id"],after=item)
            return self.send_json(dict(item),201)
        if path=="/api/settings/users":
            actor=self.require("settings.manage")
            if not actor:return
            email=valid_corporate_email(d.get("email"))
            if not email:return self.send_json({"detail":"El correo debe pertenecer a @portoservicios.com.uy"},400)
            if d.get("password") and len(d["password"])<12:return self.send_json({"detail":"La contraseña alternativa debe tener al menos 12 caracteres"},400)
            username=str(d.get("username") or email.split("@",1)[0]).strip().lower();password=d.get("password") or secrets.token_urlsafe(32)
            try:
                with connect() as db:
                    cur=db.execute("INSERT INTO users(username,email,display_name,password_hash,role_id,active) VALUES(?,?,?,?,?,1)",(username,email,d["display_name"],hash_password(password),int(d["role_id"])));audit(db,"user",cur.lastrowid,"CREADO",actor["display_name"],email,actor_id=actor["id"])
                return self.send_json({"ok":True},201)
            except sqlite3.IntegrityError:return self.send_json({"detail":"Ese usuario o correo corporativo ya existe"},400)
        if path=="/api/settings/roles":
            actor=self.require("settings.manage")
            if not actor:return
            name=str(d.get("name") or "").strip()
            description=str(d.get("description") or "").strip()
            if len(name)<2:return self.send_json({"detail":"Ingrese un nombre para el rol"},400)
            if name.lower()=="administrador":return self.send_json({"detail":"El rol Administrador está reservado"},400)
            try:
                with connect() as db:
                    role_id=db.execute("INSERT INTO roles(name,description) VALUES(?,?)",(name,description or f"Rol {name}")).lastrowid
                    audit(db,"role",role_id,"CREADO",actor["display_name"],name,actor_id=actor["id"])
                return self.send_json({"id":role_id,"name":name,"permissions":[]},201)
            except sqlite3.IntegrityError:return self.send_json({"detail":"Ya existe un rol con ese nombre"},400)
        if path=="/api/quotes/calculate":
            user=self.require("quotes.create")
            if not user:return
            uninsured=bool(d.get("uninsured")); special=bool(d.get("special")); gavilan=bool(d.get("gavilan")); manual=bool(d.get("manual_distance"))
            if gavilan and special:return self.send_json({"detail":"Gavilán no es compatible con Especial"},400)
            if not manual and (not d.get("origin") or not d.get("destination")):return self.send_json({"detail":"Origen y destino son obligatorios para la cotización automática"},400)
            if not manual and d.get("include_mobile") and not d.get("mobile_origin"):return self.send_json({"detail":"Ingrese la ubicación desde donde sale la grúa"},400)
            try:
                route_segments=[]
                manual_toll_count=0
                if manual:
                    trip_km,mobile_km=validate_manual_distances(d.get("manual_trip_km"),d.get("manual_mobile_km") if d.get("include_mobile") else 0,bool(d.get("include_mobile")))
                    manual_toll_count=validate_manual_toll_count(d.get("manual_toll_count"),bool(d.get("include_tolls")))
                else:
                    origin=parse_coordinates(d["origin"]); destination=parse_coordinates(d["destination"]); trip_route=route_data(origin,destination); trip_km=trip_route["km"]; mobile_km=0
                    route_segments.append({"label":"Traslado: origen → destino","color":"#2878b5","coordinates":trip_route["coordinates"]})
                    if d.get("include_mobile"):
                        mobile_origin=parse_coordinates(d["mobile_origin"]); mobile_route=route_data(mobile_origin,origin); mobile_km=mobile_route["km"]
                        route_segments.insert(0,{"label":"Salida de la grúa → origen del cliente","color":"#d8872f","coordinates":mobile_route["coordinates"]})
                with connect() as db:
                    rule=dict(db.execute("SELECT * FROM quote_rules WHERE id=1").fetchone())
                    if gavilan:base=rule["gavilan_uninsured_base" if uninsured else "gavilan_insured_base"]
                    elif special and uninsured:base=rule["special_uninsured_base"]
                    elif special:base=rule["special_insured_base"]
                    elif uninsured:base=rule["uninsured_base"]
                    else:base=rule["insured_base"]
                    rate=rule["special_extra_km_uninsured_rate" if uninsured else "special_extra_km_insured_rate"] if special else rule["extra_km_uninsured_rate" if uninsured else "extra_km_insured_rate"]
                    toll_rate=rule["toll_uninsured" if uninsured else "toll_insured"]
                    if manual:
                        toll_price=round_currency(manual_toll_count*toll_rate)
                        toll_passes=[] if not manual_toll_count else [{"name":f"Peajes manuales ({manual_toll_count})","segment":"Cantidad ingresada manualmente","price":toll_price}]
                        toll_count=manual_toll_count
                    else:
                        tolls=rows(db,"SELECT * FROM toll_catalog WHERE active=1")
                        toll_passes=detect_toll_passes(route_segments,tolls,toll_rate)
                        toll_price=round_currency(sum(item["price"] for item in toll_passes));toll_count=len(toll_passes)
                    total_km=round_distance(trip_km+mobile_km); extra_km=calculate_extra_km(total_km,rule["included_km"]); extra_price=round_currency(extra_km*rate); total_price=round_currency(base+extra_price+toll_price)
                    pricing_snapshot=json.dumps({"schema_version":1,"coverage":"uninsured" if uninsured else "insured","category":"gavilan" if gavilan else "special" if special else "normal","included_km":rule["included_km"],"base_price":base,"extra_rate":rate,"toll_rate":toll_rate,"mode":"manual" if manual else "automatic"},ensure_ascii=False,sort_keys=True)
                    created_at=now()
                    cur=db.execute("INSERT INTO quotes(task_number,origin_input,destination_input,mobile_input,uninsured,special,gavilan,trip_km,mobile_km,total_km,included_km,extra_km,base_price,extra_price,toll_count,toll_details,toll_price,total_price,pricing_snapshot,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(str(d.get("task_number") or "").strip() or None,d.get("origin") or "Cotización manual",d.get("destination") or "Cotización manual",d.get("mobile_origin"),uninsured,special,gavilan,trip_km,mobile_km,total_km,rule["included_km"],extra_km,base,extra_price,toll_count,json.dumps(toll_passes,ensure_ascii=False),toll_price,total_price,pricing_snapshot,user["display_name"],created_at));audit(db,"quote",cur.lastrowid,"COTIZADO",user["display_name"],f"${total_price:.0f}; peajes={toll_count}",actor_id=user["id"])
                customer_type=("No asegurado" if uninsured else "Asegurado")+(" · Gavilán" if gavilan else " · Especial" if special else "")
                return self.send_json({"id":cur.lastrowid,"task_number":str(d.get("task_number") or "").strip(),"created_at":created_at,"origin_input":d.get("origin") or "Cotización manual","destination_input":d.get("destination") or "Cotización manual","mobile_input":d.get("mobile_origin"),"uninsured":uninsured,"special":special,"gavilan":gavilan,"mode":"manual" if manual else "automatic","trip_km":trip_km,"mobile_km":mobile_km,"total_km":total_km,"included_km":rule["included_km"],"extra_km":extra_km,"base_price":base,"extra_rate":rate,"extra_price":extra_price,"toll_count":toll_count,"toll_details":toll_passes,"toll_price":toll_price,"total_price":total_price,"pricing_snapshot":json.loads(pricing_snapshot),"route_segments":route_segments,"customer_type":customer_type},201)
            except ValueError as exc:return self.send_json({"detail":str(exc)},400)
        if path=="/api/settings/standards":
            actor=self.require("settings.manage")
            if not actor:return
            try:item=normalized_business_data(clean_standard,d)
            except ValueError as exc:return self.send_json({"detail":str(exc)},422)
            stamp=now()
            with connect() as db:
                duplicate=db.execute("SELECT id FROM arrival_standards WHERE active=1 AND lower(department)=lower(?) AND lower(service)=lower(?) AND lower(zone)=lower(?)",(item["department"],item["service"],item["zone"])).fetchone()
                if duplicate:return self.send_json({"detail":"Ya existe una referencia activa para ese departamento, prestación y zona"},409)
                cur=db.execute("INSERT INTO arrival_standards(department,zone,service,minutes_min,minutes_max,note,status,source,reviewed_by,effective_from,review_due_at,owner,review_interval_days,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(item["department"],item["zone"],item["service"],item["minutes_min"],item["minutes_max"],item["note"],item["status"],item["source"],actor["display_name"],item["effective_from"].isoformat() if item["effective_from"] else None,item["review_due_at"].isoformat() if item["review_due_at"] else None,item["owner"],item["review_interval_days"],1,stamp,stamp))
                db.execute("UPDATE arrival_standards SET approval_status='APPROVED',submitted_by=?,submitted_at=?,approved_by=?,approved_at=?,approval_note=? WHERE id=?",(actor["display_name"],stamp,actor["display_name"],stamp,"Alta administrativa",cur.lastrowid))
                sync_standard_zones(db,cur.lastrowid,item["department"],item["zone"])
                record_standard_version(db,cur.lastrowid,"CREATED",actor["display_name"],"Alta administrativa")
                audit(db,"arrival_standard",cur.lastrowid,"CREADO",actor["display_name"],f"{item['department']} · {item['service']} · {item['zone']}",actor_id=actor["id"])
                created=dict(db.execute("SELECT * FROM arrival_standards WHERE id=?",(cur.lastrowid,)).fetchone())
            return self.send_json(enrich_standard(created),201)
        create_permissions={"/api/notices":"notices.create","/api/delays":"delays.create","/api/transfers":"transfers.create"}
        if path=="/api/settings/tolls":
            actor=self.require("settings.manage")
            if not actor:return
            try:
                name=str(d.get("name") or "").strip();latitude=float(d.get("latitude"));longitude=float(d.get("longitude"));price=None if d.get("price") in (None,"") else float(d["price"])
                if not all(math.isfinite(value) for value in (latitude,longitude)) or price is not None and not math.isfinite(price):raise ValueError()
                if not 2<=len(name)<=120 or not -35.5<=latitude<=-29 or not -59.5<=longitude<=-52 or price is not None and price<0:raise ValueError()
            except (TypeError,ValueError):return self.send_json({"detail":"Nombre, coordenadas uruguayas o tarifa inválidos"},400)
            with connect() as db:
                stamp=now();cur=db.execute("INSERT INTO toll_catalog(name,latitude,longitude,price,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",(name,latitude,longitude,price,1 if d.get("active",True) else 0,stamp,stamp));audit(db,"toll",cur.lastrowid,"CREADO",actor["display_name"],name,actor_id=actor["id"])
            return self.send_json({"ok":True},201)
        if path in create_permissions:
            actor_user=self.require(create_permissions[path])
            if not actor_user:return
            if path=="/api/notices":d["communicated_by"]=actor_user["display_name"]
            elif path=="/api/delays":d["agent"]=actor_user["display_name"]
            else:d["planner"]=actor_user["display_name"]
            if path=="/api/notices":
                if len(str(d.get("notice_type") or "").strip())<2 or len(str(d.get("detail") or "").strip())<2:
                    return self.send_json({"detail":"Indique el motivo y detalle del aviso"},400)
                if str(d.get("audience") or "TODOS") not in NOTICE_AUDIENCES:
                    return self.send_json({"detail":"Destinatario de aviso inválido"},400)
                if d.get("managed_by") and "notices.assign" not in actor_user["permissions"]:
                    return self.send_json({"detail":"Su rol no tiene permiso para asignar avisos"},403)
                d["status"]="PENDIENTE"
            elif path=="/api/delays":
                try:d=normalized_business_data(clean_delay,d)
                except ValueError as exc:return self.send_json({"detail":str(exc)},422)
                d["agent"]=actor_user["display_name"]
            elif path=="/api/transfers":
                allow_duplicate=bool(d.get("allow_duplicate",False))
                try:d=normalized_business_data(clean_transfer,d)
                except ValueError as exc:return self.send_json({"detail":str(exc)},422)
                d["scheduled_date"]=d["scheduled_date"].isoformat();d["scheduled_time"]=d["scheduled_time"].strftime("%H:%M") if d["scheduled_time"] else None;d["planner"]=actor_user["display_name"];d["status"]="SIN_ASIGNAR";d["allow_duplicate"]=allow_duplicate
            cfg={"/api/notices":("notices",["task_number","phone","notice_type","audience","detail","communicated_by","managed_by","status","comments"],"notice",d.get("communicated_by")),"/api/delays":("delay_zones",["service","department","zone","message","minutes","status","agent"],"delay",d.get("agent")),"/api/transfers":("scheduled_transfers",["task_number","transfer_type","scheduled_date","scheduled_time","origin","destination","provider","responsible","planner","status","comments"],"transfer",d.get("planner"))}
        if path not in cfg: return self.send_json({"detail":"Ruta inexistente"},404)
        table,fields,entity,actor=cfg[path]; defaults={"audience":"TODOS","status":"PENDIENTE","service":"TODAS","message":"Margen de"}; vals=[d.get(f,defaults.get(f)) for f in fields]
        if table=="notices":extra=["created_at","updated_at"];extra_values=[stamp,stamp]
        elif table=="delay_zones":extra=["created_at","last_verified_at","expires_at","last_verified_by"];extra_values=[stamp,stamp,(datetime.now(timezone.utc)+timedelta(minutes=d["review_minutes"])).isoformat(),actor_user["display_name"]]
        elif table=="scheduled_transfers":extra=["created_at","updated_at","updated_by"];extra_values=[stamp,stamp,actor_user["display_name"]]
        else:extra=["created_at"];extra_values=[stamp]
        vals+=extra_values;fields+=extra
        with connect() as db:
            if table=="notices" and d.get("managed_by"):
                assignee=db.execute("""SELECT 1 FROM users u
                    JOIN role_permissions rp ON rp.role_id=u.role_id AND rp.permission='notices.view'
                    WHERE u.active=1 AND u.display_name=? LIMIT 1""",(d["managed_by"],)).fetchone()
                if not assignee:return self.send_json({"detail":"El responsable debe ser un usuario activo con acceso a Avisos"},400)
            if table=="notices" and not d.get("allow_duplicate"):
                db.execute("BEGIN IMMEDIATE")
                duplicates=notice_duplicates(db,d)
                if duplicates:return self.send_json({"detail":{"message":"Ya existe un aviso abierto con esos datos","duplicate":duplicates[0]}},409)
            elif table=="delay_zones":
                db.execute("BEGIN IMMEDIATE")
                duplicate=db.execute("SELECT id FROM delay_zones WHERE status='VIGENTE' AND lower(service)=lower(?) AND lower(department)=lower(?) AND lower(zone)=lower(?)",(d["service"],d["department"],d["zone"])).fetchone()
                if duplicate:return self.send_json({"detail":"Ya existe una demora vigente para esa prestación, departamento y zona"},409)
            elif table=="scheduled_transfers":
                try:ensure_transfer_responsible(db,d.get("responsible"))
                except ValueError as exc:return self.send_json({"detail":str(exc)},400)
                db.execute("BEGIN IMMEDIATE");duplicate=transfer_duplicate(db,d)
                if duplicate and not d.get("allow_duplicate"):return self.send_json({"detail":{"message":"Ya existe un programado con la misma tarea, fecha, hora y recorrido","duplicate":dict(duplicate)}},409)
            cur=db.execute(f"INSERT INTO {table} ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",vals)
            if table=="delay_zones":
                zone_id=ensure_operational_zone(db,d["department"],d["zone"]);db.execute("UPDATE delay_zones SET zone_id=? WHERE id=?",(zone_id,cur.lastrowid));record_delay_event(db,cur.lastrowid,"CREADO",actor,d["message"],extra_values[2])
            elif table=="scheduled_transfers":record_transfer_event(db,cur.lastrowid,"CREADO",actor,new_status="SIN_ASIGNAR",note="Alta confirmada pese a coincidencia" if d.get("allow_duplicate") else None)
            created=dict(db.execute(f"SELECT * FROM {table} WHERE id=?",(cur.lastrowid,)).fetchone())
            audit(db,entity,cur.lastrowid,"CREADO",actor,"Alta confirmada pese a coincidencia abierta" if table=="notices" and d.get("allow_duplicate") else "",actor_id=actor_user["id"],after=created)
            if table=="notices":
                record_notice_event(db,cur.lastrowid,"CREADO",actor,f"{d['notice_type']} · {d.get('audience') or 'TODOS'}",new_value="PENDIENTE",comment=d.get("comments"))
                if d.get("managed_by"):record_notice_event(db,cur.lastrowid,"ASIGNACION",actor,"Responsable definido al crear",new_value=d["managed_by"])
            item=dict(db.execute(f"SELECT * FROM {table} WHERE id=?",(cur.lastrowid,)).fetchone())
        self.send_json(enrich_delay(item) if table=="delay_zones" else item,201)
    def do_PATCH(self):
        if not self.body_size_guard():return
        p=urlparse(self.path).path.strip("/").split("/"); d=self.payload(); stamp=now()
        if not self.csrf_guard():return
        if len(p)==5 and p[:3]==["api","settings","standards"] and p[4]=="decision":
            actor=self.require("standards.approve")
            if not actor:return
            try:item_id=int(p[3])
            except ValueError:return self.send_json({"detail":"Referencia inválida"},400)
            decision=str(d.get("decision") or "");note=str(d.get("note") or "").strip()
            if decision not in ("APPROVED","REJECTED") or not 2<=len(note)<=500:return self.send_json({"detail":"Indique una decisión y su fundamento"},422)
            with connect() as db:
                current=db.execute("SELECT * FROM arrival_standards WHERE id=?",(item_id,)).fetchone()
                if not current:return self.send_json({"detail":"Referencia inexistente"},404)
                if current["approval_status"]!="PENDING":return self.send_json({"detail":"La propuesta ya fue resuelta"},409)
                db.execute("UPDATE arrival_standards SET approval_status=?,approved_by=?,approved_at=?,approval_note=?,active=?,updated_at=? WHERE id=?",(decision,actor["display_name"],stamp,note,1 if decision=="APPROVED" else 0,stamp,item_id));record_standard_version(db,item_id,decision,actor["display_name"],note);audit(db,"arrival_standard",item_id,decision,actor["display_name"],note,actor_id=actor["id"]);item=dict(db.execute("SELECT * FROM arrival_standards WHERE id=?",(item_id,)).fetchone())
            return self.send_json(enrich_standard(item))
        if p==["api","settings","google-access"]:
            user=self.require("settings.manage")
            if not user:return
            client_id=str(d.get("client_id") or "").strip()
            if client_id and not re.fullmatch(r"\d+-[a-z0-9_-]+\.apps\.googleusercontent\.com",client_id,re.I):return self.send_json({"detail":"El ID de cliente OAuth de Google no tiene un formato válido"},400)
            with connect() as db:
                previous=db.execute("SELECT value FROM app_settings WHERE key='google_client_id'").fetchone();db.execute("INSERT OR REPLACE INTO app_settings(key,value) VALUES('google_client_id',?)",(client_id,));audit(db,"settings",1,"GOOGLE_ACTUALIZADO",user["display_name"],"Activado" if client_id else "Desactivado",actor_id=user["id"],before={"enabled":bool(previous and previous[0])},after={"enabled":bool(client_id)})
            return self.send_json({"ok":True,"enabled":bool(client_id)})
        if p==["api","settings","quote-rules"]:
            user=self.require("settings.manage")
            if not user:return
            fields=["insured_base","uninsured_base","special_insured_base","special_uninsured_base","gavilan_base","included_km","extra_km_rate","special_extra_km_rate",*QUOTE_RULE_EXTRA_COLUMNS]
            try:
                with connect() as db:
                    current=dict(db.execute("SELECT * FROM quote_rules WHERE id=1").fetchone())
                    values=[float(d[field] if field in d else current[field]) for field in fields]
                    validate_quote_rule_values(fields, values)
                    db.execute(f"UPDATE quote_rules SET {','.join(field+'=?' for field in fields)},updated_at=? WHERE id=1",values+[now()]);audit(db,"quote_rules",1,"ACTUALIZADO",user["display_name"],actor_id=user["id"],before=current)
            except (KeyError,TypeError,ValueError):return self.send_json({"detail":"Las tarifas y kilómetros deben ser numéricos y estar dentro del rango permitido"},400)
            return self.send_json({"ok":True})
        if len(p)==4 and p[:3]==["api","settings","tolls"]:
            actor=self.require("settings.manage")
            if not actor:return
            try:
                name=str(d.get("name") or "").strip();latitude=float(d.get("latitude"));longitude=float(d.get("longitude"));price=None if d.get("price") in (None,"") else float(d["price"])
                if not all(math.isfinite(value) for value in (latitude,longitude)) or price is not None and not math.isfinite(price):raise ValueError()
                if not 2<=len(name)<=120 or not -35.5<=latitude<=-29 or not -59.5<=longitude<=-52 or price is not None and price<0:raise ValueError()
                item_id=int(p[3])
            except (TypeError,ValueError):return self.send_json({"detail":"Nombre, coordenadas uruguayas o tarifa inválidos"},400)
            with connect() as db:
                current=db.execute("SELECT * FROM toll_catalog WHERE id=?",(item_id,)).fetchone()
                if not current:return self.send_json({"detail":"Peaje inexistente"},404)
                cur=db.execute("UPDATE toll_catalog SET name=?,latitude=?,longitude=?,price=?,active=?,updated_at=? WHERE id=?",(name,latitude,longitude,price,1 if d.get("active",True) else 0,now(),item_id))
                audit(db,"toll",item_id,"ACTUALIZADO",actor["display_name"],name,actor_id=actor["id"],before=current)
            return self.send_json({"ok":True})
        if len(p)==4 and p[:3]==["api","settings","standards"]:
            actor=self.require("settings.manage")
            if not actor:return
            try:item_id=int(p[3]);item=normalized_business_data(clean_standard,d)
            except (TypeError,ValueError) as exc:return self.send_json({"detail":str(exc)},422)
            stamp=now()
            with connect() as db:
                current=db.execute("SELECT * FROM arrival_standards WHERE id=?",(item_id,)).fetchone()
                if not current:return self.send_json({"detail":"Referencia inexistente"},404)
                duplicate=db.execute("SELECT id FROM arrival_standards WHERE active=1 AND id<>? AND lower(department)=lower(?) AND lower(service)=lower(?) AND lower(zone)=lower(?)",(item_id,item["department"],item["service"],item["zone"])).fetchone()
                if duplicate:return self.send_json({"detail":"Ya existe una referencia activa para ese departamento, prestación y zona"},409)
                db.execute("UPDATE arrival_standards SET department=?,zone=?,service=?,minutes_min=?,minutes_max=?,note=?,status=?,source=?,reviewed_by=?,effective_from=?,review_due_at=?,owner=?,review_interval_days=?,active=1,updated_at=? WHERE id=?",(item["department"],item["zone"],item["service"],item["minutes_min"],item["minutes_max"],item["note"],item["status"],item["source"],actor["display_name"],item["effective_from"].isoformat() if item["effective_from"] else None,item["review_due_at"].isoformat() if item["review_due_at"] else None,item["owner"],item["review_interval_days"],stamp,item_id))
                sync_standard_zones(db,item_id,item["department"],item["zone"])
                record_standard_version(db,item_id,"UPDATED",actor["display_name"],"Edición administrativa")
                updated=dict(db.execute("SELECT * FROM arrival_standards WHERE id=?",(item_id,)).fetchone())
                audit(db,"arrival_standard",item_id,"ACTUALIZADO",actor["display_name"],f"{item['department']} · {item['service']} · {item['zone']}",actor_id=actor["id"],before=current,after=updated)
            return self.send_json(enrich_standard(updated))
        if len(p)==3 and p[0]=="api" and p[1]=="schedules":
            actor=self.require("schedules.manage")
            if not actor:return
            item_id=int(p[2])
            try:
                user_id=int(d.get("user_id"));schedule_date=datetime.strptime(str(d.get("schedule_date") or ""),"%Y-%m-%d").date().isoformat();start_time=schedule_time(d.get("start_time"));end_time=schedule_time(d.get("end_time"))
            except (TypeError,ValueError):return self.send_json({"detail":"La persona, fecha u hora del horario no es válida"},400)
            if (start_time is None)!=(end_time is None):return self.send_json({"detail":"Complete ambas horas o deje ambas vacías"},400)
            if start_time is not None and start_time==end_time:return self.send_json({"detail":"La hora de inicio y fin no pueden ser iguales"},400)
            shift_name=str(d.get("shift_name") or "").strip();notes=str(d.get("notes") or "").strip()
            if len(shift_name)<2 or len(shift_name)>80:return self.send_json({"detail":"Indique el turno del horario"},400)
            if len(notes)>2000:return self.send_json({"detail":"Las notas no pueden superar 2000 caracteres"},400)
            with connect() as db:
                db.execute("BEGIN IMMEDIATE")
                person=db.execute("SELECT u.id,r.name role_name FROM users u JOIN roles r ON r.id=u.role_id WHERE u.id=? AND r.name IN ('Telefonista','Planificador','Supervisor')",(user_id,)).fetchone()
                if not person:return self.send_json({"detail":"La persona debe pertenecer al equipo operativo"},400)
                current=db.execute("SELECT * FROM work_schedules WHERE id=?",(item_id,)).fetchone()
                if not current:return self.send_json({"detail":"Horario inexistente"},404)
                conflict=local_schedule_conflict(db,user_id,schedule_date,shift_name,start_time,end_time,item_id)
                if conflict:return self.send_json({"detail":schedule_conflict_message(conflict)},409)
                db.execute("UPDATE work_schedules SET user_id=?,schedule_date=?,week_start=?,role_name=?,shift_name=?,start_time=?,end_time=?,notes=?,updated_at=? WHERE id=?",(user_id,schedule_date,schedule_week_start(schedule_date),person["role_name"],shift_name,start_time,end_time,notes or None,stamp,item_id));item=schedule_record(db,item_id);audit(db,"schedule",item_id,"EDITADO",actor["display_name"],f"{schedule_date} · {person['role_name']}",actor_id=actor["id"],before=current,after=item)
            return self.send_json(dict(item))
        if len(p)==3 and p[0]=="api" and p[1]=="transfers":
            user=self.require("transfers.manage")
            if not user:return
            try:
                item_id=int(p[2]);item=normalized_business_data(clean_transfer,d);allow_duplicate=item.pop("allow_duplicate",False)
            except (TypeError,ValueError) as exc:return self.send_json({"detail":str(exc)},422)
            item["scheduled_date"]=item["scheduled_date"].isoformat();item["scheduled_time"]=item["scheduled_time"].strftime("%H:%M") if item["scheduled_time"] else None
            fields=["task_number","transfer_type","scheduled_date","scheduled_time","origin","destination","provider","responsible","comments"]
            with connect() as db:
                db.execute("BEGIN IMMEDIATE");current=db.execute("SELECT * FROM scheduled_transfers WHERE id=?",(item_id,)).fetchone()
                if not current:return self.send_json({"detail":"Registro inexistente"},404)
                if normalized_status(current["status"]) in {"FINALIZADO","CANCELADO"}:return self.send_json({"detail":"Un traslado finalizado o cancelado ya no puede editarse"},409)
                try:ensure_transfer_responsible(db,item.get("responsible"))
                except ValueError as exc:return self.send_json({"detail":str(exc)},400)
                if normalized_status(current["status"]) in {"ASIGNADO","EN_CURSO"} and (not item.get("provider") or not item.get("responsible")):return self.send_json({"detail":"El traslado asignado requiere prestador y responsable"},400)
                duplicate=transfer_duplicate(db,item,item_id)
                if duplicate and not allow_duplicate:return self.send_json({"detail":{"message":"Ya existe un programado con la misma tarea, fecha, hora y recorrido","duplicate":dict(duplicate)}},409)
                db.execute(f"UPDATE scheduled_transfers SET {','.join(x+'=?' for x in fields)},updated_at=?,updated_by=? WHERE id=?",[item.get(x) for x in fields]+[stamp,user["display_name"],item_id]);record_transfer_event(db,item_id,"EDITADO",user["display_name"],current["status"],current["status"],"Datos operativos actualizados");updated=db.execute("SELECT * FROM scheduled_transfers WHERE id=?",(item_id,)).fetchone();audit(db,"transfer",item_id,"EDITADO",user["display_name"],item.get("task_number",""),actor_id=user["id"],before=current,after=updated)
            return self.send_json(dict(updated))
        if len(p)==3 and p[0]=="api" and p[1]=="users":
            user=self.require("settings.manage")
            if not user:return
            email=valid_corporate_email(d.get("email"))
            if not email:return self.send_json({"detail":"El correo debe pertenecer a @portoservicios.com.uy"},400)
            item_id=int(p[2]); fields=["display_name=?","email=?","role_id=?","active=?"]; values=[d["display_name"],email,int(d["role_id"]),1 if d.get("active",True) else 0]
            if d.get("password"):
                if len(d["password"])<12:return self.send_json({"detail":"La contraseña debe tener al menos 12 caracteres"},400)
                fields.append("password_hash=?"); values.append(hash_password(d["password"]))
            values.append(item_id)
            try:
                with connect() as db:
                    previous=db.execute("SELECT * FROM users WHERE id=?",(item_id,)).fetchone()
                    if not previous:return self.send_json({"detail":"Usuario inexistente"},404)
                    current_role=db.execute("SELECT r.name FROM users u JOIN roles r ON r.id=u.role_id WHERE u.id=?",(item_id,)).fetchone()
                    target_role=db.execute("SELECT name FROM roles WHERE id=?",(int(d["role_id"]),)).fetchone()
                    if not target_role:return self.send_json({"detail":"El rol indicado no existe"},400)
                    if current_role and current_role[0]=="Administrador" and (not d.get("active",True) or target_role[0]!="Administrador"):
                        other_admins=db.execute("SELECT count(*) FROM users u JOIN roles r ON r.id=u.role_id WHERE u.active=1 AND r.name='Administrador' AND u.id<>?",(item_id,)).fetchone()[0]
                        if other_admins<1:return self.send_json({"detail":"No se puede dejar el sistema sin un Administrador activo"},400)
                    if str(previous["email"] or "").lower()!=email:fields.append("google_sub=NULL")
                    db.execute(f"UPDATE users SET {','.join(fields)} WHERE id=?",values);audit(db,"user",item_id,"ACTUALIZADO",user["display_name"],email,actor_id=user["id"],before=previous)
                if d.get("password") or not d.get("active",True):
                    for session_token,session in list(SESSIONS.items()):
                        if session["user_id"]==item_id:SESSIONS.pop(session_token,None)
            except sqlite3.IntegrityError:return self.send_json({"detail":"Ese correo corporativo ya está asignado"},400)
            return self.send_json({"ok":True})
        if len(p)!=4 or p[0]!="api": return self.send_json({"detail":"Ruta inexistente"},404)
        kind,item_id,action=p[1],int(p[2]),p[3]; actor=d.get("actor","Operador web")
        if kind=="roles" and action=="permissions":
            user=self.require("settings.manage")
            if not user:return
            valid=[x for x in d.get("permissions",[]) if x in PERMISSIONS]
            with connect() as db:
                role=db.execute("SELECT name FROM roles WHERE id=?",(item_id,)).fetchone()
                if not role:return self.send_json({"detail":"Rol inexistente"},404)
                if role["name"]=="Administrador":return self.send_json({"detail":"Los permisos del Administrador son obligatorios y no se pueden modificar"},400)
                before=_audit_snapshot(db,"role",item_id);db.execute("DELETE FROM role_permissions WHERE role_id=?",(item_id,));db.executemany("INSERT INTO role_permissions(role_id,permission) VALUES(?,?)",[(item_id,x) for x in valid]);audit(db,"role",item_id,"PERMISOS_ACTUALIZADOS",user["display_name"],", ".join(valid),actor_id=user["id"],before=before)
            return self.send_json({"ok":True})
        if kind=="notices" and action=="status":
            user=self.current_user()
            if not user:
                self.send_json({"detail":"Debe iniciar sesión"},401);return
            with connect() as db:
                current=db.execute("SELECT * FROM notices WHERE id=?",(item_id,)).fetchone()
                if not current:
                    self.send_json({"detail":"Aviso inexistente"},404);return
                try:
                    required=notice_update_permissions(dict(current),d)
                except ValueError as exc:
                    self.send_json({"detail":str(exc)},400);return
                missing=sorted(required-set(user["permissions"]))
                if missing:
                    self.send_json({"detail":"Su rol no tiene permiso para realizar esta acción"},403);return
                if "notices.assign" in required and d.get("managed_by"):
                    assignee=db.execute("""SELECT 1 FROM users u
                        JOIN role_permissions rp ON rp.role_id=u.role_id AND rp.permission='notices.view'
                        WHERE u.active=1 AND u.display_name=? LIMIT 1""",(d["managed_by"],)).fetchone()
                    if not assignee:
                        self.send_json({"detail":"El responsable debe ser un usuario activo con acceso a Avisos"},400);return
                next_status=d.get("status",current["status"])
                if next_status not in NOTICE_STATUSES:
                    self.send_json({"detail":"Estado de aviso inválido"},400);return
                if next_status in NOTICE_CLOSED_STATUSES and next_status!=current["status"] and not str(d.get("comments") or "").strip():
                    self.send_json({"detail":"Indique el resultado o motivo del cierre"},400);return
                managed_by=d["managed_by"] if "managed_by" in d else current["managed_by"]
                comments=d["comments"] if "comments" in d else current["comments"]
                db.execute("UPDATE notices SET status=?,managed_by=?,comments=?,updated_at=? WHERE id=?",(next_status,managed_by,comments,now(),item_id))
                changes=[]
                if next_status!=current["status"]:
                    changes.append(f"estado: {current['status']} → {next_status}");record_notice_event(db,item_id,"ESTADO",user["display_name"],"Cambio de estado",current["status"],next_status)
                if managed_by!=current["managed_by"]:
                    changes.append(f"responsable: {managed_by or 'sin asignar'}");record_notice_event(db,item_id,"ASIGNACION",user["display_name"],"Cambio de responsable",current["managed_by"],managed_by)
                if comments!=current["comments"]:
                    changes.append("comentario actualizado");record_notice_event(db,item_id,"COMENTARIO",user["display_name"],"Comentario eliminado" if comments in (None,"") else "Seguimiento agregado",comment=comments)
                item=dict(db.execute("SELECT * FROM notices WHERE id=?",(item_id,)).fetchone())
                audit(db,"notice",item_id,"AVISO_ACTUALIZADO",user["display_name"]," · ".join(changes),actor_id=user["id"],before=current,after=item)
            self.send_json(item,200);return
        permission="delays.normalize" if kind=="delays" else "transfers.manage"
        user=self.require(permission)
        if not user:return
        actor=user["display_name"]
        with connect() as db:
            audit_action="CAMBIO_ESTADO";audit_detail=d.get("status","NORMALIZADO")
            if kind=="notices" and action=="status": db.execute("UPDATE notices SET status=?,managed_by=COALESCE(?,managed_by),comments=COALESCE(?,comments),updated_at=? WHERE id=?",(d["status"],d.get("managed_by"),d.get("comments"),now(),item_id)); table="notices"; entity="notice"
            elif kind=="transfers" and action=="status":
                current=db.execute("SELECT * FROM scheduled_transfers WHERE id=?",(item_id,)).fetchone()
                if not current:return self.send_json({"detail":"Programado inexistente"},404)
                try:change=validate_transition(dict(current),d);ensure_transfer_responsible(db,change["responsible"])
                except ValueError as exc:return self.send_json({"detail":str(exc)},409 if "No se puede" in str(exc) or "ya se encuentra" in str(exc) else 400)
                changed_at=now();target=change["status"];assigned_at=current["assigned_at"];started_at=current["started_at"];completed_at=current["completed_at"];cancelled_at=current["cancelled_at"];completion_note=current["completion_note"];cancellation_reason=current["cancellation_reason"];responsible=change["responsible"]
                if target=="SIN_ASIGNAR":assigned_at=None;responsible=None
                elif target=="ASIGNADO":assigned_at=assigned_at or changed_at
                elif target=="EN_CURSO":started_at=started_at or changed_at
                elif target=="FINALIZADO":completed_at=changed_at;completion_note=change["note"]
                elif target=="CANCELADO":cancelled_at=changed_at;cancellation_reason=change["note"]
                db.execute("""UPDATE scheduled_transfers SET status=?,provider=?,responsible=?,assigned_at=?,started_at=?,completed_at=?,cancelled_at=?,completion_note=?,cancellation_reason=?,updated_at=?,updated_by=? WHERE id=?""",(target,change["provider"],responsible,assigned_at,started_at,completed_at,cancelled_at,completion_note,cancellation_reason,changed_at,actor,item_id));record_transfer_event(db,item_id,"ESTADO",actor,change["previous_status"],target,change["note"]);table="scheduled_transfers";entity="transfer";audit_detail=f"{change['previous_status']} → {target}"
            elif kind=="delays" and action=="verify":
                note=str(d.get("verification_note") or "").strip()
                try:review_minutes=int(d.get("review_minutes",120))
                except (TypeError,ValueError):return self.send_json({"detail":"El plazo de revisión no es válido"},422)
                if len(note)<2 or len(note)>500 or not 15<=review_minutes<=1440:return self.send_json({"detail":"Indicá la verificación y un plazo entre 15 minutos y 24 horas"},422)
                current=db.execute("SELECT * FROM delay_zones WHERE id=?",(item_id,)).fetchone()
                if not current:return self.send_json({"detail":"Demora inexistente"},404)
                if current["status"]!="VIGENTE":return self.send_json({"detail":"La demora ya no está vigente"},409)
                verified=now();expires=(datetime.now(timezone.utc)+timedelta(minutes=review_minutes)).isoformat();db.execute("UPDATE delay_zones SET last_verified_at=?,expires_at=?,last_verified_by=? WHERE id=?",(verified,expires,actor,item_id));record_delay_event(db,item_id,"VERIFICADO",actor,note,expires);table="delay_zones";entity="delay";audit_action="VERIFICADO";audit_detail=note
            elif kind=="delays" and action=="normalize":
                note=str(d.get("resolution_note") or "").strip()
                if len(note)<2 or len(note)>500:return self.send_json({"detail":"Indique cómo se confirmó la normalización"},422)
                current=db.execute("SELECT * FROM delay_zones WHERE id=?",(item_id,)).fetchone()
                if not current:return self.send_json({"detail":"Demora inexistente"},404)
                if current["status"]!="VIGENTE":return self.send_json({"detail":"La demora ya no está vigente"},409)
                closed=now();db.execute("UPDATE delay_zones SET status='NORMALIZADO',normalized_at=?,normalized_by=?,resolution_note=?,last_verified_at=?,last_verified_by=? WHERE id=?",(closed,actor,note,closed,actor,item_id));record_delay_event(db,item_id,"NORMALIZADO",actor,note);table="delay_zones";entity="delay"
            else: return self.send_json({"detail":"Ruta inexistente"},404)
            item=db.execute(f"SELECT * FROM {table} WHERE id=?",(item_id,)).fetchone();audit(db,entity,item_id,audit_action,actor,audit_detail,actor_id=user["id"],before=current,after=item)
        result=dict(item) if item else {"detail":"Registro inexistente"}
        self.send_json(enrich_delay(result) if item and kind=="delays" else result,200 if item else 404)

    def do_DELETE(self):
        p=urlparse(self.path).path.strip("/").split("/")
        if not self.csrf_guard():return
        if len(p)==3 and p[0]=="api" and p[1]=="schedules":
            user=self.require("schedules.manage")
            if not user:return
            item_id=int(p[2])
            with connect() as db:
                item=db.execute("SELECT * FROM work_schedules WHERE id=?",(item_id,)).fetchone()
                if not item:return self.send_json({"detail":"Horario inexistente"},404)
                audit(db,"schedule",item_id,"ELIMINADO",user["display_name"],f"{item['schedule_date']} · {item['shift_name']}",actor_id=user["id"],before=item);db.execute("DELETE FROM work_schedules WHERE id=?",(item_id,))
            return self.send_json({"ok":True})
        if len(p)==4 and p[:3]==["api","settings","tolls"]:
            actor=self.require("settings.manage")
            if not actor:return
            try:item_id=int(p[3])
            except ValueError:return self.send_json({"detail":"Peaje inválido"},400)
            with connect() as db:
                item=db.execute("SELECT * FROM toll_catalog WHERE id=?",(item_id,)).fetchone()
                if not item:return self.send_json({"detail":"Peaje inexistente"},404)
                db.execute("DELETE FROM toll_catalog WHERE id=?",(item_id,));audit(db,"toll",item_id,"ELIMINADO",actor["display_name"],item["name"],actor_id=actor["id"],before=item)
            return self.send_json({"ok":True})
        if len(p)==4 and p[:3]==["api","settings","standards"]:
            actor=self.require("settings.manage")
            if not actor:return
            try:item_id=int(p[3])
            except ValueError:return self.send_json({"detail":"Referencia inválida"},400)
            with connect() as db:
                item=db.execute("SELECT * FROM arrival_standards WHERE id=?",(item_id,)).fetchone()
                if not item:return self.send_json({"detail":"Referencia inexistente"},404)
                db.execute("UPDATE arrival_standards SET active=0,updated_at=? WHERE id=?",(now(),item_id));record_standard_version(db,item_id,"DEACTIVATED",actor["display_name"],"Referencia desactivada");audit(db,"arrival_standard",item_id,"DESACTIVADO",actor["display_name"],f"{item['department']} · {item['service']} · {item['zone']}",actor_id=actor["id"],before=item)
            return self.send_json({"ok":True})
        if len(p)!=3 or p[0]!="api" or p[1]!="transfers":return self.send_json({"detail":"Ruta inexistente"},404)
        if not self.require("transfers.manage"):return
        self.send_json({"detail":"Los programados se conservan. Utilice el estado Cancelado e indique el motivo"},405)

if __name__=="__main__":
    try:
        backup_path=create_daily_backup()
        if backup_path:print(f"Copia de seguridad: {backup_path}")
    except Exception as exc:
        print(f"ADVERTENCIA: no se pudo crear la copia de seguridad: {exc}")
    initialize(); server=ThreadingHTTPServer((HOST,PORT),Handler); print("Centro Operativo esta funcionando."); print(f"Direccion: http://{HOST}:{PORT}"); print("No cierre esta ventana mientras use la herramienta.")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
