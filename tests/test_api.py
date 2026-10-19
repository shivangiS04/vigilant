"""Tests for FastAPI routes using TestClient (no real DB or AWS needed)."""

import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from backend.api.routes import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def simulator_client(monkeypatch):
    """TestClient with RING_INTEGRATION_MODE=simulator for seed/demo tests."""
    monkeypatch.setenv("RING_INTEGRATION_MODE", "simulator")
    with TestClient(app) as c:
        yield c


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "features" in body
    assert "ring_webhook" in body["features"]
    assert "bedrock_explanations" in body["features"]
    assert "database" in body["features"]


def test_get_events_empty(client):
    res = client.get("/events?home_id=test_home")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_get_patterns_empty(client):
    res = client.get("/patterns?home_id=test_home")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_get_pattern_not_found(client):
    res = client.get("/patterns/nonexistent-id")
    assert res.status_code == 404


def test_score_pattern_returns_result(client):
    payload = {
        "home_id": "test_home",
        "events": [
            {"camera": "front_door", "type": "person_detected",
             "timestamp": "2026-10-02T10:00:00", "confidence": 0.95},
            {"camera": "side_door", "type": "person_detected",
             "timestamp": "2026-10-02T10:02:00", "confidence": 0.89},
        ],
    }
    with patch(
        "backend.bedrock_integration.explanation_generator.ExplanationGenerator.generate_explanation",
        return_value="Test explanation",
    ):
        res = client.post("/patterns/score", json=payload)

    assert res.status_code == 200
    body = res.json()
    assert "final_salience" in body
    assert "pattern_type" in body
    assert "flagged" in body
    assert 0 <= body["final_salience"] <= 10


def test_get_baseline(client):
    res = client.get("/baseline?home_id=test_home")
    assert res.status_code == 200
    body = res.json()
    assert "pattern_count" in body
    assert "patterns" in body


def test_get_baseline_comparison(client):
    res = client.get("/baseline-comparison?home_id=test_home&days=7")
    assert res.status_code == 200
    body = res.json()
    assert "days" in body
    assert len(body["days"]) == 7


def test_ring_status(client):
    res = client.get("/ring/status")
    assert res.status_code == 200
    body = res.json()
    assert "ring_configured" in body
    assert "linked_accounts" in body
    assert "devices" in body
    assert "mode" in body


def test_demo_seed_disabled_in_official_mode(client):
    """/demo/seed must return 404 when not in simulator mode."""
    with patch.dict(os.environ, {"RING_INTEGRATION_MODE": "official"}):
        res = client.post("/demo/seed?home_id=test_home")
    assert res.status_code == 404


def test_demo_seed(simulator_client):
    import uuid
    home_id = f"seed_{uuid.uuid4().hex[:8]}"
    res = simulator_client.post(f"/demo/seed?home_id={home_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["seeded_events"] > 0
    assert body["seeded_patterns"] > 0


def test_demo_seed_then_get_patterns(simulator_client):
    """Seed data should show up in GET /patterns."""
    import uuid
    home_id = f"pipe_{uuid.uuid4().hex[:8]}"
    simulator_client.post(f"/demo/seed?home_id={home_id}")
    res = simulator_client.get(f"/patterns?home_id={home_id}&days=7")
    assert res.status_code == 200
    assert len(res.json()) > 0


def test_demo_seed_explanations_labeled(simulator_client):
    """Demo seed explanations must be labeled [Sample] — not presented as live Bedrock output."""
    import uuid
    home_id = f"label_{uuid.uuid4().hex[:8]}"
    simulator_client.post(f"/demo/seed?home_id={home_id}")
    res = simulator_client.get(f"/patterns?home_id={home_id}&days=7&flagged_only=true")
    assert res.status_code == 200
    patterns = res.json()
    for p in patterns:
        if p.get("explanation"):
            assert p["explanation"].startswith("[Sample]"), (
                f"Flagged pattern explanation must start with '[Sample]': {p['explanation'][:60]}"
            )
