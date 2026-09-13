"""Formatos de reportes operativos descargables."""
import csv
import io
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

try:
    from .transfers import normalized_status
except ImportError:
    from transfers import normalized_status


REPORT_TIMEZONE = ZoneInfo("America/Montevideo")

NOTICE_REPORT_COLUMNS = (
    ("ID", "id"),
    ("Fecha de creación", "created_at"),
    ("Última actualización", "updated_at"),
    ("Número de tarea", "task_number"),
    ("Teléfono o contacto", "phone"),
    ("Motivo del aviso", "notice_type"),
    ("Destinatario", "audience"),
    ("Detalle", "detail"),
    ("Aviso registrado por", "communicated_by"),
    ("Gestionado por", "managed_by"),
    ("Estado", "status"),
    ("Comentarios", "comments"),
)

DELAY_REPORT_COLUMNS = (
    ("ID", "id"),
    ("Fecha de registro", "created_at"), ("Fecha de normalización", "normalized_at"),
    ("Última verificación", "last_verified_at"), ("Revisión prevista", "expires_at"),
    ("Estado", "status"), ("Prestación", "service"), ("Departamento", "department"),
    ("Zona afectada", "zone"), ("Mensaje al cliente", "message"),
    ("Minutos informados", "minutes"), ("Registrado por", "agent"),
    ("Normalizado por", "normalized_by"), ("Evidencia de cierre", "resolution_note"),
)

TRANSFER_REPORT_COLUMNS = (
    ("ID", "id"),
    ("Número de tarea", "task_number"), ("Tipo de traslado", "transfer_type"),
    ("Fecha programada", "scheduled_date"), ("Hora programada", "scheduled_time"),
    ("Origen", "origin"), ("Destino", "destination"), ("Prestador", "provider"),
    ("Responsable interno", "responsible"), ("Planificado por", "planner"),
    ("Estado", "status"), ("Comentarios", "comments"),
    ("Asignado", "assigned_at"), ("Iniciado", "started_at"),
    ("Finalizado", "completed_at"), ("Resultado", "completion_note"),
    ("Cancelado", "cancelled_at"), ("Motivo de cancelación", "cancellation_reason"),
    ("Fecha de creación", "created_at"), ("Última actualización", "updated_at"),
    ("Actualizado por", "updated_by"),
)

QUOTE_REPORT_COLUMNS = (
    ("ID", "id"),
    ("Fecha de cotización", "created_at"), ("Número de tarea", "task_number"),
    ("Origen", "origin_input"), ("Destino", "destination_input"), ("Salida del móvil", "mobile_input"),
    ("No asegurado", "uninsured"), ("Especial", "special"), ("Gavilán", "gavilan"),
    ("Kilómetros de traslado", "trip_km"), ("Kilómetros del móvil", "mobile_km"),
    ("Kilómetros totales", "total_km"), ("Kilómetros incluidos", "included_km"),
    ("Kilómetros excedentes", "extra_km"), ("Precio base", "base_price"),
    ("Precio adicional", "extra_price"), ("Cantidad de peajes", "toll_count"),
    ("Peajes detectados", "toll_details"), ("Costo de peajes", "toll_price"),
    ("Precio total", "total_price"), ("Snapshot tarifario", "pricing_snapshot"),
    ("Cotizado por", "created_by"),
)

AUDIT_REPORT_COLUMNS = (
    ("ID de evento", "id"), ("Fecha", "created_at"), ("Registro", "entity"), ("ID de registro", "entity_id"),
    ("Acción", "action"), ("ID de usuario", "actor_id"),
    ("Usuario", "actor_name"), ("Detalle", "detail"),
    ("Antes", "before_data"), ("Después", "after_data"),
    ("Correlación", "correlation_id"), ("Origen", "source"),
)

SCHEDULE_REPORT_COLUMNS = (
    ("ID", "id"), ("Fecha", "schedule_date"), ("Semana", "week_start"), ("Persona", "display_name"),
    ("Rol", "role_name"), ("Turno", "shift_name"), ("Hora de inicio", "start_time"),
    ("Hora de fin", "end_time"), ("Notas", "notes"), ("Origen", "source"),
    ("Revisión WFM", "revision"), ("Segmentos", "segments"), ("Descanso", "break_slot"),
    ("Excepciones", "exceptions"), ("Configurado por", "created_by"),
    ("Fecha de creación", "created_at"), ("Última actualización", "updated_at"),
)

REPORT_COLUMNS = {
    "notices": NOTICE_REPORT_COLUMNS,
    "delays": DELAY_REPORT_COLUMNS,
    "transfers": TRANSFER_REPORT_COLUMNS,
    "quotes": QUOTE_REPORT_COLUMNS,
    "audit": AUDIT_REPORT_COLUMNS,
    "schedules": SCHEDULE_REPORT_COLUMNS,
}


def spreadsheet_safe(value):
    """Evita que Excel interprete texto operativo como una fórmula."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


def report_csv_bytes(kind, records):
    columns = REPORT_COLUMNS[kind]
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow([label for label, _field in columns])
    for record in records:
        writer.writerow([spreadsheet_safe(record.get(field)) for _label, field in columns])
    return output.getvalue().encode("utf-8-sig")


def notice_csv_bytes(records):
    return report_csv_bytes("notices", records)


def _text(value):
    return str(value or "").strip()


def _contains(value, expected):
    return _text(expected).casefold() in _text(value).casefold()


def _local_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value,str) and len(value)==10:
        return date.fromisoformat(value)
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(REPORT_TIMEZONE).date()


def normalized_report_filters(kind, filters=None, *, managed_by=""):
    """Devuelve únicamente filtros reconocidos, listos para consulta y auditoría."""
    allowed = {
        "notices": ("date_from", "date_to", "status", "scope", "task", "contact", "q"),
        "delays": ("date_from", "date_to", "scope", "status", "department", "service", "q"),
        "transfers": ("date_from", "date_to", "status", "transfer_type", "provider", "responsible", "task", "q"),
        "quotes": ("date_from", "date_to", "q", "coverage", "mode", "created_by"),
        "audit": ("date_from", "date_to", "entity", "entity_id", "action", "actor_id", "q"),
    }
    if kind not in allowed:
        raise KeyError(kind)
    source = filters or {}
    result = {name: _text(source.get(name)) for name in allowed[kind] if _text(source.get(name))}
    if kind == "notices" and result.get("scope") == "mine":
        result["managed_by"] = _text(managed_by)
    return result


def filter_report_records(kind, records, filters=None, *, managed_by="", current_time=None):
    """Aplica el mismo contrato a filas de pantalla y de exportación."""
    selected = normalized_report_filters(kind, filters, managed_by=managed_by)
    start = date.fromisoformat(selected["date_from"]) if selected.get("date_from") else None
    end = date.fromisoformat(selected["date_to"]) if selected.get("date_to") else None
    date_field = {"notices": "created_at", "delays": "created_at", "transfers": "scheduled_date", "quotes": "created_at", "audit": "created_at"}[kind]
    result = []
    for source in records:
        item = dict(source)
        item_date = _local_date(item.get(date_field))
        if start and (item_date is None or item_date < start):
            continue
        if end and (item_date is None or item_date > end):
            continue
        if kind == "notices":
            scope = selected.get("scope", "")
            if selected.get("status") and item.get("status") != selected["status"]:
                continue
            if scope in {"open", "unassigned", "mine", "waiting"} and item.get("status") in {"RESUELTO", "CANCELADO"}:
                continue
            if scope == "unassigned" and _text(item.get("managed_by")):
                continue
            if scope == "mine" and item.get("managed_by") != selected.get("managed_by"):
                continue
            if scope == "waiting" and item.get("status") != "ESPERANDO_RESPUESTA":
                continue
            if selected.get("task") and not _contains(item.get("task_number"), selected["task"]):
                continue
            if selected.get("contact") and not _contains(item.get("phone"), selected["contact"]):
                continue
            search_fields = ("task_number", "phone", "notice_type", "detail", "managed_by", "communicated_by", "comments")
        elif kind == "delays":
            scope = selected.get("scope", "")
            if not scope and selected.get("status") == "VIGENTE":
                scope = "all_current_status"
            elif not scope and selected.get("status") == "NORMALIZADO":
                scope = "normalized"
            if scope == "current" and not item.get("is_current"):
                continue
            if scope == "review" and not item.get("needs_review"):
                continue
            if scope == "normalized" and item.get("status") != "NORMALIZADO":
                continue
            if scope == "all_current_status" and item.get("status") != "VIGENTE":
                continue
            if selected.get("department") and _text(item.get("department")).casefold() != selected["department"].casefold():
                continue
            if selected.get("service") and _text(item.get("service")).casefold() != selected["service"].casefold():
                continue
            search_fields = ("service", "department", "zone", "message", "agent", "normalized_by", "resolution_note", "created_at", "normalized_at")
        elif kind == "transfers":
            item["status"] = normalized_status(item.get("status"))
            wanted = selected.get("status", "")
            if wanted.upper() == "ACTIVE" and item["status"] not in {"SIN_ASIGNAR", "ASIGNADO", "EN_CURSO"}:
                continue
            if wanted and wanted.upper() != "ACTIVE" and item["status"] != normalized_status(wanted):
                continue
            if selected.get("transfer_type") and item.get("transfer_type") != selected["transfer_type"]:
                continue
            if selected.get("provider") and not _contains(item.get("provider"), selected["provider"]):
                continue
            if selected.get("responsible") and not _contains(item.get("responsible"), selected["responsible"]):
                continue
            if selected.get("task") and not _contains(item.get("task_number"), selected["task"]):
                continue
            search_fields = ("task_number", "transfer_type", "origin", "destination", "provider", "responsible", "planner", "comments")
        elif kind == "quotes":
            coverage = selected.get("coverage")
            if coverage in {"insured", "uninsured"} and bool(item.get("uninsured")) != (coverage == "uninsured"):
                continue
            mode = selected.get("mode")
            is_manual = item.get("origin_input") == "Cotización manual"
            if mode in {"manual", "automatic"} and is_manual != (mode == "manual"):
                continue
            if selected.get("created_by") and not _contains(item.get("created_by"), selected["created_by"]):
                continue
            search_fields = ("task_number", "origin_input", "destination_input", "mobile_input", "created_by")
        else:
            if selected.get("entity") and item.get("entity") != selected["entity"]:
                continue
            if selected.get("entity_id") and str(item.get("entity_id")) != selected["entity_id"]:
                continue
            if selected.get("action") and item.get("action") != selected["action"]:
                continue
            if selected.get("actor_id") and str(item.get("actor_id") or "") != selected["actor_id"]:
                continue
            if not item.get("actor_name"):
                item["actor_name"] = item.get("actor")
            search_fields = ("entity", "action", "actor_name", "actor", "detail")
        if selected.get("q") and not any(_contains(item.get(field), selected["q"]) for field in search_fields):
            continue
        result.append(item)
    reverse = kind != "transfers"
    result.sort(key=lambda item: (_text(item.get(date_field)), int(item.get("id") or 0)), reverse=reverse)
    return result
