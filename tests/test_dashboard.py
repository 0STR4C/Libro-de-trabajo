import unittest
from datetime import datetime, timedelta, timezone

from app.dashboard import build_dashboard_payload


class DashboardMetricTests(unittest.TestCase):
    def setUp(self):
        self.as_of = datetime(2026, 9, 12, 15, 0, tzinfo=timezone.utc)

    def payload(self, **changes):
        values = {
            "notice_status_counts": [
                {"status": "PENDIENTE", "total": 2},
                {"status": "RESUELTO", "total": 8},
            ],
            "active_delays": [],
            "transfer_status_counts": [
                {"status": "PENDIENTE", "total": 2},
                {"status": "EN_CURSO", "total": 1},
                {"status": "COMPLETADO", "total": 5},
            ],
            "period_delays": [],
            "verification_events": 0,
            "standards": [],
            "expected_zone_services": 0,
            "days": 30,
            "current_time": self.as_of,
        }
        values.update(changes)
        return build_dashboard_payload(**values)

    def test_summary_and_distributions_share_the_same_universe(self):
        result = self.payload()
        self.assertEqual(result["notices_open"], 2)
        self.assertEqual(result["transfers_pending"], 3)
        self.assertEqual(result["distributions"]["notices_by_status"], {"PENDIENTE": 2})
        self.assertEqual(
            result["distributions"]["transfers_by_status"],
            {"SIN_ASIGNAR": 2, "EN_CURSO": 1},
        )

    def test_delay_deadline_uses_the_single_as_of_instant(self):
        result = self.payload(active_delays=[
            {"status": "VIGENTE", "department": "MONTEVIDEO", "zone": "Centro", "expires_at": self.as_of},
            {"status": "VIGENTE", "department": "MONTEVIDEO", "zone": "Cordón", "expires_at": self.as_of + timedelta(minutes=20)},
        ])
        self.assertEqual(result["delays_current"], 1)
        self.assertEqual(result["delays_need_review"], 1)
        self.assertEqual(result["delay_metrics"]["expiring_soon"], 1)
        self.assertEqual(
            result["distributions"]["delays_by_department"],
            [{"department": "MONTEVIDEO", "count": 1, "zones": ["Cordón"]}],
        )

    def test_period_metrics_use_the_date_of_each_event(self):
        before = self.as_of - timedelta(days=40)
        recent = self.as_of - timedelta(days=2)
        result = self.payload(period_delays=[
            {"status": "NORMALIZADO", "created_at": before, "normalized_at": recent, "resolution_note": "Confirmado"},
            {"status": "VIGENTE", "created_at": recent, "normalized_at": None, "service": "GRÚA"},
        ])
        metrics = result["delay_metrics"]
        self.assertEqual(metrics["delays_created"], 1)
        self.assertEqual(metrics["delays_normalized"], 1)
        self.assertEqual(metrics["average_resolution_minutes"], 54720.0)
        self.assertEqual(metrics["normalized_with_evidence_percentage"], 100.0)

    def test_empty_denominators_are_not_reported_as_full_compliance(self):
        metrics = self.payload()["delay_metrics"]
        self.assertIsNone(metrics["verified_active_percentage"])
        self.assertIsNone(metrics["normalized_with_evidence_percentage"])


if __name__ == "__main__":
    unittest.main()
