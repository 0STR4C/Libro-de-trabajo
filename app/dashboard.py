"""Definiciones canónicas y cálculo puro del panel operativo."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

try:
    from .delays import enrich_delay, standard_availability
    from .transfers import normalized_status
except ImportError:  # Compatibilidad con `python app/local_server.py`.
    from delays import enrich_delay, standard_availability
    from transfers import normalized_status


DEFINITIONS_VERSION = "1.0"
DASHBOARD_TIMEZONE = "America/Montevideo"
OPEN_NOTICE_STATUSES = ("PENDIENTE", "EN_GESTION", "ESPERANDO_RESPUESTA")
PENDING_TRANSFER_STATUSES = ("SIN_ASIGNAR", "ASIGNADO", "EN_CURSO")


def _utc_datetime(value) -> datetime | None:
    if value in (None, ""):
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _status_counts(rows, normalizer=lambda value: str(value or "").strip().upper()) -> Counter:
    result = Counter()
    for row in rows:
        result[normalizer(row.get("status"))] += int(row.get("total", 0))
    return result


def build_dashboard_payload(
    *,
    notice_status_counts,
    active_delays,
    transfer_status_counts,
    period_delays,
    verification_events,
    standards,
    expected_zone_services,
    days=30,
    current_time=None,
):
    """Construye todos los indicadores con un único instante y sin límites de lista."""
    as_of = _utc_datetime(current_time) or datetime.now(timezone.utc)
    days = max(1, min(int(days), 365))
    period_start = as_of - timedelta(days=days)

    notices = _status_counts(notice_status_counts)
    transfers = _status_counts(transfer_status_counts, normalized_status)
    enriched_active = [enrich_delay(item, as_of) for item in active_delays]
    current_delays = [item for item in enriched_active if item["is_current"]]
    review_delays = [item for item in enriched_active if item["needs_review"]]

    created = []
    normalized = []
    for item in period_delays:
        created_at = _utc_datetime(item.get("created_at"))
        normalized_at = _utc_datetime(item.get("normalized_at"))
        if created_at and period_start <= created_at <= as_of:
            created.append(item)
        if item.get("status") == "NORMALIZADO" and normalized_at and period_start <= normalized_at <= as_of:
            normalized.append(item)

    durations = []
    for item in normalized:
        created_at = _utc_datetime(item.get("created_at"))
        normalized_at = _utc_datetime(item.get("normalized_at"))
        if created_at and normalized_at and normalized_at >= created_at:
            durations.append((normalized_at - created_at).total_seconds() / 60)

    local_day = as_of.astimezone(ZoneInfo(DASHBOARD_TIMEZONE)).date()
    standards_overdue = sum(1 for item in standards if standard_availability(item, local_day) == "REVIEW_DUE")
    by_service = Counter(str(item.get("service") or "SIN DATO") for item in created)

    delay_departments = defaultdict(lambda: {"count": 0, "zones": set()})
    for item in current_delays:
        department = str(item.get("department") or "SIN DATO").strip().upper()
        delay_departments[department]["count"] += 1
        zone = str(item.get("zone") or "").strip()
        if zone:
            delay_departments[department]["zones"].add(zone)

    delay_distribution = [
        {"department": department, "count": values["count"], "zones": sorted(values["zones"], key=str.casefold)}
        for department, values in delay_departments.items()
    ]
    delay_distribution.sort(key=lambda item: (-item["count"], item["department"]))

    open_notice_distribution = {status: notices[status] for status in OPEN_NOTICE_STATUSES if notices[status]}
    pending_transfer_distribution = {status: transfers[status] for status in PENDING_TRANSFER_STATUSES if transfers[status]}
    active_total = len(enriched_active)
    normalized_total = len(normalized)

    delay_metrics = {
        "definitions_version": DEFINITIONS_VERSION,
        "as_of": as_of.isoformat(),
        "timezone": DASHBOARD_TIMEZONE,
        "period_days": days,
        "period_start": period_start.isoformat(),
        "delays_created": len(created),
        "delays_normalized": normalized_total,
        "delay_verifications": int(verification_events),
        "delays_expiring_30m": sum(1 for item in current_delays if item["expiring_soon"]),
        # Alias conservados para clientes anteriores del endpoint /api/delay-metrics.
        "created_total": len(created),
        "normalized_total": normalized_total,
        "active_current": len(current_delays),
        "need_review": len(review_delays),
        "expiring_soon": sum(1 for item in current_delays if item["expiring_soon"]),
        "verification_events": int(verification_events),
        "average_resolution_minutes": round(sum(durations) / len(durations), 1) if durations else None,
        "verified_active_percentage": round(100 * len(current_delays) / active_total, 1) if active_total else None,
        "normalized_with_evidence_percentage": round(
            100 * sum(1 for item in normalized if str(item.get("resolution_note") or "").strip()) / normalized_total,
            1,
        ) if normalized_total else None,
        "standards_overdue": standards_overdue,
        "expected_zone_services": int(expected_zone_services),
        "by_service": dict(sorted(by_service.items())),
    }

    return {
        "definitions_version": DEFINITIONS_VERSION,
        "as_of": as_of.isoformat(),
        "timezone": DASHBOARD_TIMEZONE,
        "period_start": period_start.isoformat(),
        "period_days": days,
        "notices_open": sum(notices[status] for status in OPEN_NOTICE_STATUSES),
        "delays_current": len(current_delays),
        "delays_active": len(current_delays),  # Compatibilidad con clientes anteriores.
        "delays_need_review": len(review_delays),
        "transfers_pending": sum(transfers[status] for status in PENDING_TRANSFER_STATUSES),
        "delay_metrics": delay_metrics,
        "distributions": {
            "delays_by_department": delay_distribution,
            "notices_by_status": open_notice_distribution,
            "transfers_by_status": pending_transfer_distribution,
        },
    }
