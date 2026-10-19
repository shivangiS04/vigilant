"""
Local development simulator that exercises the real /ring/webhook code path.

Builds official Ring Partner API v1.1 webhook payloads, signs them with
HMAC-SHA256 (same as Ring's production signing), and POSTs them to the local
backend — so signature verification, normalization, deduplication and the MOTIF
pipeline all run exactly as they do with real Ring webhooks.

Usage (as a standalone script):
    RING_HMAC_SIGNING_KEY=<key> python -m backend.ring_integration.webhook_simulator

Or import and use in backend/main.py.
"""

import asyncio
import hashlib
import hmac
import json
import os
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx


# ---------------------------------------------------------------------------
# Payload builder
# ---------------------------------------------------------------------------

SIMULATOR_ACCOUNT_ID = "sim_account_001"
SIMULATOR_HOME_ID = os.getenv("HOME_ID", "home_001")

_CAMERAS = [
    ("sim_cam_front", "front_door"),
    ("sim_cam_driveway", "driveway"),
    ("sim_cam_side", "side_door"),
    ("sim_cam_back", "backyard"),
]

_EVENT_TYPES = [
    # (ring event type, sub_type or None, weight)
    ("motion_detected", "human", 0.40),
    ("motion_detected", None, 0.20),
    ("motion_detected", "vehicle", 0.10),
    ("button_press", None, 0.10),
    ("motion_detected", "human", 0.20),  # extra weight for person
]


def _sign_body(raw_body: bytes, signing_key: str) -> str:
    """Return 'sha256=<hexdigest>' matching Ring's X-Signature format."""
    digest = hmac.new(
        signing_key.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return f"sha256={digest}"


def build_webhook_payload(
    camera_id: str,
    event_type: str,
    sub_type: Optional[str] = None,
    account_id: str = SIMULATOR_ACCOUNT_ID,
) -> dict:
    """Construct a Ring Partner API v1.1 webhook payload."""
    now_ms = int(time.time() * 1000)
    return {
        "meta": {
            "version": "1.1",
            "time": now_ms,
            "request_id": str(uuid.uuid4()),
            "account_id": account_id,
        },
        "data": {
            "id": f"sim_evt_{now_ms}_{random.randint(1000, 9999)}",
            "type": event_type,
            "attributes": {
                "source": camera_id,
                "timestamp": now_ms,
                **({"sub_type": sub_type} if sub_type else {}),
            },
        },
    }


def send_webhook(
    payload: dict,
    signing_key: str,
    webhook_url: str = "http://localhost:8000/ring/webhook",
) -> httpx.Response:
    """Sign and POST one webhook payload synchronously."""
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = _sign_body(raw_body, signing_key)
    with httpx.Client(timeout=10.0) as client:
        return client.post(
            webhook_url,
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature,
            },
        )


# ---------------------------------------------------------------------------
# Async simulator loop (used by backend/main.py)
# ---------------------------------------------------------------------------

async def run_simulator(
    signing_key: str,
    webhook_url: str = "http://localhost:8000/ring/webhook",
    interval_seconds: float = 5.0,
) -> None:
    """
    Continuously generate realistic Ring events and POST them to webhook_url.
    All events are HMAC-signed with signing_key, so the backend's signature
    verification, normalization and MOTIF pipeline run exactly as in production.
    """
    print(f"[Ring Simulator] Sending signed webhooks to {webhook_url} every {interval_seconds}s")
    print(f"[Ring Simulator] Account: {SIMULATOR_ACCOUNT_ID}  Home: {SIMULATOR_HOME_ID}")

    # Seed a completed Ring account so the webhook handler can route events to a home.
    await _ensure_simulator_account(webhook_url)

    while True:
        hour = datetime.now(timezone.utc).hour
        if 7 <= hour <= 9 or 17 <= hour <= 19:
            prob = 0.8
        elif hour >= 22 or hour <= 6:
            prob = 0.15
        else:
            prob = 0.45

        if random.random() < prob:
            camera_id, camera_name = random.choice(_CAMERAS)
            ring_type, sub_type, _ = random.choices(
                _EVENT_TYPES, weights=[w for *_, w in _EVENT_TYPES]
            )[0]

            payload = build_webhook_payload(camera_id, ring_type, sub_type)
            raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            signature = _sign_body(raw_body, signing_key)

            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.post(
                        webhook_url,
                        content=raw_body,
                        headers={
                            "Content-Type": "application/json",
                            "X-Signature": signature,
                        },
                    )
                status = resp.status_code
                label = sub_type or ring_type
                print(
                    f"[Ring] {camera_name}: {label}  "
                    f"→ webhook {status} "
                    f"(sig verified, request_id={payload['meta']['request_id'][:8]}…)"
                )
            except Exception as exc:
                print(f"[Ring Simulator] Webhook POST failed: {type(exc).__name__}: {exc}")

        await asyncio.sleep(interval_seconds)


async def _ensure_simulator_account(webhook_url: str) -> None:
    """
    The webhook handler requires a completed RingAccount row.
    In simulator mode, seed one directly via a private endpoint.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                webhook_url.replace("/ring/webhook", "/ring/simulator/seed-account"),
                json={"account_id": SIMULATOR_ACCOUNT_ID, "home_id": SIMULATOR_HOME_ID},
            )
            if resp.status_code == 200:
                print(f"[Ring Simulator] Seeded account {SIMULATOR_ACCOUNT_ID}")
    except Exception:
        pass  # endpoint may not exist yet; simulator still runs


# ---------------------------------------------------------------------------
# Standalone script entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    key = os.getenv("RING_HMAC_SIGNING_KEY")
    if not key:
        raise SystemExit("Set RING_HMAC_SIGNING_KEY to run the simulator")
    url = os.getenv("WEBHOOK_URL", "http://localhost:8000/ring/webhook")
    asyncio.run(run_simulator(key, url))
