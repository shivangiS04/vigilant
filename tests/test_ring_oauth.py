import os
import json
import time
import unittest
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.models import Base
from backend.database import repository as repo
from backend.ring_integration.oauth import (
    claim_ring_account,
    decrypt_token,
    encrypt_token,
    get_access_token,
    receive_authorization_code,
)
from backend.ring_integration.official_client import RingPartnerClient
from backend.ring_integration.security import compute_account_link_nonce


class RingOAuthTests(unittest.TestCase):
    def setUp(self):
        self.previous_values = {
            name: os.environ.get(name)
            for name in ("RING_TOKEN_ENCRYPTION_KEY", "RING_HMAC_SIGNING_KEY", "HOME_ID")
        }
        os.environ["RING_TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode("ascii")
        os.environ["RING_HMAC_SIGNING_KEY"] = "test-hmac-key"
        os.environ["HOME_ID"] = "home-test"
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.engine.dispose()
        for name, value in self.previous_values.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_code_exchange_fetches_ring_account_and_encrypts_tokens(self):
        seen = []

        def respond(request):
            seen.append(request)
            if request.url.path == "/oauth/token":
                fields = parse_qs(request.content.decode("utf-8"))
                self.assertEqual(fields["grant_type"], ["authorization_code"])
                self.assertEqual(fields["code"], ["one-time-code"])
                return httpx.Response(
                    200,
                    json={
                        "access_token": "access-secret",
                        "refresh_token": "refresh-secret",
                        "expires_in": 14400,
                    },
                )
            self.assertEqual(request.url.path, "/v1/users/me")
            self.assertEqual(request.headers["authorization"], "Bearer access-secret")
            return httpx.Response(200, json={"data": {"id": "ring-account-1"}})

        client = RingPartnerClient(
            "client-id", "client-secret", httpx.Client(transport=httpx.MockTransport(respond))
        )
        with self.session_factory() as db:
            account_id = receive_authorization_code("one-time-code", db, client)
            account = repo.get_ring_account(db, account_id)

        self.assertEqual(account_id, "ring-account-1")
        self.assertEqual(len(seen), 2)
        self.assertNotEqual(account.access_token_encrypted, "access-secret")
        self.assertNotEqual(account.refresh_token_encrypted, "refresh-secret")
        self.assertEqual(decrypt_token(account.access_token_encrypted), "access-secret")
        self.assertEqual(decrypt_token(account.refresh_token_encrypted), "refresh-secret")
        self.assertGreater(account.access_token_expires_at, datetime.now(timezone.utc).replace(tzinfo=None))
        self.assertEqual(account.status, "unclaimed")

    def test_webhook_receipt_is_idempotent_by_ring_request_id(self):
        with self.session_factory() as db:
            self.assertTrue(repo.save_webhook_receipt(db, "request-1", "account-1", "event-1"))
            db.commit()
        with self.session_factory() as db:
            self.assertFalse(repo.save_webhook_receipt(db, "request-1", "account-1", "event-1"))
            repo.mark_webhook_processed(db, "request-1")
            db.commit()
        with self.session_factory() as db:
            receipt = repo.get_webhook_receipt(db, "request-1")
            self.assertIsNotNone(receipt.processed_at)

    def test_ring_account_link_uses_post_nonce_then_patch_completed(self):
        calls = []

        def respond(request):
            calls.append((request.method, request.url.path, request.headers.get("authorization"), request.read()))
            return httpx.Response(200, json={"data": {"attributes": {"status": "completed"}}})

        client = RingPartnerClient(
            "client-id", "client-secret", httpx.Client(transport=httpx.MockTransport(respond))
        )
        client.complete_account_link("access-token", "o***r@example.com", "nonce-value")

        self.assertEqual(
            [(method, path) for method, path, _, _ in calls],
            [
                ("POST", "/v1/accounts/me/app-integrations"),
                ("PATCH", "/v1/accounts/me/app-integrations"),
            ],
        )
        self.assertTrue(all(call[2] == "Bearer access-token" for call in calls))
        self.assertEqual(json.loads(calls[0][3]), {
            "account_identifier": "o***r@example.com",
            "nonce": "nonce-value",
        })
        self.assertEqual(json.loads(calls[1][3]), {"status": "completed"})

    def test_expired_access_token_refreshes_and_rotates_both_tokens(self):
        class FakeRingClient:
            def refresh_tokens(self, refresh_token):
                self.received_refresh_token = refresh_token
                return {
                    "access_token": "rotated-access",
                    "refresh_token": "rotated-refresh",
                    "expires_in": 14400,
                }

        client = FakeRingClient()
        with self.session_factory() as db:
            account = repo.save_ring_account(
                db,
                {
                    "account_id": "ring-refresh-account",
                    "access_token_encrypted": encrypt_token("expired-access"),
                    "refresh_token_encrypted": encrypt_token("old-refresh"),
                    "access_token_expires_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1),
                },
            )
            token = get_access_token(db, account, client)
            db.commit()
            stored_access = account.access_token_encrypted
            stored_refresh = account.refresh_token_encrypted

        self.assertEqual(client.received_refresh_token, "old-refresh")
        self.assertEqual(token, "rotated-access")
        self.assertEqual(decrypt_token(stored_access), "rotated-access")
        self.assertEqual(decrypt_token(stored_refresh), "rotated-refresh")

    def test_nonce_expired_raises_value_error(self):
        """Nonce timestamp older than 600 seconds must be rejected."""
        old_time_ms = str((int(time.time()) - 601) * 1000)
        nonce = compute_account_link_nonce(old_time_ms, "ring-expired-account", "test-hmac-key")
        with self.session_factory() as db:
            repo.save_ring_account(
                db,
                {
                    "account_id": "ring-expired-account",
                    "access_token_encrypted": encrypt_token("tok"),
                    "refresh_token_encrypted": encrypt_token("ref"),
                    "access_token_expires_at": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1),
                },
            )
            db.commit()
        with self.session_factory() as db:
            with self.assertRaises(ValueError, msg="expired nonce should raise ValueError"):
                claim_ring_account(old_time_ms, nonce, "user-1", "u***r@example.com", db)

    def test_bad_nonce_signature_raises_value_error(self):
        """Nonce signed with wrong key must be rejected even if timestamp is fresh."""
        time_ms = str(int(time.time()) * 1000)
        bad_nonce = compute_account_link_nonce(time_ms, "ring-bad-sig-account", "wrong-key")
        with self.session_factory() as db:
            repo.save_ring_account(
                db,
                {
                    "account_id": "ring-bad-sig-account",
                    "access_token_encrypted": encrypt_token("tok"),
                    "refresh_token_encrypted": encrypt_token("ref"),
                    "access_token_expires_at": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1),
                },
            )
            db.commit()
        with self.session_factory() as db:
            with self.assertRaises(ValueError, msg="bad nonce should raise ValueError"):
                claim_ring_account(time_ms, bad_nonce, "user-1", "u***r@example.com", db)

    def test_token_exchange_ring_api_error_propagates(self):
        """If Ring's token endpoint returns an error the function must raise."""
        def respond(request):
            if request.url.path == "/oauth/token":
                return httpx.Response(401, json={"error": "invalid_client"})
            return httpx.Response(200, json={})

        client = RingPartnerClient(
            "client-id", "client-secret", httpx.Client(transport=httpx.MockTransport(respond))
        )
        from backend.ring_integration.official_client import RingPartnerAPIError
        with self.session_factory() as db:
            with self.assertRaises(RingPartnerAPIError):
                receive_authorization_code("bad-code", db, client)

    def test_repeat_token_exchange_updates_existing_account(self):
        """A second token exchange for the same account_id must overwrite the first record."""
        token_calls = [0]

        def respond(request):
            if request.url.path == "/oauth/token":
                token_calls[0] += 1
                n = token_calls[0]
                return httpx.Response(200, json={
                    "access_token": f"access-{n}",
                    "refresh_token": f"refresh-{n}",
                    "expires_in": 14400,
                })
            return httpx.Response(200, json={"data": {"id": "ring-repeat-account"}})

        client = RingPartnerClient(
            "client-id", "client-secret", httpx.Client(transport=httpx.MockTransport(respond))
        )
        with self.session_factory() as db:
            id1 = receive_authorization_code("code-1", db, client)
            db.commit()
        with self.session_factory() as db:
            id2 = receive_authorization_code("code-2", db, client)
            db.commit()
        with self.session_factory() as db:
            accounts = db.query(repo.RingAccount).filter(
                repo.RingAccount.account_id == "ring-repeat-account"
            ).all()

        self.assertEqual(id1, id2)
        self.assertEqual(len(accounts), 1, "must not create duplicate DB rows")
        self.assertEqual(decrypt_token(accounts[0].access_token_encrypted), "access-2")

    def test_claim_without_matching_account_raises_value_error(self):
        """claim_ring_account must raise ValueError when the account_id has no DB record."""
        time_ms = str(int(time.time()) * 1000)
        nonce = compute_account_link_nonce(time_ms, "nonexistent-account", "test-hmac-key")
        with self.session_factory() as db:
            with self.assertRaises(ValueError):
                claim_ring_account(time_ms, nonce, "user-1", "u***r@example.com", db)

    def test_account_claim_verifies_nonce_then_links_and_syncs_devices(self):
        now = int(time.time())
        time_parameter = str(now * 1000)
        nonce = compute_account_link_nonce(
            time_parameter, "ring-account-claim", "test-hmac-key"
        )

        class FakeRingClient:
            def __init__(self):
                self.calls = []

            def complete_account_link(self, access_token, account_identifier, received_nonce):
                self.calls.append(("confirmed", access_token, account_identifier, received_nonce))

            def list_devices(self, access_token):
                self.calls.append(("devices", access_token))
                return [{"id": "ring-device-1", "attributes": {"name": "Front Door"}}]

        ring_client = FakeRingClient()
        with self.session_factory() as db:
            repo.save_ring_account(
                db,
                {
                    "account_id": "ring-account-claim",
                    "access_token_encrypted": encrypt_token("access-token"),
                    "refresh_token_encrypted": encrypt_token("refresh-token"),
                    "access_token_expires_at": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1),
                },
            )
            db.commit()

        with self.session_factory() as db:
            account = claim_ring_account(
                time_parameter,
                nonce,
                "vigilant-user-id",
                "o***r@example.com",
                db,
                ring_client,
            )
            db.commit()
            camera = db.query(repo.Camera).filter(repo.Camera.id == "ring-device-1").one()
            account_values = (
                account.status,
                account.partner_user_id,
                account.home_id,
                camera.name,
            )

        self.assertEqual(account_values[:3], ("completed", "vigilant-user-id", "home-test"))
        self.assertEqual(ring_client.calls[0][0], "confirmed")
        self.assertEqual(ring_client.calls[1], ("devices", "access-token"))
        self.assertEqual(account_values[3], "Front Door")


if __name__ == "__main__":
    unittest.main()