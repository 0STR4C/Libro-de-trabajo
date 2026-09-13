import hashlib
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.sqlite_to_postgres.migration_core import OPTIONAL_TABLES, TABLES, counts, load_sqlite


class MigrationSourceTests(unittest.TestCase):
    def test_source_is_read_only_and_all_tables_are_loaded(self):
        with TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "source.db"
            with closing(sqlite3.connect(source)) as database:
                for table in TABLES:
                    if table == "role_permissions":
                        database.execute("CREATE TABLE role_permissions(role_id INTEGER, permission TEXT)")
                        database.execute("INSERT INTO role_permissions VALUES(1,'dashboard.view')")
                    elif table == "users":
                        database.execute("CREATE TABLE users(id INTEGER, active INTEGER)")
                        database.execute("INSERT INTO users VALUES(1,1)")
                    elif table == "quotes":
                        database.execute("CREATE TABLE quotes(id INTEGER, uninsured INTEGER, special INTEGER, gavilan INTEGER)")
                        database.execute("INSERT INTO quotes VALUES(1,0,1,0)")
                    else:
                        database.execute(f"CREATE TABLE {table}(id INTEGER)")
                        database.execute(f"INSERT INTO {table} VALUES(1)")
                database.commit()
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            dataset = load_sqlite(source)
            after = hashlib.sha256(source.read_bytes()).hexdigest()
            self.assertEqual(before, after)
            self.assertEqual(set(dataset), set(TABLES))
            self.assertTrue(dataset["users"]["rows"][0]["active"])
            self.assertTrue(dataset["quotes"]["rows"][0]["special"])
            self.assertTrue(all(total == 1 for total in counts(dataset).values()))

    def test_legacy_source_keeps_new_tables_explicitly_empty(self):
        with TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "legacy.db"
            with closing(sqlite3.connect(source)) as database:
                for table in TABLES:
                    if table in OPTIONAL_TABLES:
                        continue
                    database.execute(f"CREATE TABLE {table}(id INTEGER)")
                database.commit()
            dataset = load_sqlite(source)
            self.assertTrue(all(dataset[table]["rows"] == [] for table in OPTIONAL_TABLES))
            self.assertEqual(set(dataset), set(TABLES))


if __name__ == "__main__":
    unittest.main()
