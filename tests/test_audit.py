import json
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app import local_server


class AuditContractTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix="libro-trabajo-audit-")
        self.previous_db = local_server.DB_PATH
        local_server.DB_PATH = Path(self.directory.name) / "audit.db"
        local_server.initialize()

    def tearDown(self):
        local_server.DB_PATH = self.previous_db
        self.directory.cleanup()

    def test_actor_record_and_changes_can_be_reconstructed(self):
        with local_server.connect() as database:
            actor = database.execute("SELECT id,display_name FROM users WHERE username='admin'").fetchone()
            stamp = local_server.now()
            notice_id = database.execute(
                """INSERT INTO notices(notice_type,audience,detail,communicated_by,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?)""",
                ("Prueba", "TODOS", "Detalle inicial", actor["display_name"], "PENDIENTE", stamp, stamp),
            ).lastrowid
            created = database.execute("SELECT * FROM notices WHERE id=?", (notice_id,)).fetchone()
            local_server.audit(database, "notice", notice_id, "CREADO", actor["display_name"], actor_id=actor["id"], after=created)
            database.execute("UPDATE notices SET status='RESUELTO',detail='Detalle final' WHERE id=?", (notice_id,))
            updated = database.execute("SELECT * FROM notices WHERE id=?", (notice_id,)).fetchone()
            local_server.audit(database, "notice", notice_id, "AVISO_ACTUALIZADO", actor["display_name"], actor_id=actor["id"], after=updated)
            event = database.execute("SELECT * FROM audit_events WHERE entity='notice' AND entity_id=? ORDER BY id DESC LIMIT 1", (notice_id,)).fetchone()
        before = json.loads(event["before_data"])
        after = json.loads(event["after_data"])
        self.assertEqual(event["actor_id"], actor["id"])
        self.assertEqual(event["actor_name"], actor["display_name"])
        self.assertEqual((before["status"], after["status"]), ("PENDIENTE", "RESUELTO"))
        self.assertEqual((before["detail"], after["detail"]), ("Detalle inicial", "Detalle final"))
        self.assertTrue(event["correlation_id"])
        self.assertEqual(event["source"], "web")

    def test_sensitive_fields_are_excluded_from_snapshots(self):
        with local_server.connect() as database:
            local_server.audit(
                database, "user", 999, "ACTUALIZADO", "Administrador",
                before={"display_name": "A", "password_hash": "no-debe-salir"},
                after={"display_name": "B", "token": "no-debe-salir"},
            )
            event = database.execute("SELECT before_data,after_data FROM audit_events ORDER BY id DESC LIMIT 1").fetchone()
        self.assertNotIn("password_hash", json.loads(event["before_data"]))
        self.assertNotIn("token", json.loads(event["after_data"]))

    def test_audit_events_cannot_be_updated_or_deleted(self):
        with local_server.connect() as database:
            local_server.audit(database, "notice", 123, "CREADO", "Administrador")
        for statement in ("UPDATE audit_events SET detail='alterado'", "DELETE FROM audit_events"):
            with self.assertRaisesRegex(sqlite3.IntegrityError, "inmutable"):
                with local_server.connect() as database:
                    database.execute(statement)


if __name__ == "__main__":
    unittest.main()
