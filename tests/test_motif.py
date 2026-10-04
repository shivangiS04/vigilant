"""Tests for the MOTIF engine — the core of VIGILANT."""

import pytest
from datetime import datetime, timedelta
from backend.motif_engine.motif_core import MotifEngine, RingEvent, MotifScore


def make_event(camera, type_, minutes_ago=0, confidence=0.95):
    return RingEvent(
        camera=camera,
        type=type_,
        timestamp=datetime.utcnow() - timedelta(minutes=minutes_ago),
        confidence=confidence,
    )


@pytest.fixture
def engine():
    return MotifEngine()


# ------------------------------------------------------------------
# Scoring basics
# ------------------------------------------------------------------

def test_score_returns_motif_score(engine):
    events = [make_event("front_door", "person_detected")]
    score = engine.score_pattern(events)
    assert isinstance(score, MotifScore)


def test_salience_is_between_0_and_10(engine):
    events = [make_event("front_door", "motion_detected")]
    score = engine.score_pattern(events)
    assert 0 <= score.final_salience <= 10


def test_first_ever_event_flags(engine):
    """A completely novel pattern with no baseline should be flagged."""
    events = [
        make_event("side_door", "person_detected", minutes_ago=2),
        make_event("side_door", "motion_detected", minutes_ago=1),
        make_event("backyard", "person_detected", minutes_ago=0),
    ]
    score = engine.score_pattern(events)
    assert score.flagged is True


def test_known_pattern_lowers_novelty(engine):
    """After seeing a pattern many times it should score lower novelty."""
    events = [
        make_event("front_door", "person_detected", minutes_ago=1),
        make_event("front_door", "motion_detected", minutes_ago=0),
    ]
    # feed into baseline 10 times
    for _ in range(10):
        engine.add_baseline(events)

    score = engine.score_pattern(events)
    assert score.novelty <= 3.0


def test_repeated_same_day_lowers_adaptation(engine):
    """Seeing the same pattern multiple times today should reduce adaptation score."""
    events = [make_event("driveway", "vehicle_detected")]
    engine.score_pattern(events)  # first time
    score2 = engine.score_pattern(events)  # second time same session
    assert score2.adaptation < 10.0


def test_old_events_lower_temporal_weight(engine):
    """Events from yesterday should get a lower temporal weight than events just now."""
    recent = [make_event("front_door", "person_detected", minutes_ago=1)]
    old = [make_event("front_door", "person_detected", minutes_ago=1500)]  # ~25h ago

    score_recent = engine.score_pattern(recent)
    score_old = engine.score_pattern(old)
    assert score_recent.temporal_weight > score_old.temporal_weight


# ------------------------------------------------------------------
# Pattern classification
# ------------------------------------------------------------------

def test_classifies_rapid_return(engine):
    t = datetime.utcnow()
    events = [
        RingEvent("front_door", "person_detected", t, 0.95),
        RingEvent("front_door", "motion_detected", t + timedelta(minutes=1), 0.90),
        RingEvent("front_door", "person_detected", t + timedelta(minutes=8), 0.88),
    ]
    score = engine.score_pattern(events)
    assert score.pattern_type == "rapid_return"


def test_classifies_unusual_entrance(engine):
    events = [make_event("side_door", "person_detected")]
    score = engine.score_pattern(events)
    assert score.pattern_type == "unusual_entrance"


def test_classifies_delivery(engine):
    t = datetime.utcnow()
    events = [
        RingEvent("driveway", "vehicle_detected", t, 0.90),
        RingEvent("front_door", "person_detected", t + timedelta(minutes=2), 0.92),
    ]
    score = engine.score_pattern(events)
    assert score.pattern_type == "delivery"


def test_classifies_loitering(engine):
    t = datetime.utcnow()
    events = [
        RingEvent("front_door", "motion_detected", t, 0.85),
        RingEvent("front_door", "motion_detected", t + timedelta(minutes=2), 0.82),
        RingEvent("front_door", "motion_detected", t + timedelta(minutes=4), 0.80),
    ]
    score = engine.score_pattern(events)
    assert score.pattern_type == "loitering"


# ------------------------------------------------------------------
# Fingerprinting + novelty
# ------------------------------------------------------------------

def test_same_sequence_same_fingerprint(engine):
    t = datetime.utcnow()
    e1 = [RingEvent("front_door", "person_detected", t, 0.95)]
    e2 = [RingEvent("front_door", "person_detected", t, 0.80)]  # diff confidence, same structure
    assert engine._fingerprint(e1) == engine._fingerprint(e2)


def test_different_cameras_different_fingerprint(engine):
    t = datetime.utcnow()
    e1 = [RingEvent("front_door", "person_detected", t, 0.95)]
    e2 = [RingEvent("back_door", "person_detected", t, 0.95)]
    assert engine._fingerprint(e1) != engine._fingerprint(e2)


def test_fuzzy_novelty_similar_sequence_scores_lower(engine):
    """A near-identical sequence should have lower novelty than a completely alien one."""
    t = datetime.utcnow()
    known = [
        RingEvent("front_door", "person_detected", t, 0.95),
        RingEvent("front_door", "motion_detected", t + timedelta(minutes=1), 0.90),
    ]
    engine.add_baseline(known)

    # similar: same cameras, slightly different time gap
    similar = [
        RingEvent("front_door", "person_detected", t, 0.95),
        RingEvent("front_door", "motion_detected", t + timedelta(minutes=3), 0.90),
    ]
    # alien: completely different cameras and types
    alien = [
        RingEvent("backyard", "vehicle_detected", t, 0.95),
        RingEvent("side_door", "doorbell", t + timedelta(minutes=10), 0.90),
    ]

    novelty_similar = engine._calculate_novelty(engine._fingerprint(similar))
    novelty_alien = engine._calculate_novelty(engine._fingerprint(alien))
    assert novelty_similar < novelty_alien


# ------------------------------------------------------------------
# Baseline learning
# ------------------------------------------------------------------

def test_add_baseline_stores_pattern(engine):
    events = [make_event("front_door", "person_detected")]
    engine.add_baseline(events)
    fp = engine._fingerprint(events)
    assert fp in engine.baseline_patterns
    assert engine.baseline_patterns[fp].count == 1


def test_add_baseline_increments_count(engine):
    events = [make_event("front_door", "person_detected")]
    engine.add_baseline(events)
    engine.add_baseline(events)
    fp = engine._fingerprint(events)
    assert engine.baseline_patterns[fp].count == 2
