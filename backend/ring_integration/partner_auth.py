import base64
import hashlib
import hmac
import os
import secrets
from typing import Optional


PASSWORD_HASH_ITERATIONS = 310000


def create_password_hash(
    password: str, salt: Optional[str] = None, iterations: int = PASSWORD_HASH_ITERATIONS
) -> str:
    salt_value = salt or secrets.token_urlsafe(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_value.encode("utf-8"),
        iterations,
    )
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt_value}${encoded}"


def verify_partner_credentials(email: str, password: str) -> bool:
    configured_email = os.getenv("VIGILANT_ACCOUNT_EMAIL", "")
    encoded_hash = os.getenv("VIGILANT_ACCOUNT_PASSWORD_HASH", "")
    if not configured_email or not encoded_hash:
        return False
    if not hmac.compare_digest(email.strip().lower(), configured_email.strip().lower()):
        return False

    try:
        algorithm, iterations_text, salt, expected = encoded_hash.split("$", 3)
        iterations = int(iterations_text)
        if algorithm != "pbkdf2_sha256" or iterations < 100000:
            return False
        calculated = create_password_hash(password, salt, iterations).split("$", 3)[3]
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(calculated, expected)