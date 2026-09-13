"""Reglas de avisos independientes del motor de base de datos."""

from __future__ import annotations

import re


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


def notice_duplicates(database, candidate, limit=5):
    if not str(candidate.get("task_number") or "").strip() and len(re.sub(r"\D", "", str(candidate.get("phone") or ""))) < 6:
        return []
    matches = []
    records = database.execute(
        "SELECT * FROM notices WHERE status NOT IN ('RESUELTO','CANCELADO') ORDER BY created_at DESC LIMIT 5000"
    ).fetchall()
    for record in records:
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
