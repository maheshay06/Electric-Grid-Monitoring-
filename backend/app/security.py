import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import get_settings

DEVICE_KEY_PREFIX = "gmk_"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


MIN_PASSWORD_LENGTH = 10


def password_problem(password: str, operator_id: str = "") -> str | None:
    """Returns why a NEW password is unacceptable, or None. Existing passwords are never re-checked."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return "Password must contain at least one letter and one digit"
    if operator_id and operator_id.lower() in password.lower():
        return "Password must not contain the operator ID"
    return None


# A valid hash of a random string, used so unknown-user logins cost the same time as wrong passwords.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def burn_password_time(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def create_access_token(subject: str, role: str, token_version: int = 0) -> tuple[str, int]:
    s = get_settings()
    expires = timedelta(minutes=s.access_token_minutes)
    payload = {"sub": subject, "role": role, "tv": token_version, "exp": datetime.now(timezone.utc) + expires}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm), int(expires.total_seconds())


def decode_access_token(token: str) -> dict | None:
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError:
        return None


# ---- device API keys: long random secrets, stored only as SHA-256 (high entropy, so no salt needed) ----
def generate_device_key() -> str:
    return DEVICE_KEY_PREFIX + secrets.token_urlsafe(32)


def hash_device_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def keys_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


# ---- simple in-memory login throttle (per operator id) ----
_failures: dict[str, list[float]] = {}


def login_locked(operator_id: str) -> bool:
    s = get_settings()
    now = time.monotonic()
    recent = [t for t in _failures.get(operator_id, []) if now - t < s.login_lockout_s]
    _failures[operator_id] = recent
    return len(recent) >= s.login_max_failures


def record_login_failure(operator_id: str) -> None:
    _failures.setdefault(operator_id, []).append(time.monotonic())


def clear_login_failures(operator_id: str) -> None:
    _failures.pop(operator_id, None)