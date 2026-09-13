import unittest
from pathlib import Path

from app.local_server import APP_VERSION
from app.releases import parse_release_history, release_payload


ROOT = Path(__file__).resolve().parents[1]


class ReleaseHistoryTests(unittest.TestCase):
    def test_parser_preserves_versions_dates_titles_and_notes(self):
        history = parse_release_history(
            """# Registro\n\n## 2.0.0 — 13 de septiembre de 2026 (Entrega mayor)\n\n- Primer cambio.\n- Segundo cambio.\n\n## 1.0.0 — 1 de enero de 2026\n\n- Inicio.\n"""
        )
        self.assertEqual([item["version"] for item in history], ["2.0.0", "1.0.0"])
        self.assertEqual(history[0]["released"], "2026-09-13")
        self.assertEqual(history[0]["title"], "Entrega mayor")
        self.assertEqual(history[0]["notes"], ["Primer cambio.", "Segundo cambio."])

    def test_project_changelog_contains_current_and_first_release(self):
        payload = release_payload(APP_VERSION, "fallback", [], ROOT / "CHANGELOG.md")
        versions = [item["version"] for item in payload["releases"]]
        self.assertEqual(payload["version"], APP_VERSION)
        self.assertEqual(versions[0], APP_VERSION)
        self.assertIn("1.0.0", versions)
        self.assertEqual(len(versions), len(set(versions)))
        self.assertTrue(all(item["notes"] for item in payload["releases"]))

    def test_missing_changelog_keeps_a_safe_current_release(self):
        payload = release_payload("9.9.9", "2026-09-13", ["Cambio local"], ROOT / "missing-changelog.md")
        self.assertEqual(payload["notes"], ["Cambio local"])
        self.assertEqual(payload["releases"][0]["version"], "9.9.9")


if __name__ == "__main__":
    unittest.main()
