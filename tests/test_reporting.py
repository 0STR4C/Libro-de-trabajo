import csv
import io
import unittest

from app.reporting import NOTICE_REPORT_COLUMNS, REPORT_COLUMNS, notice_csv_bytes, report_csv_bytes


class NoticeReportTests(unittest.TestCase):
    def test_csv_has_descriptive_columns_and_excel_safe_values(self):
        content = notice_csv_bytes([{"task_number": "=1+1", "phone": "099123456", "notice_type": "Consulta"}])
        self.assertTrue(content.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(rows[0], [label for label, _field in NOTICE_REPORT_COLUMNS])
        task_column = [field for _label, field in NOTICE_REPORT_COLUMNS].index("task_number")
        self.assertEqual(rows[1][task_column], "'=1+1")

    def test_every_operational_report_has_headers(self):
        for kind, columns in REPORT_COLUMNS.items():
            rows = list(csv.reader(io.StringIO(report_csv_bytes(kind, []).decode("utf-8-sig")), delimiter=";"))
            self.assertEqual(rows[0], [label for label, _field in columns])
