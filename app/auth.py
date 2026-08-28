"""
Authentication & Security module: Password hashing, verification, and HMAC signed session token generation.
"""
import hmac
import hashlib
import os
import time
from typing import Optional
from app.config import get_settings

settings = get_settings()
SESSION_COOKIE_NAME = "leadmaps_session"
DEFAULT_SESSION_MAX_AGE_DAYS = 7


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with random salt."""
    salt = os.urandom(16)
    iterations = 100000
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        iterations
    )
    return f"pbkdf2_sha256${iterations}${salt.hex()}${key.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify raw password against stored PBKDF2 hash."""
    if not password or not password_hash:
        return False
    try:
        parts = password_hash.split('$')
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            # Fallback for plain comparison if needed
            return hmac.compare_digest(password, password_hash)

        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        stored_key = bytes.fromhex(parts[3])

        key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt,
            iterations
        )
        return hmac.compare_digest(key, stored_key)
    except Exception:
        return False


def create_session_token(user_id: int) -> str:
    """Create a tamper-proof HMAC-signed session token containing user_id and timestamp."""
    timestamp = int(time.time())
    secret = settings.SECRET_KEY.encode('utf-8')
    payload = f"{user_id}:{timestamp}"
    signature = hmac.new(secret, payload.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def verify_session_token(token: Optional[str], max_age_days: int = DEFAULT_SESSION_MAX_AGE_DAYS) -> Optional[int]:
    """Verify session token signature and check expiration. Returns user_id if valid, else None."""
    if not token or not isinstance(token, str):
        return None

    parts = token.split(':')
    if len(parts) != 3:
        return None

    user_id_str, timestamp_str, signature = parts
    try:
        user_id = int(user_id_str)
        timestamp = int(timestamp_str)
    except ValueError:
        return None

    # Check expiration
    max_age_seconds = max_age_days * 86400
    if time.time() - timestamp > max_age_seconds:
        return None

    # Verify HMAC signature
    secret = settings.SECRET_KEY.encode('utf-8')
    expected_payload = f"{user_id}:{timestamp}"
    expected_signature = hmac.new(secret, expected_payload.encode('utf-8'), hashlib.sha256).hexdigest()

    if hmac.compare_digest(signature, expected_signature):
        return user_id

    return None
