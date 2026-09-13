import unittest
from datetime import datetime, timezone

from app.reporting import filter_report_records, normalized_report_filters


class ReportFilterTests(unittest.TestCase):
    def test_delay_scopes_distinguish_current_and_review(self):
        rows = [
            {"id": 1, "status": "VIGENTE", "is_current": True, "needs_review": False, "created_at": "2026-09-13T10:00:00+00:00"},
            {"id": 2, "status": "VIGENTE", "is_current": False, "needs_review": True, "created_at": "2026-09-13T11:00:00+00:00"},
        ]
        self.assertEqual([item["id"] for item in filter_report_records("delays", rows, {"scope": "current"})], [1])
        self.assertEqual([item["id"] for item in filter_report_records("delays", rows, {"scope": "review"})], [2])

    def test_notice_mine_uses_authenticated_identity(self):
        filters = normalized_report_filters("notices", {"scope": "mine", "managed_by": "Otra persona"}, managed_by="Ana")
        self.assertEqual(filters["managed_by"], "Ana")

    def test_quote_filters_are_reusable_for_export(self):
        rows = [
            {"id": 1, "created_at": "2026-09-13T12:00:00+00:00", "uninsured": False, "origin_input": "Cotización manual", "created_by": "Ana"},
            {"id": 2, "created_at": "2026-09-13T13:00:00+00:00", "uninsured": True, "origin_input": "Montevideo", "created_by": "Luis"},
        ]
        result = filter_report_records("quotes", rows, {"coverage": "insured", "mode": "manual"})
        self.assertEqual([item["id"] for item in result], [1])

    def test_timestamp_date_filters_use_montevideo_day(self):
        rows = [{"id": 1, "created_at": datetime(2026, 9, 13, 1, 30, tzinfo=timezone.utc), "entity": "notice"}]
        self.assertEqual(filter_report_records("audit", rows, {"date_to": "2026-09-12"})[0]["id"], 1)

    def test_scheduled_date_is_not_shifted_as_a_timestamp(self):
        rows=[{"id":1,"scheduled_date":"2026-09-13","status":"PENDIENTE"}]
        result=filter_report_records("transfers",rows,{"date_from":"2026-09-13","date_to":"2026-09-13"})
        self.assertEqual(result[0]["status"],"SIN_ASIGNAR")


if __name__ == "__main__":
    unittest.main()
