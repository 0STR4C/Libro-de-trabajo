import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AccessibleLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
        cls.javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
        cls.styles = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")

    def test_navigation_has_landmarks_skip_link_and_mobile_controls(self):
        self.assertIn('class="skip-link" href="#content"', self.html)
        self.assertIn('aria-label="Navegación principal"', self.html)
        self.assertIn('id="mobile-nav-toggle"', self.html)
        self.assertIn("setMobileNavigation", self.javascript)
        self.assertIn("event.key==='Escape'", self.javascript)

    def test_tables_keep_column_meaning_on_small_screens(self):
        self.assertIn('class="panel table-scroll responsive-table"', self.javascript)
        self.assertIn('scope="col"', self.javascript)
        self.assertIn('data-label=', self.javascript)
        self.assertIn('content:attr(data-label)', self.styles)

    def test_forms_and_messages_expose_accessible_state(self):
        self.assertIn('id="form-error"', self.html)
        self.assertIn('role="status" aria-live="polite"', self.html)
        self.assertIn("enhanceFormLabels", self.javascript)
        self.assertIn("aria-required", self.javascript)
        self.assertIn("aria-invalid", self.javascript)
        self.assertIn("data-original-text", self.javascript.replace("dataset.originalText", "data-original-text"))
        self.assertIn("Guardando…", self.javascript)
        self.assertIn("prefers-reduced-motion", self.styles)


if __name__ == "__main__":
    unittest.main()
