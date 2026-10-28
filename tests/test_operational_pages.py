"""Paginación SQL con datos sintéticos y tablas temporales de PostgreSQL."""
import json
import os
import unittest

import psycopg
from psycopg.rows import dict_row

from app.postgres_server import complete_schedules, paged_operational_records, paged_delays


@unittest.skipUnless(os.getenv("DATABASE_URL"), "requiere PostgreSQL")
class OperationalPageTests(unittest.TestCase):
    def test_delays_use_fifty_rows_and_keep_history(self):
        with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as database:
            database.execute("CREATE TEMP TABLE delay_zones AS SELECT * FROM public.delay_zones WHERE FALSE")
            database.execute("""INSERT INTO delay_zones(id,service,department,zone,message,status,agent,created_at,normalized_at)
                SELECT n,'GRÚA','MALDONADO','Zona '||n,'Demora','NORMALIZADO','Prueba',
                    '2026-01-01'::timestamptz + n * interval '1 minute',
                    '2026-01-02'::timestamptz FROM generate_series(1,121) n""")
            pages = [paged_operational_records(database, "delays", {"scope": "normalized"}, offset)
                     for offset in (0, 50, 100)]
            self.assertEqual([len(page["items"]) for page in pages], [50, 50, 21])
            self.assertTrue(all(page["total"] == 121 and page["limit"] == 50 for page in pages))
            self.assertEqual(len({item["id"] for page in pages for item in page["items"]}), 121)
            self.assertEqual(len(paged_operational_records(database, "delays", {"scope": "normalized"}, 0, 100)["items"]), 100)
            self.assertEqual(paged_operational_records(database, "delays", {"department": "ROCHA"})["total"], 0)
            with self.assertRaises(ValueError):
                paged_operational_records(database, "delays", {}, 1)
            with self.assertRaises(ValueError):
                paged_operational_records(database, "delays", {}, 0, 250)

    def test_new_delay_contract_filters_sorts_and_caps_at_fifty(self):
        with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as database:
            database.execute("CREATE TEMP TABLE delay_zones AS SELECT * FROM public.delay_zones WHERE FALSE")
            database.execute("""INSERT INTO delay_zones(id,service,department,zone,message,status,agent,created_at,next_review_at)
                SELECT n,'GRÚA',CASE WHEN n <= 61 THEN 'SALTO' ELSE 'ROCHA' END,
                    'Zona '||n,'A confirmar','VIGENTE','Prueba',
                    '2026-09-01'::timestamptz + n * interval '1 minute',
                    '2099-01-01'::timestamptz FROM generate_series(1,121) n""")
            first=paged_delays(database,{"scope":"current","department":"SALTO"})
            second=paged_delays(database,{"scope":"current","department":"SALTO"},offset=50)
            self.assertEqual((first["total"],len(first["items"]),len(second["items"])),(61,50,11))
            self.assertGreater(first["items"][0]["id"],first["items"][-1]["id"])
            ascending=paged_delays(database,{"department":"SALTO"},sort_order="asc")
            self.assertEqual(ascending["items"][0]["id"],1)
            with self.assertRaises(ValueError):paged_delays(database,{},limit=51)

    def test_historical_published_revisions_show_entire_team(self):
        with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as database:
            for table in ("users", "roles", "work_schedules", "wfm_revisions", "wfm_published_plans", "wfm_published_shifts"):
                database.execute(f"CREATE TEMP TABLE {table} AS SELECT * FROM public.{table} WHERE FALSE")
            shifts = [{"user_id": number, "start": 16, "end": 32,
                       "segments": [{"start": 16, "end": 32}], "break": 24,
                       "break_duration": 1, "overtime_slots": 0, "exceptions": []}
                      for number in range(1, 89)]
            database.execute("""INSERT INTO wfm_revisions
                (plan_date,team,revision,published,payload,actor_id,created_at)
                VALUES ('2026-09-07','Telefonista',1,1,%s,1,'2026-09-06T12:00:00Z')""",
                (json.dumps({"shifts": shifts}),))
            items = complete_schedules(database, {"week": "2026-09-07"})
            self.assertEqual(len(items), 88)
            self.assertEqual(len({item["id"] for item in items}), 88)
            self.assertTrue(all(item["source"] == "wfm" for item in items))


if __name__ == "__main__":
    unittest.main()
