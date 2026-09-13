import ast
from pathlib import Path
import unittest


class ServerBoundaryTests(unittest.TestCase):
    def test_postgres_adapter_does_not_import_sqlite_server(self):
        source_path = Path(__file__).resolve().parents[1] / "app" / "postgres_server.py"
        module = ast.parse(source_path.read_text(encoding="utf-8"))
        imported_modules = {
            node.module
            for node in ast.walk(module)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        self.assertNotIn("local_server", imported_modules)
        self.assertNotIn("app.local_server", imported_modules)


if __name__ == "__main__":
    unittest.main()
