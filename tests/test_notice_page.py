"""Contrato de paginación de avisos con datos sintéticos en una tabla temporal."""
import os
import unittest

import psycopg
from psycopg.rows import dict_row

from app.postgres_server import paged_notices


@unittest.skipUnless(os.getenv("DATABASE_URL"), "requiere PostgreSQL")
class NoticePageTests(unittest.TestCase):
    def test_fifty_rows_total_filters_and_distinct_pages(self):
        with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as database:
            database.execute("""CREATE TEMP TABLE notices (
                id BIGINT, task_number TEXT, phone TEXT, notice_type TEXT, detail TEXT,
                managed_by TEXT, communicated_by TEXT, comments TEXT, status TEXT,
                created_at TIMESTAMPTZ, source_delay_id BIGINT, administratively_retired_at TIMESTAMPTZ)""")
            database.execute("""INSERT INTO notices
                SELECT n, 'T' || n, '099', 'Otro', 'Detalle', NULL, 'Agente', NULL,
                       'PENDIENTE', '2026-01-01'::timestamptz + n * interval '1 minute'
                FROM generate_series(1, 121) AS n""")
            pages = [paged_notices(database, {"scope": "open"}, "Agente", offset)
                     for offset in (0, 50, 100)]
            self.assertEqual([len(page["items"]) for page in pages], [50, 50, 21])
            self.assertTrue(all(page["total"] == 121 and page["limit"] == 50 for page in pages))
            self.assertTrue(all(page["counts"]["unassigned"] == 121 for page in pages))
            self.assertEqual(len({row["id"] for page in pages for row in page["items"]}), 121)
            self.assertEqual(paged_notices(database, {"scope": "mine"}, "Agente")["total"], 0)
            self.assertEqual(paged_notices(database, {"scope": "open", "date_from": "2026-01-02"}, "Agente")["total"], 0)
            self.assertEqual([len(paged_notices(database, {"scope": "open"}, "Agente", 0, limit)["items"]) for limit in (100, 150, 200)], [100, 121, 121])
            database.execute("UPDATE notices SET status='RESUELTO', comments='Caso cerrado' WHERE id=1")
            resolved = paged_notices(database, {"scope": "resolved"}, "Agente")
            self.assertEqual((resolved["total"], resolved["items"][0]["comments"]), (1, "Caso cerrado"))
            with self.assertRaises(ValueError):
                paged_notices(database, {"scope": "open"}, "Agente", 1)
            with self.assertRaises(ValueError):
                paged_notices(database, {"scope": "open"}, "Agente", 0, 250)


if __name__ == "__main__":
    unittest.main()
