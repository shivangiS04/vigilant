from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import math


@dataclass
class RingEvent:
    camera: str
    type: str          # person_detected, motion_detected, vehicle_detected, doorbell
    timestamp: datetime
    confidence: float  # 0.0 - 1.0


@dataclass
class MotifScore:
    novelty: float          # 0-10
    adaptation: float       # 0-10
    temporal_weight: float  # 0-1 multiplier
    competition: float      # 0-10
    final_salience: float   # 0-10
    pattern_type: str
    flagged: bool


@dataclass
class BaselinePattern:
    fingerprint: str
    count: int = 0
    last_seen: Optional[datetime] = None
    first_seen: Optional[datetime] = None


class MotifEngine:
    """
    Drosophila-inspired attention model for Ring event sequences.
    Scores how much a pattern deserves user attention.

    Final salience = (novelty * 0.4) + (adaptation * 0.3) + (temporal * 0.2) + (competition * 0.1)
    Flag threshold: salience > 6.0
    """

    SALIENCE_FLAG_THRESHOLD = 6.0

    WEIGHTS = {
        "novelty": 0.4,
        "adaptation": 0.3,
        "temporal": 0.2,
        "competition": 0.1,
    }

    def __init__(self):
        # key: fingerprint string → BaselinePattern
        self.baseline_patterns: Dict[str, BaselinePattern] = {}
        # list of (timestamp, fingerprint) for today's events
        self.daily_events: List[tuple] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score_pattern(self, events: List[RingEvent]) -> MotifScore:
        fingerprint = self._fingerprint(events)
        pattern_type = self._classify_pattern(events)

        novelty = self._calculate_novelty(fingerprint)
        adaptation = self._calculate_adaptation(fingerprint)
        temporal_weight = self._calculate_temporal_weight(events)
        competition = self._calculate_competition(events)

        salience = (
            novelty * self.WEIGHTS["novelty"]
            + adaptation * self.WEIGHTS["adaptation"]
            + temporal_weight * self.WEIGHTS["temporal"]
            + competition * self.WEIGHTS["competition"]
        )

        self._record_pattern(fingerprint, events)

        return MotifScore(
            novelty=round(novelty, 2),
            adaptation=round(adaptation, 2),
            temporal_weight=round(temporal_weight, 2),
            competition=round(competition, 2),
            final_salience=round(salience, 2),
            pattern_type=pattern_type,
            flagged=salience > self.SALIENCE_FLAG_THRESHOLD,
        )

    def add_baseline(self, events: List[RingEvent]):
        """Feed a known-normal sequence into the baseline."""
        fingerprint = self._fingerprint(events)
        if fingerprint not in self.baseline_patterns:
            self.baseline_patterns[fingerprint] = BaselinePattern(fingerprint=fingerprint)
        bp = self.baseline_patterns[fingerprint]
        bp.count += 1
        bp.last_seen = events[-1].timestamp if events else None
        if bp.first_seen is None:
            bp.first_seen = events[0].timestamp if events else None

    # ------------------------------------------------------------------
    # Scoring layers
    # ------------------------------------------------------------------

    def _calculate_novelty(self, fingerprint: str) -> float:
        """Layer 1 — How different from learned baseline? (0-10)"""
        if fingerprint not in self.baseline_patterns:
            return 9.0  # never seen

        bp = self.baseline_patterns[fingerprint]
        if bp.count >= 10:
            return 1.0  # deeply familiar
        if bp.count >= 5:
            return 3.0
        if bp.count >= 2:
            return 5.0
        return 7.0  # seen once before

    def _calculate_adaptation(self, fingerprint: str) -> float:
        """Layer 2 — Sensory adaptation: how often seen? (0-10)"""
        if fingerprint not in self.baseline_patterns:
            return 10.0  # first time ever

        bp = self.baseline_patterns[fingerprint]
        now = datetime.utcnow()

        # same-day repeat → near-zero
        if bp.last_seen and (now - bp.last_seen) < timedelta(hours=3):
            return 1.0

        # decay by count
        if bp.count == 1:
            return 7.0
        if bp.count <= 3:
            return 5.0
        if bp.count <= 7:
            return 3.0
        return 1.5

    def _calculate_temporal_weight(self, events: List[RingEvent]) -> float:
        """Layer 3 — Recency multiplier (0-1)."""
        if not events:
            return 0.5
        latest = max(e.timestamp for e in events)
        age = datetime.utcnow() - latest
        minutes = age.total_seconds() / 60

        if minutes <= 5:
            return 1.0
        if minutes <= 60:
            return 0.8
        if minutes <= 1440:  # 24 h
            return 0.5
        return 0.2

    def _calculate_competition(self, events: List[RingEvent]) -> float:
        """Layer 4 — Attention competition from other patterns today (0-10)."""
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=24)
        today_count = sum(1 for ts, _ in self.daily_events if ts > cutoff)

        if today_count == 0:
            return 10.0
        if today_count == 1:
            return 7.0
        if today_count <= 3:
            return 5.0
        return 3.0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fingerprint(self, events: List[RingEvent]) -> str:
        """Encode a sequence as a compact string for comparison."""
        parts = []
        for e in events:
            parts.append(f"{e.camera}:{e.type}")
        # time deltas between consecutive events (bucketed to 5-min windows)
        for i in range(1, len(events)):
            delta_min = int((events[i].timestamp - events[i - 1].timestamp).total_seconds() / 60)
            bucket = (delta_min // 5) * 5
            parts.append(f"Δ{bucket}m")
        return "|".join(parts)

    def _classify_pattern(self, events: List[RingEvent]) -> str:
        if not events:
            return "empty"

        cameras = [e.camera for e in events]
        types = [e.type for e in events]

        # rapid return: left then came back quickly
        if len(events) >= 2 and cameras[0] == cameras[-1] and "person_detected" in types:
            if len(events) >= 2:
                span = (events[-1].timestamp - events[0].timestamp).total_seconds() / 60
                if span < 15:
                    return "rapid_return"

        # unusual entrance: person on non-primary camera first
        if cameras[0] in ("side_door", "back_door", "garage"):
            return "unusual_entrance"

        # loitering: multiple motion events, no person exit
        motion_count = types.count("motion_detected")
        if motion_count >= 3:
            return "loitering"

        # package delivery: vehicle then person then leave
        if "vehicle_detected" in types and "person_detected" in types:
            return "delivery"

        # multiple cameras in short window
        unique_cameras = set(cameras)
        if len(unique_cameras) >= 3:
            return "multi_camera_activity"

        return "standard_activity"

    def _record_pattern(self, fingerprint: str, events: List[RingEvent]):
        now = datetime.utcnow()
        self.daily_events.append((now, fingerprint))
        # prune old entries (keep last 48h)
        cutoff = now - timedelta(hours=48)
        self.daily_events = [(ts, fp) for ts, fp in self.daily_events if ts > cutoff]


# ------------------------------------------------------------------
# Smoke test
# ------------------------------------------------------------------
if __name__ == "__main__":
    engine = MotifEngine()

    t0 = datetime(2026, 9, 26, 14, 30, 0)
    events = [
        RingEvent("front_door", "person_detected", t0, 0.95),
        RingEvent("front_door", "motion_detected", t0 + timedelta(minutes=1), 0.92),
        RingEvent("side_door", "person_detected", t0 + timedelta(minutes=5), 0.89),
    ]

    score = engine.score_pattern(events)
    print(f"Pattern: {score.pattern_type}")
    print(f"Salience: {score.final_salience}/10  (flagged={score.flagged})")
    print(f"  novelty={score.novelty}  adaptation={score.adaptation}  "
          f"temporal={score.temporal_weight}  competition={score.competition}")
