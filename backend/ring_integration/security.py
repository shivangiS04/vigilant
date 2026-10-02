import base64
import hashlib
import hmac
import time
from typing import Optional


NONCE_VALIDITY_SECONDS = 600


def compute_account_link_nonce(time_parameter: str, account_id: str, signing_key: str) -> str:
    message = f"{time_parameter}:{account_id}".encode("utf-8")
    digest = hmac.new(signing_key.encode("utf-8"), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def verify_account_link_nonce(
    received_nonce: str,
    time_parameter: str,
    account_id: str,
    signing_key: str,
    now_seconds: Optional[float] = None,
) -> bool:
    try:
        timestamp_ms = int(time_parameter)
    except (TypeError, ValueError):
        return False

    now_ms = int((time.time() if now_seconds is None else now_seconds) * 1000)
    age_ms = now_ms - timestamp_ms
    if age_ms < 0 or age_ms > NONCE_VALIDITY_SECONDS * 1000:
        return False

    expected = compute_account_link_nonce(time_parameter, account_id, signing_key)
    return hmac.compare_digest(expected, received_nonce)


def verify_webhook_signature(signing_key: str, raw_body: bytes, signature: str) -> bool:
    if not signature.startswith("sha256="):
        return False
    expected = hmac.new(
        signing_key.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature.removeprefix("sha256="))