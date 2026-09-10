"""Modo local: servidor HTTP con SQLite y autenticación corporativa."""
import base64, hmac, json, math, re, secrets, sqlite3, time
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.request import Request, urlopen
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
try:
    from . import wfm
    from .tolls import detect_toll_passes
    from .reporting import notice_csv_bytes, report_csv_bytes
    from .scheduling import find_schedule_conflict, schedule_conflict_message, schedule_date_value, schedule_time_text
    from .security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME, csrf_token_for_session, hash_password, password_needs_rehash, verify_password
except ImportError:
    import wfm
    from tolls import detect_toll_passes
    from reporting import notice_csv_bytes, report_csv_bytes
    from scheduling import find_schedule_conflict, schedule_conflict_message, schedule_date_value, schedule_time_text
    from security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME, csrf_token_for_session, hash_password, password_needs_rehash, verify_password

ROOT=Path(__file__).resolve().parent; STATIC=ROOT/"static"; DB_PATH=ROOT.parent/"centro_operativo.db"; BACKUP_DIR=ROOT.parent/"backups"; HOST="127.0.0.1"; PORT=8000
APP_VERSION="1.21.0"
VERSION_NOTES=[
    "Cotizador con catálogo local de peajes: detección por recorrido, doble tramo y desglose histórico.",
    "Planificación más fluida: publicación semanal atómica, arrastre con punto de agarre estable y mermas móviles dentro del turno.",
    "Columna de agentes despejada y edición concentrada en un menú contextual sobre la barra del turno.",
    "Horarios es una vista estrictamente de consulta, con búsqueda en vivo y mediante Enter.",
    "Horarios reales de Telefonistas para la semana ISO 37: variaciones diarias, descansos opcionales, novedades puntuales y horas extra.",
    "WFM avanzado: turnos nocturnos y entrecortados, mermas por actividad y portal de solicitudes con aprobación.",
    "WFM: reglas globales de jornada y descanso, demanda legacy completada sin reescritura silenciosa y auditoría de guardados/publicaciones.",
    "Libro de Trabajo: identidad visual, icono de escritorio y alta aditiva del equipo de Telefonistas.",
    "Planificación WFM: cobertura semanal por día, ventanas por equipo, borradores y publicación individual.",
    "Horizonte WFM extendido al día siguiente, con identificación visual +1 para cruces de medianoche.",
    "Horarios con prevención de duplicados y turnos superpuestos, incluso durante la madrugada.",
    "Copia segura de la semana anterior y carga rápida desde cada celda del calendario.",
    "Agenda histórica de horarios por semana, persona y rol, con descarga de reportes.",
    "Configuración de horarios para Telefonistas, Planificadores y Supervisores desde un modal.",
    "Los campos de cerrajería desp. 22 hs con costo cero ya no se muestran en las tarifas.",
    "Exportación administrativa del Registro de auditoría como CSV.",
    "Tarifas del cotizador separadas en costos para asegurados y no asegurados.",
    "Lanzador de escritorio Windows para iniciar Docker y abrir la aplicación.",
    "Endurecimiento de sesiones, CSRF, límites de autenticación y validación de entradas.",
    "Reportes históricos de Avisos con filtros y descarga compatible con Excel.",
    "Filtros de Demoras por período, estado, departamento, prestación y texto libre.",
    "Respaldos PostgreSQL horarios, verificados y sin eliminación automática.",
    "Backend Docker/PostgreSQL llevado a paridad con el modo local.",
    "Migración conservadora desde SQLite hacia un PostgreSQL vacío.",
    "Copia de seguridad diaria y consistente de la base SQLite al iniciar.",
    "Mapa operativo basado únicamente en demoras vigentes y concentración geográfica.",
    "Registro de auditoría reservado al Administrador y herramientas de supervisión agrupadas.",
    "Cotizaciones con tarea, recuperación, borrador automático y resumen copiable.",
    "Mapa interactivo de tiempos de arribo y administración de roles personalizados.",
]
SCHEMA="""
CREATE TABLE IF NOT EXISTS notices(id INTEGER PRIMARY KEY AUTOINCREMENT,task_number TEXT,phone TEXT,notice_type TEXT NOT NULL,audience TEXT NOT NULL DEFAULT 'TODOS',detail TEXT NOT NULL,communicated_by TEXT NOT NULL,managed_by TEXT,status TEXT NOT NULL DEFAULT 'PENDIENTE',comments TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS delay_zones(id INTEGER PRIMARY KEY AUTOINCREMENT,service TEXT NOT NULL,department TEXT NOT NULL,zone TEXT NOT NULL,message TEXT NOT NULL,minutes INTEGER,status TEXT NOT NULL,agent TEXT NOT NULL,created_at TEXT NOT NULL,normalized_at TEXT);
CREATE TABLE IF NOT EXISTS scheduled_transfers(id INTEGER PRIMARY KEY AUTOINCREMENT,task_number TEXT NOT NULL,transfer_type TEXT NOT NULL,scheduled_date TEXT NOT NULL,scheduled_time TEXT,origin TEXT NOT NULL,destination TEXT NOT NULL,provider TEXT,planner TEXT NOT NULL,status TEXT NOT NULL,comments TEXT,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS work_schedules(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,schedule_date TEXT NOT NULL,week_start TEXT NOT NULL,role_name TEXT NOT NULL,shift_name TEXT NOT NULL,start_time TEXT,end_time TEXT,notes TEXT,created_by TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id));
CREATE INDEX IF NOT EXISTS work_schedules_date_idx ON work_schedules(schedule_date,week_start);
CREATE INDEX IF NOT EXISTS work_schedules_user_idx ON work_schedules(user_id,schedule_date);
CREATE TABLE IF NOT EXISTS arrival_standards(id INTEGER PRIMARY KEY AUTOINCREMENT,department TEXT NOT NULL,zone TEXT NOT NULL,service TEXT NOT NULL,minutes_min INTEGER,minutes_max INTEGER,note TEXT);
CREATE TABLE IF NOT EXISTS audit_events(id INTEGER PRIMARY KEY AUTOINCREMENT,entity TEXT NOT NULL,entity_id INTEGER NOT NULL,action TEXT NOT NULL,actor TEXT NOT NULL,detail TEXT,created_at TEXT NOT NULL);
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
CREATE TABLE IF NOT EXISTS quotes(id INTEGER PRIMARY KEY AUTOINCREMENT,task_number TEXT,origin_input TEXT NOT NULL,destination_input TEXT NOT NULL,mobile_input TEXT,uninsured INTEGER NOT NULL,special INTEGER NOT NULL,gavilan INTEGER NOT NULL,trip_km REAL NOT NULL,mobile_km REAL NOT NULL,total_km REAL NOT NULL,included_km REAL NOT NULL,extra_km REAL NOT NULL,base_price REAL NOT NULL,extra_price REAL NOT NULL,toll_count INTEGER NOT NULL DEFAULT 0,toll_details TEXT NOT NULL DEFAULT '[]',toll_price REAL NOT NULL DEFAULT 0,total_price REAL NOT NULL,created_by TEXT NOT NULL,created_at TEXT NOT NULL);
"""
QUOTE_RULE_EXTRA_COLUMNS={
    "gavilan_insured_base":2140,"gavilan_uninsured_base":2140,
    "transfer_insured_base":2550,"transfer_uninsured_base":2850,
    "transfer_special_insured_base":4050,"transfer_special_uninsured_base":4470,
    "locksmith_mvd_insured_base":1785,"locksmith_mvd_uninsured_base":1930,
    "locksmith_coast_insured_base":2720,"locksmith_coast_uninsured_base":2950,
    "locksmith_mvd_after22_insured_base":0,"locksmith_mvd_after22_uninsured_base":0,
    "locksmith_coast_after22_insured_base":0,"locksmith_coast_after22_uninsured_base":0,
    "extra_km_insured_rate":120,"extra_km_uninsured_rate":90,
    "special_extra_km_insured_rate":120,"special_extra_km_uninsured_rate":110,
    "toll_insured":416,"toll_uninsured":416,
    "waiting_hour_insured":820,"waiting_hour_uninsured":820,
    "rescue_hour_insured":900,"rescue_hour_uninsured":900,
}
QUOTE_RULE_LEGACY_COPIES={
    "gavilan_insured_base":"gavilan_base","gavilan_uninsured_base":"gavilan_base",
    "extra_km_insured_rate":"extra_km_rate","special_extra_km_insured_rate":"special_extra_km_rate",
}
PERMISSIONS={"dashboard.view":"Ver resumen","delays.view":"Ver demoras","delays.create":"Registrar demoras","delays.normalize":"Normalizar demoras","notices.view":"Ver avisos","notices.create":"Registrar avisos","notices.manage":"Asignar, comentar y resolver avisos","reports.export":"Filtrar y descargar reportes","transfers.view":"Ver programados","transfers.create":"Registrar programados","transfers.manage":"Editar y cambiar el estado de programados","schedules.view":"Ver horarios del equipo","schedules.manage":"Configurar y editar horarios","quotes.view":"Ver cotizador e historial","quotes.create":"Generar cotizaciones","standards.view":"Ver tiempos de arribo","audit.view":"Ver registro de auditoría","settings.manage":"Administrar usuarios, roles y permisos"}
DEFAULT_ROLES={"Administrador":set(PERMISSIONS),"Supervisor":set(PERMISSIONS)-{"settings.manage","audit.view"},"Planificador":set(PERMISSIONS)-{"settings.manage","audit.view","reports.export"},"Telefonista":{"dashboard.view","delays.view","notices.view","notices.create","notices.manage","transfers.view","quotes.view","quotes.create","standards.view","schedules.view"}}
SCHEDULE_ROLES=("Telefonista","Planificador","Supervisor")
SESSIONS={}
LOGIN_ATTEMPTS={}
LOCAL_SESSION_SECONDS=43200
LOCAL_SESSION_IDLE_SECONDS=1800
MAX_BODY_BYTES=1024*1024
LOCAL_APP_SECRET=secrets.token_urlsafe(32)
GOOGLE_NONCES={}
GOOGLE_JWKS={"expires":0,"keys":{}}
ALLOWED_GOOGLE_DOMAIN="portoservicios.com.uy"
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
        db.executescript(wfm.SCHEMA)
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
        for column,definition in {"toll_count":"INTEGER NOT NULL DEFAULT 0","toll_details":"TEXT NOT NULL DEFAULT '[]'","toll_price":"REAL NOT NULL DEFAULT 0"}.items():
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
        if not db.execute("SELECT 1 FROM schema_migrations WHERE key='quotes_permissions_v1'").fetchone():
            for role_name in ("Administrador","Supervisor","Planificador","Telefonista"):
                role_id=db.execute("SELECT id FROM roles WHERE name=?",(role_name,)).fetchone()[0]
                db.executemany("INSERT OR IGNORE INTO role_permissions(role_id,permission) VALUES(?,?)",[(role_id,"quotes.view"),(role_id,"quotes.create")])
            db.execute("INSERT INTO schema_migrations(key,applied_at) VALUES('quotes_permissions_v1',?)",(now(),))
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
            db.executemany("INSERT INTO arrival_standards(department,zone,service,minutes_min,minutes_max,note) VALUES(?,?,?,?,?,?)",[("MONTEVIDEO","Centro, Parque Rodó, Pocitos, Punta Carretas, Tres Cruces, Buceo","ML",None,30,None),("MONTEVIDEO","Nuevo París, Cerro, Colón, Casavalle, Peñarol, La Teja, Manga","ML",None,45,None),("MONTEVIDEO","Ciudad","GRÚA",None,45,None),("CANELONES","Ciudad de la Costa","ML",None,45,None),("ARTIGAS","Artigas","ML",None,45,None),("ARTIGAS","Artigas","GRÚA",None,60,None),("MALDONADO","Maldonado Ciudad, Piriápolis","ML",30,45,None),("INTERIOR","Zona no listada","ML",None,None,"A confirmar")])
def rows(db,sql,p=()): return [dict(r) for r in db.execute(sql,p).fetchall()]
def audit(db,e,i,a,actor,d=""): db.execute("INSERT INTO audit_events(entity,entity_id,action,actor,detail,created_at) VALUES(?,?,?,?,?,?)",(e,i,a,actor,d,now()))

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

def valid_corporate_email(value):
    email=str(value or "").strip().lower()
    return email if re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@portoservicios\.com\.uy",email,re.I) else None

def b64url_decode(value):return base64.urlsafe_b64decode(value+"="*(-len(value)%4))

def google_public_keys():
    if GOOGLE_JWKS["expires"]>time.time() and GOOGLE_JWKS["keys"]:return GOOGLE_JWKS["keys"]
    with urlopen(Request("https://www.googleapis.com/oauth2/v3/certs",headers={"User-Agent":"CentroOperativo/1.0"}),timeout=10) as response:
        data=json.loads(response.read()); cache=response.headers.get("Cache-Control","")
    max_age_match=re.search(r"max-age=(\d+)",cache); max_age=int(max_age_match.group(1)) if max_age_match else 3600
    GOOGLE_JWKS["keys"]={item["kid"]:item for item in data.get("keys",[])}; GOOGLE_JWKS["expires"]=time.time()+max_age
    return GOOGLE_JWKS["keys"]

def verify_google_id_token(token,client_id,expected_nonce):
    try:
        encoded_header,encoded_payload,encoded_signature=token.split(".")
        header=json.loads(b64url_decode(encoded_header)); payload_data=json.loads(b64url_decode(encoded_payload)); jwk=google_public_keys().get(header.get("kid"))
        if header.get("alg")!="RS256" or not jwk:raise ValueError()
        public_key=rsa.RSAPublicNumbers(int.from_bytes(b64url_decode(jwk["e"]),"big"),int.from_bytes(b64url_decode(jwk["n"]),"big")).public_key()
        public_key.verify(b64url_decode(encoded_signature),f"{encoded_header}.{encoded_payload}".encode(),padding.PKCS1v15(),hashes.SHA256())
        if payload_data.get("aud")!=client_id or payload_data.get("iss") not in ("accounts.google.com","https://accounts.google.com"):raise ValueError()
        if int(payload_data.get("exp",0))<=int(time.time()) or payload_data.get("nonce")!=expected_nonce:raise ValueError()
        if payload_data.get("email_verified") not in (True,"true") or str(payload_data.get("hd","")).lower()!=ALLOWED_GOOGLE_DOMAIN:raise ValueError()
        email=valid_corporate_email(payload_data.get("email"))
        if not email:raise ValueError()
        payload_data["email"]=email
        return payload_data
    except Exception as exc:raise ValueError("No se pudo verificar la identidad de Google") from exc

def parse_coordinates(value):
    text=unquote(str(value or "").strip())
    patterns=[r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*[,; ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$",r"!3d(-?\d{1,2}(?:\.\d+)?).*?!4d(-?\d{1,3}(?:\.\d+)?)",r"(?:query|q|destination|origin)=(-?\d{1,2}(?:\.\d+)?),(-?\d{1,3}(?:\.\d+)?)",r"@(-?\d{1,2}(?:\.\d+)?),(-?\d{1,3}(?:\.\d+)?)"]
    for pattern in patterns:
        match=re.search(pattern,text,re.I)
        if match:
            lat,lon=float(match.group(1)),float(match.group(2))
            if -36.5<=lat<=-29 and -59.5<=lon<=-52:return lat,lon
    dms=re.search(r"(\d{1,2})[°º]\s*(\d{1,2})['′]\s*(\d{1,2}(?:\.\d+)?)[\"″]?\s*([NS]).*?(\d{1,3})[°º]\s*(\d{1,2})['′]\s*(\d{1,2}(?:\.\d+)?)[\"″]?\s*([EW])",text,re.I)
    if dms:
        lat=float(dms.group(1))+float(dms.group(2))/60+float(dms.group(3))/3600
        lon=float(dms.group(5))+float(dms.group(6))/60+float(dms.group(7))/3600
        if dms.group(4).upper()=="S":lat=-lat
        if dms.group(8).upper()=="W":lon=-lon
        if -36.5<=lat<=-29 and -59.5<=lon<=-52:return lat,lon
    if text.startswith(("http://","https://")):
        host=(urlparse(text).hostname or "").lower()
        if host.endswith(("google.com","google.com.uy","goo.gl","maps.app.goo.gl")):
            try:
                response=urlopen(Request(text,headers={"User-Agent":"Mozilla/5.0"}),timeout=8)
                final=response.geturl(); response.close()
                if final!=text:return parse_coordinates(final)
            except Exception:pass
    raise ValueError("No se pudieron obtener coordenadas. Use un enlace de Google Maps que incluya la ubicación o escriba latitud,longitud.")

def route_data(start,end):
    lat1,lon1=start; lat2,lon2=end
    url=f"https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson&alternatives=false&steps=false"
    try:
        with urlopen(Request(url,headers={"User-Agent":"CentroOperativo/1.0"}),timeout=15) as response:data=json.loads(response.read())
        if data.get("code")!="Ok" or not data.get("routes"):raise ValueError()
        route=data["routes"][0]
        return {"km":round(route["distance"]/1000,2),"coordinates":route.get("geometry",{}).get("coordinates",[])}
    except Exception as exc:raise ValueError("No se pudo calcular la ruta automáticamente. Verifique las ubicaciones o use la distancia manual.") from exc

def route_km(start,end):return route_data(start,end)["km"]

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
                        event={'APROBAR':'SOLICITUD_WFM_APROBADA','RECHAZAR':'SOLICITUD_WFM_RECHAZADA'}.get(decision,'SOLICITUD_WFM_CREADA')
                        detail=f"{result.get('request_id','')} · {result.get('requested_date','')} · {result.get('request_type','')}"
                    elif action_name == 'publish-week':
                        event='SEMANA_WFM_PUBLICADA';detail=f"{result.get('week','')} · {result.get('team','')} · {result.get('published_count',0)} días"
                    else:
                        event='WFM_ACTUALIZADO';detail=params.get('team','')
                    audit(db,'wfm',0,event,actor['display_name'],detail)
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
            return self.send_json({"version":APP_VERSION,"released":"2026-09-09","notes":VERSION_NOTES})
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
            query="SELECT s.id,s.user_id,s.schedule_date,s.week_start,COALESCE(NULLIF(s.role_name,''),r.name,'') role_name,s.shift_name,s.start_time,s.end_time,s.notes,s.created_by,s.created_at,s.updated_at,COALESCE(u.display_name,'Usuario no disponible') display_name FROM work_schedules s LEFT JOIN users u ON u.id=s.user_id LEFT JOIN roles r ON r.id=u.role_id WHERE 1=1";values=[]
            if week:query+=" AND s.week_start=?";values.append(week)
            else:
                if date_from:query+=" AND s.schedule_date>=?";values.append(date_from)
                if date_to:query+=" AND s.schedule_date<=?";values.append(date_to)
            if not wfm.manager(actor):employee_id=actor['id']
            if employee_id is not None:query+=" AND s.user_id=?";values.append(employee_id)
            if value("role"):query+=" AND COALESCE(NULLIF(s.role_name,''),r.name)=?";values.append(value("role"))
            if value("q"):
                query+=" AND lower(COALESCE(u.display_name,'')||' '||COALESCE(s.role_name,'')||' '||COALESCE(s.shift_name,'')||' '||COALESCE(s.notes,'')) LIKE lower(?)";values.append(f"%{value('q')}%")
            query+=" ORDER BY s.schedule_date,s.start_time,display_name LIMIT 20000"
            with connect() as db:result=rows(db,query,values)
            if path.startswith("/api/reports/"):return self.send_bytes(report_csv_bytes("schedules",result),"text/csv; charset=utf-8","reporte_horarios.csv")
            return self.send_json(result)
        if path in ("/api/notices","/api/reports/notices.csv"):
            permission="reports.export" if path.startswith("/api/reports/") else "notices.view"
            if not self.require(permission):return
            query="SELECT * FROM notices WHERE 1=1";values=[]
            def value(name):return str(params.get(name,[""])[0]).strip()
            if value("date_from"):query+=" AND date(created_at)>=date(?)";values.append(value("date_from"))
            if value("date_to"):query+=" AND date(created_at)<=date(?)";values.append(value("date_to"))
            if value("status"):query+=" AND status=?";values.append(value("status"))
            if value("task"):query+=" AND lower(COALESCE(task_number,'')) LIKE lower(?)";values.append(f"%{value('task')}%")
            if value("contact"):query+=" AND lower(COALESCE(phone,'')) LIKE lower(?)";values.append(f"%{value('contact')}%")
            if value("q"):query+=" AND lower(COALESCE(task_number,'')||' '||COALESCE(phone,'')||' '||COALESCE(notice_type,'')||' '||COALESCE(detail,'')||' '||COALESCE(managed_by,'')||' '||COALESCE(communicated_by,'')||' '||COALESCE(comments,'')) LIKE lower(?)";values.append(f"%{value('q')}%")
            query+=" ORDER BY created_at DESC"
            if path=="/api/notices":query+=" LIMIT 20000"
            with connect() as db:result=rows(db,query,values)
            if path.startswith("/api/reports/"):return self.send_bytes(notice_csv_bytes(result),"text/csv; charset=utf-8","reporte_avisos.csv")
            return self.send_json(result)
        report_paths={"/api/reports/delays.csv":("delays","delay_zones","created_at",["service","department","zone","message","agent"],"demoras"),"/api/reports/transfers.csv":("transfers","scheduled_transfers","scheduled_date",["task_number","transfer_type","origin","destination","provider","planner","comments"],"programados"),"/api/reports/quotes.csv":("quotes","quotes","created_at",["task_number","origin_input","destination_input","mobile_input","created_by"],"cotizaciones"),"/api/reports/audit.csv":("audit","audit_events","created_at",["entity","action","actor","detail"],"auditoria")}
        if path in report_paths:
            if report_paths[path][0]=="audit" and not self.require("audit.view"):return
            if not self.require("reports.export"):return
            kind,table,date_field,search_fields,filename=report_paths[path];query=f"SELECT * FROM {table} WHERE 1=1";values=[]
            def value(name):return str(params.get(name,[""])[0]).strip()
            if value("date_from"):query+=f" AND date({date_field})>=date(?)";values.append(value("date_from"))
            if value("date_to"):query+=f" AND date({date_field})<=date(?)";values.append(value("date_to"))
            allowed=set(search_fields)
            if kind in ("delays","transfers"):allowed.add("status")
            for field,param in (("status","status"),("task_number","task"),("department","department"),("service","service"),("provider","provider"),("created_by","created_by")):
                if field in allowed and value(param):query+=f" AND lower(COALESCE({field},'')) LIKE lower(?)";values.append(f"%{value(param)}%")
            if value("q"):query+=" AND lower("+"||' '||".join(f"COALESCE({field},'')" for field in search_fields)+") LIKE lower(?)";values.append(f"%{value('q')}%")
            query+=f" ORDER BY {date_field} DESC"
            with connect() as db:result=rows(db,query,values)
            return self.send_bytes(report_csv_bytes(kind,result),"text/csv; charset=utf-8",f"reporte_{filename}.csv")
        view_permissions={"/api/dashboard":"dashboard.view","/api/notices":"notices.view","/api/delays":"delays.view","/api/transfers":"transfers.view","/api/quotes":"quotes.view","/api/standards":"standards.view","/api/audit":"audit.view"}
        if path in view_permissions and not self.require(view_permissions[path]): return
        with connect() as db:
            if path=="/api/dashboard": return self.send_json({"notices_open":db.execute("SELECT count(*) FROM notices WHERE status NOT IN ('RESUELTO','CANCELADO')").fetchone()[0],"delays_active":db.execute("SELECT count(*) FROM delay_zones WHERE status='VIGENTE'").fetchone()[0],"transfers_pending":db.execute("SELECT count(*) FROM scheduled_transfers WHERE status IN ('PENDIENTE','CONFIRMADO','SIN_ASIGNAR','ASIGNADO')").fetchone()[0]})
            q={"/api/delays":"SELECT * FROM delay_zones ORDER BY created_at DESC LIMIT 5000","/api/transfers":"SELECT * FROM scheduled_transfers ORDER BY scheduled_date,scheduled_time LIMIT 5000","/api/quotes":"SELECT * FROM quotes ORDER BY created_at DESC LIMIT 1000","/api/standards":"SELECT * FROM arrival_standards ORDER BY department,zone","/api/audit":"SELECT * FROM audit_events ORDER BY created_at DESC LIMIT 500"}
            if path in q: return self.send_json(rows(db,q[path]))
        self.send_json({"detail":"Ruta inexistente"},404)
    def do_POST(self):
        if not self.body_size_guard():return
        path=urlparse(self.path).path; d=self.payload(); stamp=now(); cfg={"/api/notices":("notices",["task_number","phone","notice_type","audience","detail","communicated_by","managed_by","status","comments"],"notice",d.get("communicated_by","Operador")),"/api/delays":("delay_zones",["service","department","zone","message","minutes","status","agent"],"delay",d.get("agent","Operador")),"/api/transfers":("scheduled_transfers",["task_number","transfer_type","scheduled_date","scheduled_time","origin","destination","provider","planner","status","comments"],"transfer",d.get("planner","Operador"))}
        if path not in ("/api/auth/login","/api/auth/google") and not self.csrf_guard():return
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
                try:db.execute("UPDATE users SET google_sub=? WHERE id=?",(identity["sub"],row["id"]));audit(db,"user",row["id"],"INGRESO_GOOGLE",row["display_name"],identity["email"])
                except sqlite3.IntegrityError:return self.send_json({"detail":"Esta cuenta de Google ya está vinculada a otro usuario"},403)
            clear_login_failures(google_key)
            SESSIONS.pop(self.session_token(),None);token=secrets.token_urlsafe(32);stamp=time.time();SESSIONS[token]={"user_id":row["id"],"expires":stamp+LOCAL_SESSION_SECONDS,"last_seen":stamp};return self.send_json({"ok":True},extra_headers=self.auth_cookie_headers(token))
        if path=="/api/auth/logout":
            session=SESSIONS.pop(self.session_token(),None)
            if session:
                with connect() as db:
                    user=db.execute("SELECT id,display_name FROM users WHERE id=?",(session["user_id"],)).fetchone()
                    if user:audit(db,"session",user["id"],"SALIDA",user["display_name"])
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
                if copied or skipped:audit(db,"schedule_week",int(target_week.replace("-","")),"COPIA_SEMANAL",actor["display_name"],f"{source_week} → {target_week}; copiados={copied}; omitidos={skipped}")
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
                cur=db.execute("INSERT INTO work_schedules(user_id,schedule_date,week_start,role_name,shift_name,start_time,end_time,notes,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(user_id,schedule_date,schedule_week_start(schedule_date),person["role_name"],shift_name,start_time,end_time,notes or None,actor["display_name"],stamp,stamp));audit(db,"schedule",cur.lastrowid,"CREADO",actor["display_name"],f"{schedule_date} · {person['role_name']}");item=schedule_record(db,cur.lastrowid)
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
                    cur=db.execute("INSERT INTO users(username,email,display_name,password_hash,role_id,active) VALUES(?,?,?,?,?,1)",(username,email,d["display_name"],hash_password(password),int(d["role_id"]))); audit(db,"user",cur.lastrowid,"CREADO",actor["display_name"],email)
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
                    audit(db,"role",role_id,"CREADO",actor["display_name"],name)
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
                    trip_km=float(d.get("manual_trip_km") or 0); mobile_km=float(d.get("manual_mobile_km") or 0) if d.get("include_mobile") else 0
                    if trip_km<=0 or mobile_km<0:raise ValueError("La distancia manual debe ser mayor a cero")
                    if d.get("include_mobile") and mobile_km<=0:raise ValueError("Ingrese los kilómetros desde la salida del móvil hasta el origen")
                    if d.get("include_tolls"):
                        raw_toll_count=d.get("manual_toll_count")
                        if isinstance(raw_toll_count,bool) or not re.fullmatch(r"\d+",str(raw_toll_count or "")):raise ValueError("Ingrese una cantidad válida de peajes")
                        manual_toll_count=int(raw_toll_count)
                        if not 1<=manual_toll_count<=100:raise ValueError("Ingrese una cantidad válida de peajes")
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
                        toll_price=round(manual_toll_count*toll_rate,2)
                        toll_passes=[] if not manual_toll_count else [{"name":f"Peajes manuales ({manual_toll_count})","segment":"Cantidad ingresada manualmente","price":toll_price}]
                        toll_count=manual_toll_count
                    else:
                        tolls=rows(db,"SELECT * FROM toll_catalog WHERE active=1")
                        toll_passes=detect_toll_passes(route_segments,tolls,toll_rate)
                        toll_price=round(sum(item["price"] for item in toll_passes),2);toll_count=len(toll_passes)
                    total_km=round(trip_km+mobile_km,2); extra_km=max(0,math.ceil(total_km-rule["included_km"])); extra_price=extra_km*rate; total_price=base+extra_price+toll_price
                    created_at=now()
                    cur=db.execute("INSERT INTO quotes(task_number,origin_input,destination_input,mobile_input,uninsured,special,gavilan,trip_km,mobile_km,total_km,included_km,extra_km,base_price,extra_price,toll_count,toll_details,toll_price,total_price,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(str(d.get("task_number") or "").strip() or None,d.get("origin") or "Cotización manual",d.get("destination") or "Cotización manual",d.get("mobile_origin"),uninsured,special,gavilan,trip_km,mobile_km,total_km,rule["included_km"],extra_km,base,extra_price,toll_count,json.dumps(toll_passes,ensure_ascii=False),toll_price,total_price,user["display_name"],created_at)); audit(db,"quote",cur.lastrowid,"COTIZADO",user["display_name"],f"${total_price:.0f}; peajes={toll_count}")
                customer_type=("No asegurado" if uninsured else "Asegurado")+(" · Gavilán" if gavilan else " · Especial" if special else "")
                return self.send_json({"id":cur.lastrowid,"task_number":str(d.get("task_number") or "").strip(),"created_at":created_at,"origin_input":d.get("origin") or "Cotización manual","destination_input":d.get("destination") or "Cotización manual","mobile_input":d.get("mobile_origin"),"uninsured":uninsured,"special":special,"gavilan":gavilan,"mode":"manual" if manual else "automatic","trip_km":trip_km,"mobile_km":mobile_km,"total_km":total_km,"included_km":rule["included_km"],"extra_km":extra_km,"base_price":base,"extra_rate":rate,"extra_price":extra_price,"toll_count":toll_count,"toll_details":toll_passes,"toll_price":toll_price,"total_price":total_price,"route_segments":route_segments,"customer_type":customer_type},201)
            except ValueError as exc:return self.send_json({"detail":str(exc)},400)
        create_permissions={"/api/notices":"notices.create","/api/delays":"delays.create","/api/transfers":"transfers.create"}
        if path=="/api/settings/tolls":
            actor=self.require("settings.manage")
            if not actor:return
            try:
                name=str(d.get("name") or "").strip();latitude=float(d.get("latitude"));longitude=float(d.get("longitude"));price=None if d.get("price") in (None,"") else float(d["price"])
                if not 2<=len(name)<=120 or not -35.5<=latitude<=-29 or not -59.5<=longitude<=-52 or price is not None and price<0:raise ValueError()
            except (TypeError,ValueError):return self.send_json({"detail":"Nombre, coordenadas uruguayas o tarifa inválidos"},400)
            with connect() as db:
                stamp=now();cur=db.execute("INSERT INTO toll_catalog(name,latitude,longitude,price,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",(name,latitude,longitude,price,1 if d.get("active",True) else 0,stamp,stamp));audit(db,"toll",cur.lastrowid,"CREADO",actor["display_name"],name)
            return self.send_json({"ok":True},201)
        if path in create_permissions:
            actor_user=self.require(create_permissions[path])
            if not actor_user:return
            if path=="/api/notices":d["communicated_by"]=actor_user["display_name"]
            elif path=="/api/delays":d["agent"]=actor_user["display_name"]
            else:d["planner"]=actor_user["display_name"]
            cfg={"/api/notices":("notices",["task_number","phone","notice_type","audience","detail","communicated_by","managed_by","status","comments"],"notice",d.get("communicated_by")),"/api/delays":("delay_zones",["service","department","zone","message","minutes","status","agent"],"delay",d.get("agent")),"/api/transfers":("scheduled_transfers",["task_number","transfer_type","scheduled_date","scheduled_time","origin","destination","provider","planner","status","comments"],"transfer",d.get("planner"))}
        if path not in cfg: return self.send_json({"detail":"Ruta inexistente"},404)
        table,fields,entity,actor=cfg[path]; defaults={"audience":"TODOS","status":"PENDIENTE","service":"TODAS","message":"Margen de"}; vals=[d.get(f,defaults.get(f)) for f in fields]; extra=["created_at","updated_at"] if table=="notices" else ["created_at"]; vals += [stamp]*len(extra); fields += extra
        with connect() as db:
            cur=db.execute(f"INSERT INTO {table} ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",vals); audit(db,entity,cur.lastrowid,"CREADO",actor); item=dict(db.execute(f"SELECT * FROM {table} WHERE id=?",(cur.lastrowid,)).fetchone())
        self.send_json(item,201)
    def do_PATCH(self):
        if not self.body_size_guard():return
        p=urlparse(self.path).path.strip("/").split("/"); d=self.payload(); stamp=now()
        if not self.csrf_guard():return
        if p==["api","settings","google-access"]:
            user=self.require("settings.manage")
            if not user:return
            client_id=str(d.get("client_id") or "").strip()
            if client_id and not re.fullmatch(r"\d+-[a-z0-9_-]+\.apps\.googleusercontent\.com",client_id,re.I):return self.send_json({"detail":"El ID de cliente OAuth de Google no tiene un formato válido"},400)
            with connect() as db:db.execute("INSERT OR REPLACE INTO app_settings(key,value) VALUES('google_client_id',?)",(client_id,));audit(db,"settings",1,"GOOGLE_ACTUALIZADO",user["display_name"],"Activado" if client_id else "Desactivado")
            return self.send_json({"ok":True,"enabled":bool(client_id)})
        if p==["api","settings","quote-rules"]:
            user=self.require("settings.manage")
            if not user:return
            fields=["insured_base","uninsured_base","special_insured_base","special_uninsured_base","gavilan_base","included_km","extra_km_rate","special_extra_km_rate",*QUOTE_RULE_EXTRA_COLUMNS]
            try:
                with connect() as db:
                    current=dict(db.execute("SELECT * FROM quote_rules WHERE id=1").fetchone())
                    values=[float(d[field] if field in d else current[field]) for field in fields]
                    if any(value<0 for value in values):return self.send_json({"detail":"Las tarifas no pueden ser negativas"},400)
                    db.execute(f"UPDATE quote_rules SET {','.join(field+'=?' for field in fields)},updated_at=? WHERE id=1",values+[now()]);audit(db,"quote_rules",1,"ACTUALIZADO",user["display_name"])
            except (KeyError,TypeError,ValueError):return self.send_json({"detail":"Todas las tarifas deben ser numéricas"},400)
            return self.send_json({"ok":True})
        if len(p)==4 and p[:3]==["api","settings","tolls"]:
            actor=self.require("settings.manage")
            if not actor:return
            try:
                name=str(d.get("name") or "").strip();latitude=float(d.get("latitude"));longitude=float(d.get("longitude"));price=None if d.get("price") in (None,"") else float(d["price"])
                if not 2<=len(name)<=120 or not -35.5<=latitude<=-29 or not -59.5<=longitude<=-52 or price is not None and price<0:raise ValueError()
                item_id=int(p[3])
            except (TypeError,ValueError):return self.send_json({"detail":"Nombre, coordenadas uruguayas o tarifa inválidos"},400)
            with connect() as db:
                cur=db.execute("UPDATE toll_catalog SET name=?,latitude=?,longitude=?,price=?,active=?,updated_at=? WHERE id=?",(name,latitude,longitude,price,1 if d.get("active",True) else 0,now(),item_id))
                if not cur.rowcount:return self.send_json({"detail":"Peaje inexistente"},404)
                audit(db,"toll",item_id,"ACTUALIZADO",actor["display_name"],name)
            return self.send_json({"ok":True})
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
                current=db.execute("SELECT id FROM work_schedules WHERE id=?",(item_id,)).fetchone()
                if not current:return self.send_json({"detail":"Horario inexistente"},404)
                conflict=local_schedule_conflict(db,user_id,schedule_date,shift_name,start_time,end_time,item_id)
                if conflict:return self.send_json({"detail":schedule_conflict_message(conflict)},409)
                db.execute("UPDATE work_schedules SET user_id=?,schedule_date=?,week_start=?,role_name=?,shift_name=?,start_time=?,end_time=?,notes=?,updated_at=? WHERE id=?",(user_id,schedule_date,schedule_week_start(schedule_date),person["role_name"],shift_name,start_time,end_time,notes or None,stamp,item_id));audit(db,"schedule",item_id,"EDITADO",actor["display_name"],f"{schedule_date} · {person['role_name']}");item=schedule_record(db,item_id)
            return self.send_json(dict(item))
        if len(p)==3 and p[0]=="api" and p[1]=="transfers":
            user=self.require("transfers.manage")
            if not user:return
            item_id=int(p[2]); fields=["task_number","transfer_type","scheduled_date","scheduled_time","origin","destination","provider","comments"]
            with connect() as db:
                db.execute(f"UPDATE scheduled_transfers SET {','.join(x+'=?' for x in fields)} WHERE id=?",[d.get(x) for x in fields]+[item_id]); audit(db,"transfer",item_id,"EDITADO",user["display_name"],d.get("task_number","")); item=db.execute("SELECT * FROM scheduled_transfers WHERE id=?",(item_id,)).fetchone()
            return self.send_json(dict(item) if item else {"detail":"Registro inexistente"},200 if item else 404)
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
                    previous=db.execute("SELECT email FROM users WHERE id=?",(item_id,)).fetchone()
                    if not previous:return self.send_json({"detail":"Usuario inexistente"},404)
                    current_role=db.execute("SELECT r.name FROM users u JOIN roles r ON r.id=u.role_id WHERE u.id=?",(item_id,)).fetchone()
                    target_role=db.execute("SELECT name FROM roles WHERE id=?",(int(d["role_id"]),)).fetchone()
                    if not target_role:return self.send_json({"detail":"El rol indicado no existe"},400)
                    if current_role and current_role[0]=="Administrador" and (not d.get("active",True) or target_role[0]!="Administrador"):
                        other_admins=db.execute("SELECT count(*) FROM users u JOIN roles r ON r.id=u.role_id WHERE u.active=1 AND r.name='Administrador' AND u.id<>?",(item_id,)).fetchone()[0]
                        if other_admins<1:return self.send_json({"detail":"No se puede dejar el sistema sin un Administrador activo"},400)
                    if str(previous["email"] or "").lower()!=email:fields.append("google_sub=NULL")
                    db.execute(f"UPDATE users SET {','.join(fields)} WHERE id=?",values); audit(db,"user",item_id,"ACTUALIZADO",user["display_name"],email)
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
                db.execute("DELETE FROM role_permissions WHERE role_id=?",(item_id,)); db.executemany("INSERT INTO role_permissions(role_id,permission) VALUES(?,?)",[(item_id,x) for x in valid]); audit(db,"role",item_id,"PERMISOS_ACTUALIZADOS",user["display_name"],", ".join(valid))
            return self.send_json({"ok":True})
        permission="delays.normalize" if kind=="delays" else "notices.manage" if kind=="notices" else "transfers.manage"
        user=self.require(permission)
        if not user:return
        actor=user["display_name"]
        with connect() as db:
            if kind=="notices" and action=="status": db.execute("UPDATE notices SET status=?,managed_by=COALESCE(?,managed_by),comments=COALESCE(?,comments),updated_at=? WHERE id=?",(d["status"],d.get("managed_by"),d.get("comments"),now(),item_id)); table="notices"; entity="notice"
            elif kind=="transfers" and action=="status": db.execute("UPDATE scheduled_transfers SET status=? WHERE id=?",(d["status"],item_id)); table="scheduled_transfers"; entity="transfer"
            elif kind=="delays" and action=="normalize": db.execute("UPDATE delay_zones SET status='NORMALIZADO',normalized_at=? WHERE id=?",(now(),item_id)); table="delay_zones"; entity="delay"
            else: return self.send_json({"detail":"Ruta inexistente"},404)
            audit(db,entity,item_id,"CAMBIO_ESTADO",actor,d.get("status","NORMALIZADO")); item=db.execute(f"SELECT * FROM {table} WHERE id=?",(item_id,)).fetchone()
        self.send_json(dict(item) if item else {"detail":"Registro inexistente"},200 if item else 404)

    def do_DELETE(self):
        p=urlparse(self.path).path.strip("/").split("/")
        if not self.csrf_guard():return
        if len(p)==3 and p[0]=="api" and p[1]=="schedules":
            user=self.require("schedules.manage")
            if not user:return
            item_id=int(p[2])
            with connect() as db:
                item=db.execute("SELECT schedule_date,shift_name FROM work_schedules WHERE id=?",(item_id,)).fetchone()
                if not item:return self.send_json({"detail":"Horario inexistente"},404)
                audit(db,"schedule",item_id,"ELIMINADO",user["display_name"],f"{item['schedule_date']} · {item['shift_name']}");db.execute("DELETE FROM work_schedules WHERE id=?",(item_id,))
            return self.send_json({"ok":True})
        if len(p)==4 and p[:3]==["api","settings","tolls"]:
            actor=self.require("settings.manage")
            if not actor:return
            try:item_id=int(p[3])
            except ValueError:return self.send_json({"detail":"Peaje inválido"},400)
            with connect() as db:
                item=db.execute("SELECT name FROM toll_catalog WHERE id=?",(item_id,)).fetchone()
                if not item:return self.send_json({"detail":"Peaje inexistente"},404)
                db.execute("DELETE FROM toll_catalog WHERE id=?",(item_id,));audit(db,"toll",item_id,"ELIMINADO",actor["display_name"],item["name"])
            return self.send_json({"ok":True})
        if len(p)!=3 or p[0]!="api" or p[1]!="transfers":return self.send_json({"detail":"Ruta inexistente"},404)
        user=self.require("transfers.manage")
        if not user:return
        item_id=int(p[2])
        with connect() as db:
            item=db.execute("SELECT task_number FROM scheduled_transfers WHERE id=?",(item_id,)).fetchone()
            if not item:return self.send_json({"detail":"Programado inexistente"},404)
            audit(db,"transfer",item_id,"ELIMINADO",user["display_name"],item["task_number"]); db.execute("DELETE FROM scheduled_transfers WHERE id=?",(item_id,))
        self.send_json({"ok":True})

if __name__=="__main__":
    try:
        backup_path=create_daily_backup()
        if backup_path:print(f"Copia de seguridad: {backup_path}")
    except Exception as exc:
        print(f"ADVERTENCIA: no se pudo crear la copia de seguridad: {exc}")
    initialize(); server=ThreadingHTTPServer((HOST,PORT),Handler); print("Centro Operativo esta funcionando."); print(f"Direccion: http://{HOST}:{PORT}"); print("No cierre esta ventana mientras use la herramienta.")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
