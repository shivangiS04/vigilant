"""Tests for the rule-based explanation engine."""

import pytest
from datetime import datetime, timedelta, timezone

from backend.explanation.explainer import RuleBasedExplainer, _span_minutes, _fmt_local


@pytest.fixture
def explainer():
    return RuleBasedExplainer()


def _ts(offset_minutes: int = 0) -> str:
    """Return an ISO UTC timestamp offset_minutes ago."""
    return (datetime.now(timezone.utc) - timedelta(minutes=offset_minutes)).isoformat()


RAPID_RETURN = {
    "pattern_type": "rapid_return",
    "novelty_score": 9.0,
    "adaptation_score": 10.0,
    "salience_score": 8.2,
    "events": [
        {"timestamp": _ts(10), "camera": "front_door", "type": "person_detected", "confidence": 0.95},
        {"timestamp": _ts(2),  "camera": "side_door",  "type": "person_detected", "confidence": 0.89},
    ],
}


def test_rapid_return_mentions_camera(explainer):
    result = explainer.generate_explanation(RAPID_RETURN)
    assert "side door" in result.lower() or "side_door" in result.lower()


def test_rapid_return_mentions_salience(explainer):
    result = explainer.generate_explanation(RAPID_RETURN)
    assert "8.2" in result


def test_rapid_return_high_novelty_references_baseline(explainer):
    result = explainer.generate_explanation(RAPID_RETURN)
    assert "baseline" in result.lower()


def test_loitering_mentions_motion_count(explainer):
    data = {
        "pattern_type": "loitering",
        "novelty_score": 7.0,
        "adaptation_score": 6.0,
        "salience_score": 6.5,
        "events": [
            {"timestamp": _ts(15), "camera": "driveway", "type": "motion_detected"},
            {"timestamp": _ts(10), "camera": "driveway", "type": "motion_detected"},
            {"timestamp": _ts(5),  "camera": "driveway", "type": "motion_detected"},
        ],
    }
    result = explainer.generate_explanation(data)
    assert "driveway" in result.lower()
    assert "3" in result or "motion" in result.lower()


def test_delivery_distinguishes_vehicle_and_person_camera(explainer):
    data = {
        "pattern_type": "delivery",
        "novelty_score": 5.0,
        "adaptation_score": 5.0,
        "salience_score": 5.1,
        "events": [
            {"timestamp": _ts(5), "camera": "driveway",   "type": "vehicle_detected"},
            {"timestamp": _ts(3), "camera": "front_door", "type": "person_detected"},
        ],
    }
    result = explainer.generate_explanation(data)
    assert "driveway" in result.lower() or "front door" in result.lower()
    assert "delivery" in result.lower()


def test_late_night_activity_mentions_time_window(explainer):
    data = {
        "pattern_type": "late_night_activity",
        "novelty_score": 7.5,
        "adaptation_score": 8.0,
        "salience_score": 7.0,
        "events": [
            {"timestamp": _ts(5), "camera": "back_door", "type": "person_detected"},
        ],
    }
    result = explainer.generate_explanation(data)
    assert "11 pm" in result.lower() or "5 am" in result.lower()


def test_late_first_activity_mentions_checkin(explainer):
    data = {
        "pattern_type": "late_first_activity",
        "novelty_score": 7.0,
        "adaptation_score": 8.0,
        "salience_score": 6.8,
        "events": [
            {"timestamp": _ts(5), "camera": "front_door", "type": "motion_detected"},
        ],
    }
    result = explainer.generate_explanation(data)
    assert "check" in result.lower()


def test_standard_activity_mentions_baseline(explainer):
    data = {
        "pattern_type": "standard_activity",
        "novelty_score": 2.0,
        "adaptation_score": 3.0,
        "salience_score": 2.8,
        "events": [
            {"timestamp": _ts(5), "camera": "backyard", "type": "motion_detected"},
        ],
    }
    result = explainer.generate_explanation(data)
    assert "baseline" in result.lower()


def test_high_novelty_says_no_baseline_match(explainer):
    data = {
        "pattern_type": "unusual_entrance",
        "novelty_score": 9.0,
        "adaptation_score": 10.0,
        "salience_score": 8.5,
        "events": [
            {"timestamp": _ts(5), "camera": "garage", "type": "person_detected"},
        ],
    }
    result = explainer.generate_explanation(data)
    assert "baseline" in result.lower()


def test_moderate_novelty_says_rarely_seen(explainer):
    data = {
        "pattern_type": "multi_camera_activity",
        "novelty_score": 6.5,
        "adaptation_score": 5.0,
        "salience_score": 6.0,
        "events": [
            {"timestamp": _ts(10), "camera": "front_door", "type": "person_detected"},
            {"timestamp": _ts(8),  "camera": "driveway",   "type": "motion_detected"},
            {"timestamp": _ts(5),  "camera": "backyard",   "type": "motion_detected"},
        ],
    }
    result = explainer.generate_explanation(data)
    assert "rarely" in result.lower() or "baseline" in result.lower()


def test_daily_summary_no_patterns(explainer):
    result = explainer.generate_daily_summary([], "2026-10-20")
    assert "No patterns" in result


def test_daily_summary_counts_and_top_type(explainer):
    patterns = [
        {"pattern_type": "rapid_return", "flagged": True,  "salience_score": 8.2},
        {"pattern_type": "delivery",     "flagged": False, "salience_score": 5.1},
        {"pattern_type": "rapid_return", "flagged": True,  "salience_score": 6.0},
    ]
    result = explainer.generate_daily_summary(patterns, "2026-10-20")
    assert "3" in result
    assert "rapid return" in result.lower()


def test_daily_summary_flags_highest_salience(explainer):
    patterns = [
        {"pattern_type": "rapid_return",     "flagged": True, "salience_score": 8.2},
        {"pattern_type": "unusual_entrance", "flagged": True, "salience_score": 7.5},
    ]
    result = explainer.generate_daily_summary(patterns, "2026-10-20")
    assert "8.2" in result


def test_span_minutes_two_events():
    t0 = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    t1 = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    assert _span_minutes([{"timestamp": t0}, {"timestamp": t1}]) == 10


def test_span_minutes_single_event():
    events = [{"timestamp": datetime.now(timezone.utc).isoformat()}]
    assert _span_minutes(events) == 0


def test_generate_explanation_returns_nonempty_string(explainer):
    result = explainer.generate_explanation({
        "pattern_type": "standard_activity",
        "novelty_score": 3.0,
        "salience_score": 3.0,
        "events": [],
    })
    assert isinstance(result, str)
    assert len(result) > 0
