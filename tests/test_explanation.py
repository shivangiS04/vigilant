"""Tests for the Bedrock explanation generator (no real AWS calls)."""

import pytest
from backend.bedrock_integration.explanation_generator import ExplanationGenerator


@pytest.fixture
def gen():
    return ExplanationGenerator()


SAMPLE_PATTERN = {
    "pattern_type": "rapid_return",
    "confidence": 0.95,
    "novelty_score": 8.5,
    "salience_score": 7.2,
    "location": "123 Main Street",
    "baseline_patterns": "Person typically out 4+ hours",
    "normal_hours": "7 AM - 11 PM",
    "resident_count": 2,
    "events": [
        {"timestamp": "2:30 PM", "camera": "front_door", "type": "person_detected", "confidence": 0.95},
        {"timestamp": "2:35 PM", "camera": "side_door",  "type": "person_detected", "confidence": 0.89},
    ],
    "frequency": "First time this week",
    "last_occurrence": "Never",
}


def test_prompt_contains_pattern_type(gen):
    prompt = gen._build_prompt(SAMPLE_PATTERN)
    assert "rapid_return" in prompt


def test_prompt_contains_salience(gen):
    prompt = gen._build_prompt(SAMPLE_PATTERN)
    assert "7.2" in prompt


def test_prompt_contains_event_sequence(gen):
    prompt = gen._build_prompt(SAMPLE_PATTERN)
    assert "front_door" in prompt
    assert "side_door" in prompt


def test_high_salience_uses_alert_tone(gen):
    p = {**SAMPLE_PATTERN, "salience_score": 8.0}
    prompt = gen._build_prompt(p)
    assert "checking into" in prompt.lower() or "alert" in prompt.lower()


def test_low_salience_uses_fyi_tone(gen):
    p = {**SAMPLE_PATTERN, "salience_score": 2.0}
    prompt = gen._build_prompt(p)
    assert "unusual" in prompt.lower() or "fyi" in prompt.lower()


def test_cache_key_same_for_same_pattern_type_and_salience(gen):
    p1 = {**SAMPLE_PATTERN, "salience_score": 7.2}
    p2 = {**SAMPLE_PATTERN, "salience_score": 7.4, "location": "456 Other St"}
    # both round to salience bucket 7 → same cache key regardless of location
    assert gen._cache_key(p1) == gen._cache_key(p2)


def test_cache_key_differs_for_different_pattern_type(gen):
    p1 = {**SAMPLE_PATTERN, "pattern_type": "rapid_return"}
    p2 = {**SAMPLE_PATTERN, "pattern_type": "loitering"}
    assert gen._cache_key(p1) != gen._cache_key(p2)


def test_bedrock_failure_returns_fallback(gen):
    """If Bedrock fails, should return a fallback string not raise."""
    result = gen._call_bedrock("any prompt")
    # without real AWS creds this should return a fallback, not raise
    assert isinstance(result, str)
    assert len(result) > 0


def test_batch_prompt_contains_all_patterns(gen):
    patterns = [
        {"pattern_type": "rapid_return",     "time": "2:30 PM", "salience_score": 8.2, "summary": "Quick return"},
        {"pattern_type": "delivery",         "time": "1:00 PM", "salience_score": 5.1, "summary": "Package arrival"},
        {"pattern_type": "unusual_entrance", "time": "3:00 PM", "salience_score": 7.5, "summary": "Side door"},
    ]
    prompt = gen._build_batch_prompt(patterns, "2026-10-02", "123 Main Street")
    assert "rapid_return" in prompt
    assert "delivery" in prompt
    assert "unusual_entrance" in prompt
