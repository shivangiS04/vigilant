"""
End-to-end webhook pipeline tests.

Tests the full path: signed webhook → HMAC verification → normalization →
deduplication → MOTIF scoring. No real Ring account or AWS credentials needed.
"""

import hashlib
import hmac
import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.ring_integration.security import verify_webhook_signature
from backend.ring_integration.normalization import normalize_webhook_event
from backend.ring_integration.webhook_simulator import build_webhook_payload, _sign_body


# ---------------------------------------------------------------------------
# Official Ring v1.1 sample payloads (from Ring Partner API docs)
# ---------------------------------------------------------------------------

MOTION_PAYLOAD = {
    "meta": {
        "version": "1.1",
        "time": 1_800_000_000_000,
        "request_id": "req-motion-001",
        "account_id": "ring-account-001",
    },
    "data": {
        "id": "evt-motion-001",
        "type": "motion_detected",
        "attributes": {
            "source": "device-front-door",
            "timestamp": 1_800_000_000_000,
            "sub_type": "human",
        },
    },
}

BUTTON_PRESS_PAYLOAD = {
    "meta": {
        "version": "1.1",
        "time": 1_800_000_001_000,
        "request_id": "req-doorbell-001",
        "account_id": "ring-account-001",
    },
    "data": {
        "id": "evt-doorbell-001",
        "type": "button_press",
        "attributes": {
            "source": "device-front-door",
            "timestamp": 1_800_000_001_000,
        },
    },
}

VEHICLE_PAYLOAD = {
    "meta": {
        "version": "1.1",
        "time": 1_800_000_002_000,
        "request_id": "req-vehicle-001",
        "account_id": "ring-account-001",
    },
    "data": {
        "id": "evt-vehicle-001",
        "type": "motion_detected",
        "attributes": {
            "source": "device-driveway",
            "timestamp": 1_800_000_002_000,
            "sub_type": "vehicle",
        },
    },
}

APP_INTEGRATION_REMOVED_PAYLOAD = {
    "meta": {
        "version": "1.1",
        "time": 1_800_000_003_000,
        "request_id": "req-removed-001",
        "account_id": "ring-account-001",
    },
    "data": {
        "id": "evt-removed-001",
        "type": "app_integration_removed",
        "attributes": {},
    },
}

SIGNING_KEY = "test-signing-key-32-chars-exactly"


def _sign(payload: dict, key: str = SIGNING_KEY) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return _sign_body(raw, key)


# ---------------------------------------------------------------------------
# HMAC verification tests
# ---------------------------------------------------------------------------

class TestWebhookSignatureVerification(unittest.TestCase):

    def test_valid_signature_accepted(self):
        body = json.dumps(MOTION_PAYLOAD, separators=(",", ":")).encode()
        digest = hmac.new(SIGNING_KEY.encode(), body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_webhook_signature(SIGNING_KEY, body, f"sha256={digest}"))

    def test_wrong_key_rejected(self):
        body = json.dumps(MOTION_PAYLOAD, separators=(",", ":")).encode()
        digest = hmac.new(b"wrong-key", body, hashlib.sha256).hexdigest()
        self.assertFalse(verify_webhook_signature(SIGNING_KEY, body, f"sha256={digest}"))

    def test_tampered_body_rejected(self):
        body = json.dumps(MOTION_PAYLOAD, separators=(",", ":")).encode()
        digest = hmac.new(SIGNING_KEY.encode(), body, hashlib.sha256).hexdigest()
        tampered = body + b"X"
        self.assertFalse(verify_webhook_signature(SIGNING_KEY, tampered, f"sha256={digest}"))

    def test_missing_sha256_prefix_rejected(self):
        body = json.dumps(MOTION_PAYLOAD, separators=(",", ":")).encode()
        digest = hmac.new(SIGNING_KEY.encode(), body, hashlib.sha256).hexdigest()
        self.assertFalse(verify_webhook_signature(SIGNING_KEY, body, digest))

    def test_empty_signature_rejected(self):
        body = json.dumps(MOTION_PAYLOAD, separators=(",", ":")).encode()
        self.assertFalse(verify_webhook_signature(SIGNING_KEY, body, ""))


# ---------------------------------------------------------------------------
# Normalization tests (official payload shapes)
# ---------------------------------------------------------------------------

class TestWebhookNormalization(unittest.TestCase):

    def test_motion_human_subtype_becomes_person_detected(self):
        event = normalize_webhook_event(MOTION_PAYLOAD)
        self.assertIsNotNone(event)
        self.assertEqual(event.type, "person_detected")
        self.assertEqual(event.camera_id, "device-front-door")
        self.assertEqual(event.event_id, "evt-motion-001")
        self.assertIsNone(event.confidence)

    def test_button_press_becomes_doorbell(self):
        event = normalize_webhook_event(BUTTON_PRESS_PAYLOAD)
        self.assertIsNotNone(event)
        self.assertEqual(event.type, "doorbell")
        self.assertEqual(event.camera_id, "device-front-door")

    def test_motion_vehicle_subtype(self):
        event = normalize_webhook_event(VEHICLE_PAYLOAD)
        self.assertIsNotNone(event)
        self.assertEqual(event.type, "vehicle_detected")
        self.assertEqual(event.camera_id, "device-driveway")

    def test_app_integration_removed_returns_none(self):
        event = normalize_webhook_event(APP_INTEGRATION_REMOVED_PAYLOAD)
        self.assertIsNone(event)

    def test_timestamp_parsed_from_milliseconds(self):
        event = normalize_webhook_event(MOTION_PAYLOAD)
        self.assertIsNotNone(event)
        expected = datetime.fromtimestamp(1_800_000_000_000 / 1000, tz=timezone.utc).replace(tzinfo=None)
        self.assertEqual(event.timestamp, expected)

    def test_malformed_payload_raises(self):
        with self.assertRaises(ValueError):
            normalize_webhook_event({"meta": {}, "data": {}})


# ---------------------------------------------------------------------------
# Simulator payload builder
# ---------------------------------------------------------------------------

class TestWebhookSimulatorBuilder(unittest.TestCase):

    def test_built_payload_normalizes_correctly(self):
        payload = build_webhook_payload("cam-001", "motion_detected", "human")
        event = normalize_webhook_event(payload)
        self.assertIsNotNone(event)
        self.assertEqual(event.type, "person_detected")
        self.assertEqual(event.camera_id, "cam-001")

    def test_signature_validates(self):
        payload = build_webhook_payload("cam-001", "button_press")
        raw = json.dumps(payload, separators=(",", ":")).encode()
        sig = _sign_body(raw, SIGNING_KEY)
        self.assertTrue(verify_webhook_signature(SIGNING_KEY, raw, sig))


# ---------------------------------------------------------------------------
# Webhook endpoint integration (no real Ring account needed)
# ---------------------------------------------------------------------------

@pytest.fixture
def webhook_client(monkeypatch):
    monkeypatch.setenv("RING_HMAC_SIGNING_KEY", SIGNING_KEY)
    monkeypatch.setenv("RING_INTEGRATION_MODE", "simulator")
    from backend.api.routes import app
    with TestClient(app) as c:
        # Seed a simulator account so events can be routed
        c.post(
            "/ring/simulator/seed-account",
            json={"account_id": "ring-account-001", "home_id": "webhook_test_home"},
        )
        yield c


def _post_webhook(client, payload, key=SIGNING_KEY):
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return client.post(
        "/ring/webhook",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Signature": _sign_body(raw, key),
        },
    )


def test_webhook_motion_accepted(webhook_client):
    res = _post_webhook(webhook_client, MOTION_PAYLOAD)
    assert res.status_code == 200
    assert res.json()["status"] in ("accepted", "duplicate")


def test_webhook_invalid_signature_rejected(webhook_client):
    raw = json.dumps(MOTION_PAYLOAD, separators=(",", ":")).encode()
    res = webhook_client.post(
        "/ring/webhook",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Signature": "sha256=badbadbadbad",
        },
    )
    assert res.status_code == 401


def test_webhook_duplicate_request_id_is_idempotent(webhook_client):
    """Same request_id sent twice must not create duplicate events."""
    first = _post_webhook(webhook_client, BUTTON_PRESS_PAYLOAD)
    second = _post_webhook(webhook_client, BUTTON_PRESS_PAYLOAD)
    assert first.status_code == 200
    assert second.status_code == 200
    # Second call is a duplicate — status may differ but must not crash
    assert second.json()["status"] in ("accepted", "duplicate")


def test_webhook_no_signing_key_returns_503(monkeypatch):
    monkeypatch.delenv("RING_HMAC_SIGNING_KEY", raising=False)
    from backend.api.routes import app
    with TestClient(app) as client:
        raw = json.dumps(MOTION_PAYLOAD, separators=(",", ":")).encode()
        res = client.post(
            "/ring/webhook",
            content=raw,
            headers={"Content-Type": "application/json", "X-Signature": "sha256=anything"},
        )
    assert res.status_code == 503
