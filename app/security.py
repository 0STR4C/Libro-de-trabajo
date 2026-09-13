"""Configuración de seguridad común para los modos Docker de Centro Operativo."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import secrets
from typing import Mapping
from urllib.parse import urlparse

from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id


VALID_APP_ENVS = {"development", "production"}
WEAK_VALUES = {
    "",
    "operativa",
    "admin1234",
    "cambiar-esta-clave",
    "cambiar-por-un-secreto-largo",
    "desarrollo-no-usar-en-produccion",
    "password",
    "changeme",
    "secret",
}
ARGON2_MEMORY_KIB = 64 * 1024
ARGON2_ITERATIONS = 3
ARGON2_LANES = 4
ARGON2_LENGTH = 32
SESSION_COOKIE_NAME = "centro_session"
CSRF_COOKIE_NAME = "centro_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"


@dataclass(frozen=True)
class RuntimeSecurityConfig:
    app_env: str
    app_secret: str
    postgres_password: str
    admin_password: str
    public_base_url: str


@dataclass(frozen=True)
class RateLimitState:
    failures: int
    window_started_at: float
    blocked_until: float


def _is_marker(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in WEAK_VALUES or normalized.startswith("<") or "cambiar" in normalized


def _require_secure(name: str, value: str, minimum_bytes: int) -> None:
    low_diversity = len(set(value)) < min(8, minimum_bytes // 2) or (value and value == value[0] * len(value))
    if _is_marker(value) or len(value.encode("utf-8")) < minimum_bytes or low_diversity:
        raise RuntimeError(
            f"Configuración de producción inválida: {name} está ausente, es predeterminado o no alcanza {minimum_bytes} bytes."
        )


def validate_runtime_environment(environment: Mapping[str, str]) -> RuntimeSecurityConfig:
    app_env = environment.get("APP_ENV", "development").strip().lower()
    if app_env not in VALID_APP_ENVS:
        raise RuntimeError("APP_ENV debe ser development o production.")

    config = RuntimeSecurityConfig(
        app_env=app_env,
        app_secret=environment.get("APP_SECRET", "desarrollo-no-usar-en-produccion"),
        postgres_password=environment.get("POSTGRES_PASSWORD", "operativa"),
        admin_password=environment.get("ADMIN_PASSWORD", "admin1234"),
        public_base_url=environment.get("PUBLIC_BASE_URL", "http://localhost:8000").strip().rstrip("/"),
    )
    if app_env == "production":
        _require_secure("APP_SECRET", config.app_secret, 32)
        _require_secure("POSTGRES_PASSWORD", config.postgres_password, 16)
        _require_secure("ADMIN_PASSWORD", config.admin_password, 12)
        public_url = urlparse(config.public_base_url)
        if public_url.scheme != "https" or not public_url.netloc or public_url.username or public_url.password:
            raise RuntimeError(
                "Configuración de producción inválida: PUBLIC_BASE_URL debe ser una URL pública https:// sin credenciales."
            )
        allowed_origins = {
            item.strip().rstrip("/")
            for item in environment.get("ALLOWED_ORIGINS", "").split(",")
            if item.strip()
        }
        if config.public_base_url not in allowed_origins:
            raise RuntimeError("Configuración de producción inválida: PUBLIC_BASE_URL debe estar incluida en ALLOWED_ORIGINS.")
        allowed_hosts = {item.strip().lower() for item in environment.get("ALLOWED_HOSTS", "").split(",") if item.strip()}
        if not public_url.hostname or public_url.hostname.lower() not in allowed_hosts:
            raise RuntimeError("Configuración de producción inválida: el host de PUBLIC_BASE_URL debe estar incluido en ALLOWED_HOSTS.")
    return config


def hash_password(password: str) -> str:
    """Crea un hash PHC Argon2id; nunca recorta la contraseña recibida."""
    password_bytes = str(password).encode("utf-8")
    return Argon2id(
        salt=secrets.token_bytes(16),
        length=ARGON2_LENGTH,
        iterations=ARGON2_ITERATIONS,
        lanes=ARGON2_LANES,
        memory_cost=ARGON2_MEMORY_KIB,
    ).derive_phc_encoded(password_bytes)


def _verify_legacy_pbkdf2(password: str, stored: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
        if not salt or not expected:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200000).hex()
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("$argon2id$"):
        try:
            Argon2id.verify_phc_encoded(str(password).encode("utf-8"), stored)
            return True
        except (InvalidKey, TypeError, ValueError):
            return False
    return _verify_legacy_pbkdf2(str(password), stored)


def password_needs_rehash(stored: str) -> bool:
    return not stored.startswith("$argon2id$")


def csrf_token_for_session(session_token: str, app_secret: str) -> str:
    return hmac.new(app_secret.encode("utf-8"), f"csrf:{session_token}".encode("utf-8"), hashlib.sha256).hexdigest()


def next_rate_limit_state(previous: RateLimitState | None, timestamp: float, window_seconds: int = 900, max_failures: int = 5) -> RateLimitState:
    if previous is None or previous.window_started_at <= timestamp - window_seconds:
        failures = 1
        window_started_at = timestamp
    else:
        failures = previous.failures + 1
        window_started_at = previous.window_started_at
    delay = min(60 * (2 ** max(0, failures - max_failures)), window_seconds) if failures >= max_failures else 0
    return RateLimitState(failures, window_started_at, timestamp + delay if delay else 0)
