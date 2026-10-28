import unittest
import sqlite3
from datetime import date, datetime, timedelta, timezone

from app.delays import clean_delay, clean_standard, enrich_delay, normalized_key, split_zones, standard_availability, zone_matches
from app.geography import ALL_DEPARTMENT, URUGUAY_ZONES, geography_payload
from app.local_server import paged_delays


class DelayRulesTests(unittest.TestCase):
    def test_geography_covers_all_departments_and_defaults_to_whole_department(self):
        catalog = geography_payload()
        self.assertEqual(len(catalog), 19)
        self.assertEqual(set(catalog), set(URUGUAY_ZONES))
        self.assertTrue(all(zones[0] == ALL_DEPARTMENT and len(zones) > 1 for zones in catalog.values()))

    def test_catalog_zone_cannot_belong_to_another_department(self):
        base = {"service": "GRÚA", "department": "SALTO", "zone": "Pocitos", "message": "A confirmar", "catalog_zone": True}
        with self.assertRaisesRegex(ValueError, "Zona inválido"):
            clean_delay(base)
        valid = clean_delay({**base, "zone": ALL_DEPARTMENT, "duration_minutes": 30})
        self.assertEqual(valid["review_minutes"], 30)
        self.assertEqual(valid["duration_minutes"], 30)

    def test_explicit_next_review_takes_precedence_over_legacy_expiry(self):
        current = datetime(2026, 9, 11, 15, 0, tzinfo=timezone.utc)
        item = enrich_delay({"status": "VIGENTE", "expires_at": current + timedelta(hours=2), "next_review_at": current}, current)
        self.assertTrue(item["needs_review"])
        self.assertEqual(item["review_due_at"], current.isoformat())

    def test_sqlite_delay_page_filters_and_limits_in_database(self):
        database = sqlite3.connect(":memory:")
        database.row_factory = sqlite3.Row
        try:
            database.execute("CREATE TABLE delay_zones (id INTEGER PRIMARY KEY,service TEXT,department TEXT,zone TEXT,message TEXT,status TEXT,agent TEXT,created_at TEXT,next_review_at TEXT)")
            database.executemany("INSERT INTO delay_zones VALUES (?,?,?,?,?,?,?,?,?)", [
                (number, "GRÚA", "SALTO" if number <= 61 else "ROCHA", f"Zona {number}", "A confirmar", "VIGENTE", "Prueba", f"2026-09-01T00:{number % 60:02d}:00+00:00", "2099-01-01T00:00:00+00:00")
                for number in range(1, 122)
            ])
            page = paged_delays(database, {"department": "SALTO", "limit": "50", "offset": "50"})
            self.assertEqual((page["total"], len(page["items"]), page["limit"]), (61, 11, 50))
            with self.assertRaises(ValueError):paged_delays(database, {"limit": "51"})
        finally:
            database.close()

    def test_delay_normalizes_catalog_values_and_whitespace(self):
        item = clean_delay({
            "service": "grua",
            "department": "montevideo",
            "zone": "  Centro   y Cordón ",
            "message": "margen de",
            "minutes": 45,
            "status": "VIGENTE",
        })
        self.assertEqual(item["service"], "GRÚA")
        self.assertEqual(item["department"], "MONTEVIDEO")
        self.assertEqual(item["zone"], "Centro y Cordón")

    def test_delay_rejects_minutes_without_margin(self):
        with self.assertRaisesRegex(ValueError, "minutos solo corresponden"):
            clean_delay({"service": "ML", "department": "SALTO", "zone": "Centro", "message": "A confirmar", "minutes": 30})

    def test_delay_requires_margin_minutes(self):
        with self.assertRaisesRegex(ValueError, "margen entre"):
            clean_delay({"service": "ML", "department": "SALTO", "zone": "Centro", "message": "Margen de", "minutes": None})

    def test_confirmed_standard_requires_source_and_time(self):
        base = {"department": "SALTO", "zone": "Centro", "service": "ML", "status": "CONFIRMADO"}
        with self.assertRaisesRegex(ValueError, "informar un tiempo"):
            clean_standard(base)
        with self.assertRaisesRegex(ValueError, "indicar su fuente"):
            clean_standard({**base, "minutes_max": 45})

    def test_standard_rejects_reversed_review_window(self):
        with self.assertRaisesRegex(ValueError, "revisión no puede"):
            clean_standard({
                "department": "SALTO", "zone": "Centro", "service": "ML",
                "status": "PROVISIONAL", "effective_from": date(2026, 9, 10),
                "review_due_at": date(2026, 9, 9),
            })

    def test_zone_match_is_exact_or_comma_delimited(self):
        self.assertTrue(zone_matches(ALL_DEPARTMENT, "Pocitos"))
        self.assertTrue(zone_matches("Centro, Parque Rodó", "parque rodo"))
        self.assertFalse(zone_matches("Centro ampliado", "Centro"))
        self.assertEqual(normalized_key(" RÍO  Negro "), "rio negro")
        self.assertEqual(split_zones("Centro, Parque Rodó, Cordón"), ["Centro", "Parque Rodó", "Cordón"])

    def test_standard_assigns_owner_and_computes_review_cycle(self):
        item=clean_standard({
            "department":"SALTO","zone":"Centro","service":"ML","status":"PROVISIONAL",
            "effective_from":date(2026,9,11),"owner":" Mesa Norte ","review_interval_days":30,
        })
        self.assertEqual(item["owner"],"Mesa Norte")
        self.assertEqual(item["review_interval_days"],30)
        self.assertEqual(item["review_due_at"],date(2026,10,11))

    def test_delay_stops_being_current_when_review_expires(self):
        current=datetime(2026,9,11,15,0,tzinfo=timezone.utc)
        fresh=enrich_delay({"status":"VIGENTE","expires_at":current+timedelta(minutes=1)},current)
        stale=enrich_delay({"status":"VIGENTE","expires_at":current},current)
        self.assertTrue(fresh["is_current"])
        self.assertTrue(stale["needs_review"])

    def test_only_confirmed_effective_reviewed_standard_is_current(self):
        base={"active":True,"status":"CONFIRMADO","effective_from":"2026-09-01","review_due_at":"2026-09-30"}
        self.assertEqual(standard_availability(base,date(2026,9,11)),"CURRENT")
        self.assertEqual(standard_availability({**base,"status":"PROVISIONAL"},date(2026,9,11)),"PROVISIONAL")
        self.assertEqual(standard_availability({**base,"review_due_at":"2026-09-10"},date(2026,9,11)),"REVIEW_DUE")


if __name__ == "__main__":
    unittest.main()
