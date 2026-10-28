"""Carreras de Avisos sobre PostgreSQL efímero, nunca sobre la base operativa."""

import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi import HTTPException


@unittest.skipUnless(os.getenv("SECURITY_TEST_DATABASE_URL"), "requiere PostgreSQL aislado")
class NoticeConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["DATABASE_URL"] = os.environ["SECURITY_TEST_DATABASE_URL"]
        os.environ.setdefault("APP_ENV", "development")
        os.environ.setdefault("APP_SECRET", "test-app-secret-notices-only-1234567890")
        os.environ.setdefault("ADMIN_PASSWORD", "test-admin-notices-only")
        from app import postgres_server

        cls.server = postgres_server
        cls.server.initialize()
        with cls.server.connect() as database:
            actor = database.execute("SELECT id,display_name FROM users WHERE username=%s", ("admin",)).fetchone()
        cls.actor = {**actor, "permissions": {
            "notices.create", "notices.view", "notices.assign", "notices.comment",
            "notices.change_status", "notices.close",
        }}
        cls.original_authorized = cls.server.authorized
        cls.original_current_user = cls.server.current_user
        cls.server.authorized = lambda request, permission: cls.actor
        cls.server.current_user = lambda request: cls.actor

    @classmethod
    def tearDownClass(cls):
        cls.server.authorized = cls.original_authorized
        cls.server.current_user = cls.original_current_user

    def create(self, **changes):
        payload = {"task_number": f"synthetic-{uuid4().hex}", "notice_type": "Consulta", "detail": "Caso sintético", **changes}
        return self.server.create_item("notices", None, payload)

    def update(self, item_id, revision, **changes):
        return self.server.notice_status(item_id, None, self.server.NoticeUpdateIn(expected_revision=revision, **changes))

    def test_equivalent_simultaneous_creates_do_not_both_pass(self):
        task = f"race-{uuid4().hex}"
        barrier = threading.Barrier(2)

        def create_at_once():
            barrier.wait(timeout=5)
            try:
                return ("created", self.create(task_number=task)["id"])
            except HTTPException as error:
                return (error.status_code, error.detail)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: create_at_once(), range(2)))
        self.assertEqual(sorted(result[0] for result in results if isinstance(result[0], int)), [409])
        self.assertEqual(sum(result[0] == "created" for result in results), 1)
        with self.server.connect() as database:
            count = database.execute("SELECT count(*) AS total FROM notices WHERE duplicate_task_key=%s", (task,)).fetchone()["total"]
        self.assertEqual(count, 1)

    def test_phone_format_race_uses_the_same_lock(self):
        phone = f"099{uuid4().int % 1000000:06d}"
        barrier = threading.Barrier(2)

        def create_at_once(formatted_phone):
            barrier.wait(timeout=5)
            try:
                return ("created", self.create(task_number="", phone=formatted_phone, notice_type="Reclamo")["id"])
            except HTTPException as error:
                return (error.status_code, error.detail)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(create_at_once, (phone, f"{phone[:3]} {phone[3:]}")))
        self.assertEqual(sum(result[0] == "created" for result in results), 1)
        self.assertEqual(sum(result[0] == 409 for result in results), 1)

    def test_postgres_finds_duplicate_older_than_five_thousand(self):
        old = self.create(task_number=f"old-{uuid4().hex}")
        with self.server.connect() as database:
            database.execute("""INSERT INTO notices(
                task_number,notice_type,audience,detail,communicated_by,status,
                created_at,updated_at,duplicate_task_key,duplicate_type_key)
                SELECT 'synthetic-filler-' || g::text,'Consulta','TODOS','Caso sintético',
                    'Prueba','PENDIENTE',now() + interval '1 day',now() + interval '1 day',
                    'synthetic-filler-' || g::text,'consulta'
                FROM generate_series(1,6000) AS g""")
            from app.notices import notice_duplicates
            matches = notice_duplicates(database, {"task_number": old["task_number"]}, postgres=True)
        self.assertEqual(matches[0]["id"], old["id"])

    def test_comment_conflicting_with_close_keeps_draft_out_of_database(self):
        notice = self.create()
        closed = self.update(notice["id"], notice["revision"], status="RESUELTO", comments="Cierre vigente")
        with self.assertRaises(HTTPException) as conflict:
            self.update(notice["id"], notice["revision"], comments="Borrador de seguimiento")
        self.assertEqual(conflict.exception.status_code, 409)
        with self.server.connect() as database:
            current = database.execute("SELECT status,comments,revision FROM notices WHERE id=%s", (notice["id"],)).fetchone()
        self.assertEqual((current["status"], current["comments"], current["revision"]),
                         ("RESUELTO", "Cierre vigente", closed["revision"]))
        continued = self.update(notice["id"], current["revision"], comments="Borrador de seguimiento")
        self.assertEqual((continued["status"], continued["comments"]), ("RESUELTO", "Borrador de seguimiento"))

    def test_reassignment_conflict_preserves_unrelated_fields(self):
        notice = self.create()
        commented = self.update(notice["id"], notice["revision"], comments="Seguimiento vigente")
        with self.assertRaises(HTTPException) as conflict:
            self.update(notice["id"], notice["revision"], managed_by=self.actor["display_name"])
        self.assertEqual(conflict.exception.status_code, 409)
        assigned = self.update(notice["id"], commented["revision"], managed_by=self.actor["display_name"])
        self.assertEqual(assigned["comments"], "Seguimiento vigente")
        self.assertEqual(assigned["status"], "PENDIENTE")
        self.assertEqual(assigned["managed_by"], self.actor["display_name"])

    def test_comment_assignment_and_close_change_only_requested_fields(self):
        notice = self.create()
        assigned = self.update(notice["id"], notice["revision"], managed_by=self.actor["display_name"])
        self.assertEqual((assigned["status"], assigned["comments"]), ("PENDIENTE", None))
        commented = self.update(notice["id"], assigned["revision"], comments="Seguimiento")
        self.assertEqual((commented["status"], commented["managed_by"]),
                         ("PENDIENTE", self.actor["display_name"]))
        closed = self.update(notice["id"], commented["revision"], status="RESUELTO", comments="Cerrado")
        self.assertEqual(closed["managed_by"], self.actor["display_name"])
        self.assertEqual((closed["status"], closed["comments"]), ("RESUELTO", "Cerrado"))


if __name__ == "__main__":
    unittest.main()
