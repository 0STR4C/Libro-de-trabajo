"""Reglas de avisos independientes del motor de base de datos."""

from __future__ import annotations

import re
import hashlib


NOTICE_STATUSES = {"PENDIENTE", "EN_GESTION", "ESPERANDO_RESPUESTA", "RESUELTO", "CANCELADO"}
NOTICE_AUDIENCES = {"TODOS", "TELEFONISTAS", "PLANIFICADORES"}
NOTICE_CLOSED_STATUSES = {"RESUELTO", "CANCELADO"}


def notice_update_permissions(current, data):
    requested = set()
    if "managed_by" in data and data.get("managed_by") != current.get("managed_by"):
        requested.add("notices.assign")
    closing = "status" in data and data.get("status") in NOTICE_CLOSED_STATUSES and data.get("status") != current.get("status")
    if "comments" in data and not closing:
        requested.add("notices.comment")
    if "status" in data and data.get("status") != current.get("status"):
        status = str(data.get("status") or "")
        if status not in NOTICE_STATUSES:
            raise ValueError("Estado de aviso inválido")
        requested.add("notices.close" if status in NOTICE_CLOSED_STATUSES else "notices.change_status")
    return requested


def notice_duplicate_reason(existing, candidate):
    existing_task = str(existing.get("task_number") or "").strip().casefold()
    candidate_task = str(candidate.get("task_number") or "").strip().casefold()
    if candidate_task and existing_task == candidate_task:
        return "Mismo número de tarea"
    existing_phone = re.sub(r"\D", "", str(existing.get("phone") or ""))
    candidate_phone = re.sub(r"\D", "", str(candidate.get("phone") or ""))
    existing_type = str(existing.get("notice_type") or "").strip().casefold()
    candidate_type = str(candidate.get("notice_type") or "").strip().casefold()
    if len(candidate_phone) >= 6 and existing_phone == candidate_phone and existing_type == candidate_type:
        return "Mismo teléfono y motivo"
    return ""


def notice_duplicate_keys(candidate):
    task = str(candidate.get("task_number") or "").strip().casefold()
    phone = re.sub(r"\D", "", str(candidate.get("phone") or ""))
    notice_type = str(candidate.get("notice_type") or "").strip().casefold()
    return task, phone, notice_type


def notice_duplicate_lock_keys(candidate):
    task, phone, notice_type = notice_duplicate_keys(candidate)
    keys = []
    if task:
        keys.append(f"notice:task:{task}")
    if len(phone) >= 6:
        keys.append(f"notice:phone-type:{phone}:{notice_type}")
    return sorted(keys)


def ensure_notice_duplicate_lookup(database, *, postgres=False):
    """Agrega claves de búsqueda; conserva los valores originales del aviso."""
    columns = ("duplicate_task_key", "duplicate_phone_key", "duplicate_type_key")
    if postgres:
        for column in columns:
            database.execute(f"ALTER TABLE notices ADD COLUMN IF NOT EXISTS {column} TEXT NOT NULL DEFAULT ''")
        placeholder = "%s"
    else:
        existing = {row[1] for row in database.execute("PRAGMA table_info(notices)").fetchall()}
        for column in columns:
            if column not in existing:
                database.execute(f"ALTER TABLE notices ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        placeholder = "?"
    migration_key = "notice_duplicate_lookup_v1"
    if not database.execute(f"SELECT 1 FROM schema_migrations WHERE key={placeholder}", (migration_key,)).fetchone():
        last_id = 0
        while True:
            batch = database.execute(
                f"SELECT id,task_number,phone,notice_type FROM notices WHERE id>{placeholder} ORDER BY id LIMIT 1000",
                (last_id,),
            ).fetchall()
            if not batch:
                break
            updates = [(*notice_duplicate_keys(dict(row)), row["id"]) for row in batch]
            database.cursor().executemany(
                f"UPDATE notices SET duplicate_task_key={placeholder},duplicate_phone_key={placeholder},duplicate_type_key={placeholder} WHERE id={placeholder}",
                updates,
            )
            last_id = batch[-1]["id"]
        database.execute(
            f"INSERT INTO schema_migrations(key,applied_at,checksum) VALUES({placeholder},CURRENT_TIMESTAMP,{placeholder})",
            (migration_key, hashlib.sha256(migration_key.encode('utf-8')).hexdigest()),
        )
    database.execute("""CREATE INDEX IF NOT EXISTS notice_open_task_key_idx
        ON notices(duplicate_task_key,created_at DESC,id DESC)
        WHERE status NOT IN ('RESUELTO','CANCELADO') AND duplicate_task_key<>''""")
    database.execute("""CREATE INDEX IF NOT EXISTS notice_open_phone_type_key_idx
        ON notices(duplicate_phone_key,duplicate_type_key,created_at DESC,id DESC)
        WHERE status NOT IN ('RESUELTO','CANCELADO') AND duplicate_phone_key<>''""")


def notice_duplicates(database, candidate, limit=5, *, postgres=False):
    task, phone, notice_type = notice_duplicate_keys(candidate)
    if limit <= 0 or not task and len(phone) < 6:
        return []
    placeholder = "%s" if postgres else "?"
    fields = "id,task_number,phone,notice_type,managed_by,status,created_at"
    visibility = "administratively_retired_at IS NULL"
    base = f" FROM notices WHERE status NOT IN ('RESUELTO','CANCELADO') AND {visibility} AND "
    order = f" ORDER BY created_at DESC,id DESC LIMIT {placeholder}"
    records = {}
    if task:
        query = f"SELECT {fields}{base}duplicate_task_key<>'' AND duplicate_task_key={placeholder}{order}"
        for record in database.execute(query, (task, limit)).fetchall():
            records[record["id"]] = record
    if len(phone) >= 6:
        query = f"SELECT {fields}{base}duplicate_phone_key<>'' AND duplicate_phone_key={placeholder} AND duplicate_type_key={placeholder}{order}"
        for record in database.execute(query, (phone, notice_type, limit)).fetchall():
            records[record["id"]] = record
    matches = []
    for record in sorted(records.values(), key=lambda item: (item["created_at"], item["id"]), reverse=True):
        existing = dict(record)
        reason = notice_duplicate_reason(existing, candidate)
        if reason:
            summary = {key: existing.get(key) for key in ("id", "task_number", "phone", "notice_type", "managed_by", "status", "created_at")}
            if hasattr(summary["created_at"], "isoformat"):
                summary["created_at"] = summary["created_at"].isoformat()
            summary["duplicate_reason"] = reason
            matches.append(summary)
            if len(matches) >= limit:
                break
    return matches
