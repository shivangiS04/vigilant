import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api.routes import app


class APIRouteTests(unittest.TestCase):
    def setUp(self):
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)

    def test_health_and_empty_event_routes(self):
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")

        events = self.client.get("/events", params={"home_id": "api-test-home"})
        self.assertEqual(events.status_code, 200)
        self.assertEqual(events.json(), [])

    def test_token_callback_rejects_missing_and_wrong_client_id(self):
        with patch.dict(os.environ, {"RING_CLIENT_ID": "configured-client"}):
            missing = self.client.post("/ring/token", data={"code": "auth-code"})
            wrong = self.client.post(
                "/ring/token",
                data={"code": "auth-code", "client_id": "other-client"},
            )

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(wrong.status_code, 401)

    def test_demo_seed_is_disabled_in_official_mode(self):
        with patch.dict(os.environ, {"RING_INTEGRATION_MODE": "official"}):
            response = self.client.post("/demo/seed")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()