import hashlib
import hmac
import unittest

from backend.ring_integration.normalization import (
    normalize_history_event,
    normalize_webhook_event,
)
from backend.ring_integration.security import (
    compute_account_link_nonce,
    verify_account_link_nonce,
    verify_webhook_signature,
)


class RingSecurityTests(unittest.TestCase):
    def test_webhook_signature_uses_raw_body_and_sha256_prefix(self):
        body = b'{"meta":{"request_id":"req-1"}}'
        digest = hmac.new(b"key", body, hashlib.sha256).hexdigest()

        self.assertTrue(verify_webhook_signature("key", body, f"sha256={digest}"))
        self.assertFalse(verify_webhook_signature("key", body + b" ", f"sha256={digest}"))
        self.assertFalse(verify_webhook_signature("key", body, digest))

    def test_account_link_nonce_is_time_bound_and_constant_format(self):
        now = 1_800_000_000
        timestamp = str(now * 1000)
        nonce = compute_account_link_nonce(timestamp, "ring-account", "signing-key")

        self.assertTrue(
            verify_account_link_nonce(
                nonce, timestamp, "ring-account", "signing-key", now_seconds=now
            )
        )
        self.assertFalse(
            verify_account_link_nonce(
                nonce, timestamp, "other-account", "signing-key", now_seconds=now
            )
        )
        self.assertFalse(
            verify_account_link_nonce(
                nonce, str((now - 601) * 1000), "ring-account", "signing-key", now_seconds=now
            )
        )
        self.assertFalse(
            verify_account_link_nonce(
                nonce, "not-a-time", "ring-account", "signing-key", now_seconds=now
            )
        )

    def test_webhook_motion_and_button_press_normalize_without_confidence(self):
        payload = {
            "meta": {"account_id": "account-1", "request_id": "request-1"},
            "data": {
                "id": "event-1",
                "type": "motion_detected",
                "attributes": {
                    "source": "device-1",
                    "timestamp": 1_800_000_000_000,
                    "sub_type": "human",
                },
            },
        }

        event = normalize_webhook_event(payload)

        self.assertEqual(event.type, "person_detected")
        self.assertEqual(event.camera_id, "device-1")
        self.assertIsNone(event.confidence)

        payload["data"]["type"] = "button_press"
        payload["data"]["id"] = "event-2"
        self.assertEqual(normalize_webhook_event(payload).type, "doorbell")

    def test_history_ding_and_motion_subtype_normalize(self):
        event = normalize_history_event(
            {
                "id": "history-1",
                "attributes": {"event_type": "ding", "start": 1_800_000_000_000},
                "relationships": {"source": {"data": {"id": "device-1"}}},
            },
            account_id="account-1",
        )
        self.assertEqual(event.type, "doorbell")

        event = normalize_history_event(
            {
                "id": "history-2",
                "attributes": {"event_type": "motion.vehicle", "start": 1_800_000_000_000},
                "relationships": {"source": {"data": {"id": "device-1"}}},
            },
            account_id="account-1",
        )
        self.assertEqual(event.type, "vehicle_detected")
        self.assertIsNone(event.confidence)


if __name__ == "__main__":
    unittest.main()