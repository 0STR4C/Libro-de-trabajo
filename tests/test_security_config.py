import hashlib
import importlib.util
import os
import subprocess
import sys
import unittest

from app.security import RateLimitState, hash_password, next_rate_limit_state, password_needs_rehash, validate_runtime_environment, verify_password


class RuntimeSecurityConfigTests(unittest.TestCase):
    def valid_production(self):
        return {
            "APP_ENV": "production",
            "APP_SECRET": "a9f3c8e7b6d54120A9f3c8e7b6d54120",
            "POSTGRES_PASSWORD": "db-a9f3c8e7b6d54120",
            "ADMIN_PASSWORD": "admin-a9f3C8e7",
            "PUBLIC_BASE_URL": "https://centro.interno.example",
            "ALLOWED_ORIGINS": "https://centro.interno.example",
            "ALLOWED_HOSTS": "centro.interno.example",
        }

    def test_development_accepts_local_defaults(self):
        result = validate_runtime_environment({})
        self.assertEqual(result.app_env, "development")

    def test_production_rejects_missing_or_default_secrets(self):
        for name in ("APP_SECRET", "POSTGRES_PASSWORD", "ADMIN_PASSWORD"):
            environment = self.valid_production()
            environment[name] = ""
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                validate_runtime_environment(environment)

        environment = self.valid_production()
        environment["APP_SECRET"] = "desarrollo-no-usar-en-produccion"
        with self.assertRaises(RuntimeError):
            validate_runtime_environment(environment)

    def test_production_rejects_short_values(self):
        limits = {"APP_SECRET": "short", "POSTGRES_PASSWORD": "short", "ADMIN_PASSWORD": "short"}
        for name, value in limits.items():
            environment = self.valid_production()
            environment[name] = value
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                validate_runtime_environment(environment)

        environment = self.valid_production()
        environment["APP_SECRET"] = "a" * 32
        with self.assertRaises(RuntimeError):
            validate_runtime_environment(environment)

    def test_production_accepts_non_default_values(self):
        result = validate_runtime_environment(self.valid_production())
        self.assertEqual(result.app_env, "production")
        self.assertEqual(result.public_base_url, "https://centro.interno.example")

    def test_production_requires_an_https_public_url(self):
        for invalid_url in ("", "http://centro.interno.example", "https://", "https://usuario:clave@centro.interno.example"):
            environment = self.valid_production()
            environment["PUBLIC_BASE_URL"] = invalid_url
            with self.subTest(public_base_url=invalid_url), self.assertRaises(RuntimeError):
                validate_runtime_environment(environment)

    def test_production_requires_public_url_in_allowed_hosts_and_origins(self):
        environment = self.valid_production()
        environment["ALLOWED_ORIGINS"] = "https://otro.interno.example"
        with self.assertRaisesRegex(RuntimeError, "ALLOWED_ORIGINS"):
            validate_runtime_environment(environment)
        environment = self.valid_production()
        environment["ALLOWED_HOSTS"] = "otro.interno.example"
        with self.assertRaisesRegex(RuntimeError, "ALLOWED_HOSTS"):
            validate_runtime_environment(environment)

    def test_unknown_environment_is_rejected(self):
        with self.assertRaises(RuntimeError):
            validate_runtime_environment({"APP_ENV": "staging"})


class PasswordHashTests(unittest.TestCase):
    def test_new_passwords_use_argon2id_without_truncation(self):
        first = "a" * 100 + "x"
        second = "a" * 100 + "y"
        stored = hash_password(first)
        self.assertTrue(stored.startswith("$argon2id$"))
        self.assertTrue(verify_password(first, stored))
        self.assertFalse(verify_password(second, stored))
        self.assertFalse(password_needs_rehash(stored))

    def test_legacy_pbkdf2_remains_compatible_and_requests_rehash(self):
        password = "clave histórica suficientemente larga"
        salt = "0123456789abcdef0123456789abcdef"
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200000).hex()
        stored = f"{salt}${digest}"
        self.assertTrue(verify_password(password, stored))
        self.assertFalse(verify_password(password + "x", stored))
        self.assertTrue(password_needs_rehash(stored))


class RateLimitTests(unittest.TestCase):
    def test_fifth_failure_blocks_and_wait_grows_progressively(self):
        state = None
        for offset in range(4):
            state = next_rate_limit_state(state, 1000 + offset)
            self.assertEqual(state.blocked_until, 0)
        state = next_rate_limit_state(state, 1004)
        self.assertEqual(state.failures, 5)
        self.assertEqual(state.blocked_until, 1064)
        state = next_rate_limit_state(state, 1064)
        self.assertEqual(state.blocked_until, 1184)

    def test_window_expiration_resets_failures(self):
        previous = RateLimitState(8, 1000, 0)
        state = next_rate_limit_state(previous, 1901)
        self.assertEqual(state.failures, 1)
        self.assertEqual(state.blocked_until, 0)


class FastApiSecurityConfigTests(unittest.TestCase):
    def test_production_disables_api_docs_without_starting_database(self):
        if importlib.util.find_spec("psycopg") is None:
            self.skipTest("requiere las dependencias del contenedor Docker")
        environment = os.environ.copy()
        environment.update(
            {
                "APP_ENV": "production",
                "APP_SECRET": "a9f3c8e7b6d54120A9f3c8e7b6d54120",
                "POSTGRES_PASSWORD": "db-a9f3c8e7b6d54120",
                "ADMIN_PASSWORD": "admin-a9f3C8e7",
                "PUBLIC_BASE_URL": "https://centro.interno.example",
                "ALLOWED_ORIGINS": "https://centro.interno.example",
                "ALLOWED_HOSTS": "centro.interno.example",
                "ENABLE_API_DOCS": "false",
            }
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", "from app import postgres_server as s; from fastapi.responses import Response; response=Response(); s.set_auth_cookies(response, 'token'); assert s.app.openapi_url is None; assert all('Secure' in value for value in response.headers.getlist('set-cookie')); print('ok')"],
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), "ok")


if __name__ == "__main__":
    unittest.main()
