"""Metadatos y permisos compartidos por los adaptadores HTTP."""

try:
    from .releases import release_payload
except ImportError:
    from releases import release_payload


APP_VERSION = "1.32.0"
CURRENT_VERSION_NOTES = [
    "El alta de avisos ofrece motivos predefinidos, etiquetas opcionales claras y menos texto técnico.",
    "La autoasignación se realiza directamente desde la columna Responsable.",
    "Cada aviso reúne Asignar, Editar e Historial en un menú contextual según rol y permisos.",
    "El selector de estado despliega sus opciones debajo del control en escritorio y móvil.",
]

PERMISSIONS = {
    "dashboard.view": "Ver resumen",
    "delays.view": "Ver demoras",
    "delays.create": "Registrar demoras",
    "delays.normalize": "Normalizar demoras",
    "notices.view": "Ver avisos",
    "notices.create": "Registrar avisos",
    "notices.comment": "Comentar avisos",
    "notices.assign": "Asignar avisos",
    "notices.change_status": "Cambiar estados de avisos",
    "notices.close": "Cerrar o cancelar avisos",
    "reports.export": "Filtrar y descargar reportes",
    "transfers.view": "Ver programados",
    "transfers.create": "Registrar programados",
    "transfers.manage": "Editar y cambiar el estado de programados",
    "schedules.view": "Ver horarios del equipo",
    "schedules.manage": "Configurar y editar horarios",
    "quotes.view": "Ver cotizador e historial",
    "quotes.create": "Generar cotizaciones",
    "standards.view": "Ver tiempos de arribo",
    "standards.propose": "Proponer referencias de arribo",
    "standards.approve": "Aprobar referencias de arribo",
    "audit.view": "Ver registro de auditoría",
    "settings.manage": "Administrar usuarios, roles y permisos",
}
NOTICE_MANAGE_PERMISSIONS = {"notices.comment", "notices.assign", "notices.change_status", "notices.close"}
DEFAULT_ROLES = {
    "Administrador": set(PERMISSIONS),
    "Supervisor": set(PERMISSIONS) - {"settings.manage", "audit.view"},
    "Planificador": set(PERMISSIONS) - {"settings.manage", "audit.view", "reports.export", "standards.approve"},
    "Telefonista": {
        "dashboard.view", "delays.view", "notices.view", "notices.create", "notices.comment",
        "notices.assign", "notices.change_status", "notices.close", "transfers.view", "quotes.view",
        "quotes.create", "standards.view", "standards.propose", "schedules.view",
    },
}
SCHEDULE_ROLES = ("Telefonista", "Planificador", "Supervisor")


def current_release_payload():
    return release_payload(APP_VERSION, "2026-09-23", CURRENT_VERSION_NOTES)
