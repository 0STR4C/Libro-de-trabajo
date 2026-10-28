"""Búsqueda de duplicados con datos sintéticos y sin servicios operativos."""

import sqlite3
import time
import unittest

from app.notices import (
    ensure_notice_duplicate_lookup,
    notice_duplicate_keys,
    notice_duplicate_lock_keys,
    notice_duplicates,
)


class NoticeDuplicateLookupTests(unittest.TestCase):
    def setUp(self):
        self.database = sqlite3.connect(":memory:")
        self.database.row_factory = sqlite3.Row
        self.database.executescript("""
            CREATE TABLE notices (
                id INTEGER PRIMARY KEY,task_number TEXT,phone TEXT,notice_type TEXT,
                managed_by TEXT,status TEXT,created_at TEXT,administratively_retired_at TEXT
            );
            CREATE TABLE schema_migrations (key TEXT PRIMARY KEY,applied_at TEXT,checksum TEXT);
        """)

    def tearDown(self):
        self.database.close()

    def insert(self, task=None, phone=None, notice_type="Consulta", status="PENDIENTE", timestamp="2026-01-01T00:00:00"):
        return self.database.execute(
            "INSERT INTO notices(task_number,phone,notice_type,status,created_at) VALUES(?,?,?,?,?)",
            (task, phone, notice_type, status, timestamp),
        ).lastrowid

    def migrate(self):
        ensure_notice_duplicate_lookup(self.database)

    def test_finds_a_match_older_than_five_thousand_open_notices(self):
        old_id = self.insert(task="  T-OLD  ")
        self.database.executemany(
            "INSERT INTO notices(task_number,notice_type,status,created_at) VALUES(?,?,?,?)",
            ((f"T-{number}", "Consulta", "PENDIENTE", "2026-02-01T00:00:00") for number in range(6000)),
        )
        self.migrate()
        started = time.perf_counter()
        old_scan = self.database.execute("""SELECT * FROM notices
            WHERE status NOT IN ('RESUELTO','CANCELADO') ORDER BY created_at DESC LIMIT 5000""").fetchall()
        old_ms = (time.perf_counter() - started) * 1000
        self.assertEqual(len(old_scan), 5000)
        self.assertNotIn(old_id, [row["id"] for row in old_scan])
        started = time.perf_counter()
        self.assertEqual(notice_duplicates(self.database, {"task_number": "t-old"})[0]["id"], old_id)
        indexed_ms = (time.perf_counter() - started) * 1000
        print(f"duplicados sintéticos (6001 avisos): barrido 5000={old_ms:.2f} ms; consulta indexada={indexed_ms:.2f} ms")
        plan = self.database.execute("""EXPLAIN QUERY PLAN SELECT id FROM notices
            WHERE status NOT IN ('RESUELTO','CANCELADO') AND duplicate_task_key<>'' AND duplicate_task_key=?
            ORDER BY created_at DESC,id DESC LIMIT ?""", ("t-old", 5)).fetchall()
        self.assertTrue(any("notice_open_task_key_idx" in row["detail"] for row in plan))

    def test_phone_format_empty_task_and_terminal_states(self):
        open_id = self.insert(task="", phone="099 123 456", notice_type=" Reclamo ")
        self.insert(task="", phone="099-123-456", notice_type="Reclamo", status="RESUELTO")
        self.insert(task="", phone="099-123-456", notice_type="Reclamo", status="CANCELADO")
        self.migrate()
        self.assertEqual(
            notice_duplicates(self.database, {"task_number": "", "phone": "099-123-456", "notice_type": "reclamo"})[0]["id"],
            open_id,
        )
        self.assertEqual(notice_duplicates(self.database, {"task_number": "", "phone": "12345", "notice_type": "Reclamo"}), [])
        self.assertEqual(notice_duplicates(self.database, {"task_number": "", "phone": "099123456", "notice_type": "Otro"}), [])
        plan = self.database.execute("""EXPLAIN QUERY PLAN SELECT id FROM notices
            WHERE status NOT IN ('RESUELTO','CANCELADO') AND duplicate_phone_key<>'' AND duplicate_phone_key=? AND duplicate_type_key=?
            ORDER BY created_at DESC,id DESC LIMIT ?""", ("099123456", "reclamo", 5)).fetchall()
        self.assertTrue(any("notice_open_phone_type_key_idx" in row["detail"] for row in plan))
        self.assertEqual(notice_duplicate_keys({"task_number": "  STRASSE ", "phone": "０９９ 123-456", "notice_type": "Maße"}),
                         ("strasse", "０９９123456", "masse"))

    def test_migration_is_additive_and_repeatable(self):
        old_id = self.insert(task=" Straße ", phone="０９９-123456", notice_type="Maße")
        self.migrate()
        self.migrate()
        self.assertEqual(notice_duplicates(self.database, {"task_number": "STRASSE"})[0]["id"], old_id)
        self.assertEqual(self.database.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0], 1)

    def test_administrative_retirement_excludes_only_marked_notice(self):
        retired_id = self.insert(task="T-DEMORA", notice_type="Reclamo")
        human_id = self.insert(task="T-HUMANO", notice_type="Reclamo")
        self.database.execute("UPDATE notices SET administratively_retired_at=? WHERE id=?", ("2026-10-16T12:00:00", retired_id))
        self.migrate()
        self.assertEqual(notice_duplicates(self.database, {"task_number": "T-DEMORA"}), [])
        self.assertEqual(notice_duplicates(self.database, {"task_number": "T-HUMANO"})[0]["id"], human_id)

    def test_lock_keys_cover_both_matching_rules_without_a_global_key(self):
        keys = notice_duplicate_lock_keys({"task_number": " A ", "phone": "099 123 456", "notice_type": "Reclamo"})
        self.assertEqual(len(keys), 2)
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(notice_duplicate_lock_keys({"task_number": "", "phone": "12345", "notice_type": "Reclamo"}), [])


if __name__ == "__main__":
    unittest.main()
