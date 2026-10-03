import unittest
from datetime import datetime, timedelta

from backend.motif_engine.motif_core import MotifEngine, RingEvent


class MotifTests(unittest.TestCase):
    def test_scores_event_sequence_without_fabricated_confidence(self):
        start = datetime.utcnow()
        events = [
            RingEvent("side_door", "motion_detected", start, None, "event-1"),
            RingEvent("front_door", "doorbell", start + timedelta(minutes=1), None, "event-2"),
            RingEvent("driveway", "motion_detected", start + timedelta(minutes=2), None, "event-3"),
        ]

        score = MotifEngine().score_pattern(events)

        self.assertEqual(score.pattern_type, "unusual_entrance")
        self.assertGreaterEqual(score.final_salience, 0)
        self.assertLessEqual(score.final_salience, 10)

    def test_baseline_reduces_novelty_for_seen_fingerprint(self):
        engine = MotifEngine()
        start = datetime.utcnow()
        events = [
            RingEvent("front-door", "motion_detected", start, None, "event-1"),
            RingEvent("driveway", "vehicle_detected", start + timedelta(minutes=3), None, "event-2"),
        ]
        engine.add_baseline(events)
        score = engine.score_pattern(events)

        self.assertLess(score.novelty, 9)


if __name__ == "__main__":
    unittest.main()