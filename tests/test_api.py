"""Tests for FastAPI routes using TestClient (no real DB or AWS needed)."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from backend.api.routes import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


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
    with patch("backend.bedrock_integration.explanation_generator.ExplanationGenerator.generate_explanation",
               return_value="Test explanation"):
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


def test_demo_seed(client):
    res = client.post("/demo/seed?home_id=test_home")
    assert res.status_code == 200
    body = res.json()
    assert body["seeded_events"] > 0
    assert body["seeded_patterns"] > 0


def test_demo_seed_then_get_patterns(client):
    """Seed data should actually show up in GET /patterns."""
    client.post("/demo/seed?home_id=pipeline_test")
    res = client.get("/patterns?home_id=pipeline_test&days=7")
    assert res.status_code == 200
    assert len(res.json()) > 0
