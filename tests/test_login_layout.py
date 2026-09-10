import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LoginLayoutRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        cls.javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        cls.styles = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")
        cls.auth_styles = (ROOT / "app" / "static" / "auth.css").read_text(encoding="utf-8")

    def test_password_form_is_the_only_primary_login_content(self):
        self.assertIn("Ingresar a Libro de Trabajo", self.index)
        self.assertIn('id="login-form" class="login-primary-form"', self.index)
        self.assertNotIn("Cuenta corporativa", self.index)
        self.assertNotIn("Acceso alternativo", self.index)
        self.assertNotIn("password-login", self.index)
        self.assertNotIn("google-login-status", self.index)
        self.assertNotIn("accounts.google.com/gsi/client", self.index)
        self.assertNotIn("El ingreso con Google quedará disponible", self.javascript)

    def test_login_does_not_initialize_removed_google_controls(self):
        show_login = self.javascript.split("function showLogin()", 1)[1].split("\n", 1)[0]
        self.assertNotIn("initializeGoogleLogin", show_login)

    def test_password_visibility_uses_proportional_svg_icons(self):
        self.assertIn("function passwordEyeIcon", self.javascript)
        self.assertIn('<circle cx="12" cy="12" r="3"/>', self.javascript)
        self.assertIn('d="m2 2 20 20"', self.javascript)
        self.assertIn(".password-eye svg", self.styles)
        self.assertNotIn(".password-eye:before", self.styles)
        self.assertNotIn(".password-eye:after", self.styles)
        self.assertIn(".login-primary-form", self.auth_styles)


if __name__ == "__main__":
    unittest.main()
