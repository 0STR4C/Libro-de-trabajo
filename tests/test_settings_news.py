import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SettingsNewsLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        cls.styles = (ROOT / "app" / "static" / "settings.css").read_text(encoding="utf-8")

    def test_settings_has_a_dedicated_complete_news_tab(self):
        self.assertIn("selectSettingsTab('news')\">Novedades", self.javascript)
        self.assertIn("Array.isArray(version.releases)", self.javascript)
        self.assertIn('class="release-history"', self.javascript)
        self.assertIn('class="panel release-entry"', self.javascript)

    def test_release_history_is_responsive(self):
        self.assertIn(".release-history", self.styles)
        self.assertIn(".release-entry summary", self.styles)
        self.assertIn("@media(max-width:650px)", self.styles)


if __name__ == "__main__":
    unittest.main()
