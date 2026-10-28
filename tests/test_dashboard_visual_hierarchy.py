import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@unittest.skip('Contrato visual histórico de app.js; la interfaz vigente se compila con Vite')
class DashboardVisualHierarchyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        cls.styles = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")
        cls.dashboard_styles = (ROOT / "app" / "static" / "dashboard.css").read_text(encoding="utf-8")
        cls.script = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        cls.frontend = (ROOT / "frontend" / "main.jsx").read_text(encoding="utf-8")
        cls.tailwind = (ROOT / "tailwind.config.js").read_text(encoding="utf-8")

    def test_supervision_is_immediately_before_settings_in_bottom_navigation(self):
        bottom = re.search(r'<div class="sidebar-bottom">(.*?)</aside>', self.index, re.DOTALL)
        self.assertIsNotNone(bottom)
        markup = bottom.group(1)
        supervision = markup.index('data-supervision-menu')
        settings = markup.index('data-page="settings"')
        self.assertLess(supervision, settings)
        self.assertNotIn('data-supervision-menu', self.index[: bottom.start()])

    def test_supervision_chevron_is_right_aligned_and_hidden_when_collapsed(self):
        self.assertIn('.sidebar-section-toggle::after', self.styles)
        self.assertIn('margin-left:auto', self.styles)
        self.assertIn('body.sidebar-collapsed .sidebar-section-toggle::after{display:none}', self.styles)
        self.assertIn('body.sidebar-collapsed .sidebar-section-toggle::after{display:inline-block}', self.styles)
        self.assertNotIn('.sidebar-section-toggle::before', self.styles)

    def test_dashboard_priorities_have_requested_top_down_order(self):
        top = self.script.index("stack.append(top,notices,programmed)")
        self.assertGreaterEqual(top, 0)
        self.assertIn("topSide.append(cards[1],panels[0],panels[1])", self.script)
        self.assertIn("noticeBand.append(cards[0])", self.script)
        self.assertIn("programmedBand.append(cards[2],panels[2])", self.script)
        self.assertIn("target=$('#dashboard-operational-alerts')", self.script)

    def test_dashboard_priority_grid_is_responsive(self):
        for selector in (
            '.dashboard-priority-top',
            '.dashboard-notice-band',
            '.dashboard-programmed-band',
            '@media(max-width:820px)',
            '@media(max-width:760px)',
        ):
            self.assertIn(selector, self.dashboard_styles)

    def test_dashboard_uses_isolated_primereact_cards_and_tailwind(self):
        self.assertIn('id="prime-react-root"', self.index)
        self.assertIn('/static/frontend/prime-react.js?v=7', self.index)
        self.assertIn("<Card", self.frontend)
        self.assertIn("<Tag", self.frontend)
        self.assertIn("tw-p-4", self.frontend)
        self.assertIn("dark:tw-bg-slate-800", self.frontend)
        self.assertIn("prefix: 'tw-'", self.tailwind)
        self.assertIn("darkMode: 'class'", self.tailwind)
        self.assertIn("migrateDashboardVisual", self.script)

    def test_theme_toggle_has_three_persisted_preferences(self):
        self.assertIn('id="theme-toggle-root"', self.index)
        for preference in ("system", "light", "dark"):
            self.assertIn(f"value: '{preference}'", self.frontend)
        self.assertIn("prefers-color-scheme: dark", self.frontend)
        self.assertIn("libro-de-trabajo-theme", self.frontend)

    def test_dashboard_keeps_existing_api_contracts(self):
        self.assertEqual(self.script.count("api('/api/dashboard')"), 1)
        # La misma geometría también alimenta la vista de referencias por zona.
        # La migración visual no debe sumar una tercera descarga para Resumen.
        self.assertEqual(self.script.count("fetch('/uruguay-departamentos.geojson')"), 2)
        self.assertEqual(self.script.count("api('/api/operational-alerts')"), 1)


if __name__ == "__main__":
    unittest.main()
