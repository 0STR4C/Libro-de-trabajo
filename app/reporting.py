"""Formatos de reportes operativos descargables."""
import csv
import io

NOTICE_REPORT_COLUMNS = (
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
    ("Fecha de registro", "created_at"), ("Fecha de normalización", "normalized_at"),
    ("Estado", "status"), ("Prestación", "service"), ("Departamento", "department"),
    ("Zona afectada", "zone"), ("Mensaje al cliente", "message"),
    ("Minutos informados", "minutes"), ("Registrado por", "agent"),
)

TRANSFER_REPORT_COLUMNS = (
    ("Número de tarea", "task_number"), ("Tipo de traslado", "transfer_type"),
    ("Fecha programada", "scheduled_date"), ("Hora programada", "scheduled_time"),
    ("Origen", "origin"), ("Destino", "destination"), ("Prestador", "provider"),
    ("Planificado por", "planner"), ("Estado", "status"), ("Comentarios", "comments"),
    ("Fecha de creación", "created_at"),
)

QUOTE_REPORT_COLUMNS = (
    ("Fecha de cotización", "created_at"), ("Número de tarea", "task_number"),
    ("Origen", "origin_input"), ("Destino", "destination_input"), ("Salida del móvil", "mobile_input"),
    ("No asegurado", "uninsured"), ("Especial", "special"), ("Gavilán", "gavilan"),
    ("Kilómetros de traslado", "trip_km"), ("Kilómetros del móvil", "mobile_km"),
    ("Kilómetros totales", "total_km"), ("Kilómetros incluidos", "included_km"),
    ("Kilómetros excedentes", "extra_km"), ("Precio base", "base_price"),
    ("Precio adicional", "extra_price"), ("Cantidad de peajes", "toll_count"),
    ("Peajes detectados", "toll_details"), ("Costo de peajes", "toll_price"),
    ("Precio total", "total_price"),
    ("Cotizado por", "created_by"),
)

AUDIT_REPORT_COLUMNS = (
    ("Fecha", "created_at"), ("Registro", "entity"), ("ID", "entity_id"),
    ("Acción", "action"), ("Usuario", "actor"), ("Detalle", "detail"),
)

SCHEDULE_REPORT_COLUMNS = (
    ("Fecha", "schedule_date"), ("Semana", "week_start"), ("Persona", "display_name"),
    ("Rol", "role_name"), ("Turno", "shift_name"), ("Hora de inicio", "start_time"),
    ("Hora de fin", "end_time"), ("Notas", "notes"), ("Configurado por", "created_by"),
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
