import sqlite3
import unittest

from app.migrations import ensure_sqlite_migration_registry, migration_checksum, reconcile_migration_checksums


class MigrationRegistryTests(unittest.TestCase):
    def database(self):
        database = sqlite3.connect(":memory:")
        database.row_factory = sqlite3.Row
        database.execute("CREATE TABLE schema_migrations(key TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        return database

    def test_registry_upgrade_backfills_checksum_idempotently(self):
        database = self.database()
        database.execute("INSERT INTO schema_migrations(key, applied_at) VALUES('example_v1', 'now')")
        ensure_sqlite_migration_registry(database)
        reconcile_migration_checksums(database, {"example_v1": "CREATE TABLE example(id INTEGER)"})
        expected = migration_checksum("CREATE TABLE example(id INTEGER)")
        self.assertEqual(database.execute("SELECT checksum FROM schema_migrations").fetchone()[0], expected)
        reconcile_migration_checksums(database, {"example_v1": "CREATE TABLE example(id INTEGER)"})

    def test_changed_applied_migration_is_rejected(self):
        database = self.database()
        ensure_sqlite_migration_registry(database)
        database.execute(
            "INSERT INTO schema_migrations(key, applied_at, checksum) VALUES(?, ?, ?)",
            ("example_v1", "now", migration_checksum("original")),
        )
        with self.assertRaisesRegex(RuntimeError, "no coincide"):
            reconcile_migration_checksums(database, {"example_v1": "changed"})


if __name__ == "__main__":
    unittest.main()
