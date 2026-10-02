import hashlib
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from backend.database import repository as repo
from backend.database.models import RingAccount
from backend.ring_integration.official_client import RingPartnerAPIError, RingPartnerClient
from backend.ring_integration.security import verify_account_link_nonce


def _fernet() -> Fernet:
    key = os.getenv("RING_TOKEN_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("RING_TOKEN_ENCRYPTION_KEY must be configured")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError("RING_TOKEN_ENCRYPTION_KEY must be a valid Fernet key") from exc


def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode("utf-8")).decode("ascii")


def decrypt_token(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeEncodeError) as exc:
        raise RuntimeError("Stored Ring token cannot be decrypted") from exc


def receive_authorization_code(
    code: str, db: Session, client: Optional[RingPartnerClient] = None
) -> str:
    api = client or RingPartnerClient.from_env()
    tokens = api.exchange_authorization_code(code)
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    if not isinstance(access_token, str) or not access_token:
        raise RingPartnerAPIError("Ring token response has no access token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise RingPartnerAPIError("Ring token response has no refresh token")
    profile = api.get_user_profile(access_token)
    try:
        account_id = profile["data"]["id"]
        expires_in = int(tokens["expires_in"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RingPartnerAPIError("Ring returned an incomplete account or token response") from exc
    if not isinstance(account_id, str) or not account_id or expires_in <= 0:
        raise RingPartnerAPIError("Ring returned an invalid account or token response")

    repo.save_ring_account(
        db,
        {
            "account_id": account_id,
            "access_token_encrypted": encrypt_token(access_token),
            "refresh_token_encrypted": encrypt_token(refresh_token),
            "access_token_expires_at": datetime.utcnow() + timedelta(seconds=expires_in),
        },
    )
    return account_id


def get_access_token(
    db: Session, account: RingAccount, client: Optional[RingPartnerClient] = None
) -> str:
    api = client or RingPartnerClient.from_env()
    if account.access_token_expires_at > datetime.utcnow() + timedelta(minutes=5):
        return decrypt_token(account.access_token_encrypted)

    tokens = api.refresh_tokens(decrypt_token(account.refresh_token_encrypted))
    expires_in = int(tokens["expires_in"])
    account.access_token_encrypted = encrypt_token(tokens["access_token"])
    account.refresh_token_encrypted = encrypt_token(tokens["refresh_token"])
    account.access_token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    db.flush()
    return tokens["access_token"]


def mask_account_email(email: str) -> str:
    local, separator, domain = email.strip().partition("@")
    if not separator or not local or not domain:
        raise ValueError("VIGILANT_ACCOUNT_EMAIL must be a valid email address")
    if len(local) <= 2:
        masked_local = local[0] + "***"
    else:
        masked_local = local[0] + "***" + local[-1]
    return f"{masked_local}@{domain}"


def claim_ring_account(
    time_parameter: str,
    nonce: str,
    partner_user_id: str,
    account_identifier: str,
    db: Session,
    client: Optional[RingPartnerClient] = None,
) -> RingAccount:
    signing_key = os.getenv("RING_HMAC_SIGNING_KEY")
    if not signing_key:
        raise RuntimeError("RING_HMAC_SIGNING_KEY must be configured")

    matched = None
    for candidate in repo.get_unclaimed_ring_accounts(db):
        if verify_account_link_nonce(
            nonce, time_parameter, candidate.account_id, signing_key
        ):
            matched = candidate
            break
    if matched is None:
        raise ValueError("No unclaimed Ring account matches this link request")

    home_id = os.getenv("HOME_ID", "home_001")
    api = client or RingPartnerClient.from_env()
    access_token = get_access_token(db, matched, api)
    api.complete_account_link(access_token, account_identifier, nonce)

    matched.partner_user_id = partner_user_id
    matched.account_identifier = account_identifier
    matched.home_id = home_id
    matched.status = "completed"
    repo.get_or_create_home(db, home_id)
    for device in api.list_devices(access_token):
        device_id = device.get("id")
        attributes = device.get("attributes") or {}
        if isinstance(device_id, str) and device_id:
            repo.upsert_camera(
                db, home_id, device_id, attributes.get("name") or device_id
            )
    db.flush()
    return matched


def partner_user_id_from_email(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()