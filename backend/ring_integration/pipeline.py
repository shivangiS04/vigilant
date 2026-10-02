import threading
import uuid
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Dict, List

from backend.database import repository as repo
from backend.database.session import get_db
from backend.motif_engine.motif_core import MotifEngine, RingEvent as MotifRingEvent


class RingEventPipeline:
    def __init__(self, motif: MotifEngine, bedrock: Any, alexa: Any, window_size: int = 5):
        self.motif = motif
        self.bedrock = bedrock
        self.alexa = alexa
        self.window_size = window_size
        self._pending: Dict[str, deque] = defaultdict(lambda: deque(maxlen=window_size))
        self._lock = threading.RLock()

    def process(self, event_data: dict, home_id: str) -> None:
        event = MotifRingEvent(
            camera=event_data["camera_name"],
            type=event_data["type"],
            timestamp=datetime.fromisoformat(event_data["timestamp"]),
            confidence=event_data.get("confidence"),
            event_id=event_data["id"],
        )

        with self._lock:
            window_buffer = self._pending[home_id]
            window_buffer.append(event)
            if len(window_buffer) < self.window_size:
                return
            window = list(window_buffer)

            score = self.motif.score_pattern(window)
            fingerprint = self.motif._fingerprint(window)
            known_confidences = [
                item.confidence for item in window if item.confidence is not None
            ]
            confidence = (
                sum(known_confidences) / len(known_confidences)
                if known_confidences
                else None
            )

            pattern_data = {
                "pattern_type": score.pattern_type,
                "confidence": confidence,
                "novelty_score": score.novelty,
                "salience_score": score.final_salience,
                "events": [
                    {
                        "timestamp": item.timestamp.isoformat(),
                        "camera": item.camera,
                        "type": item.type,
                        "confidence": item.confidence,
                    }
                    for item in window
                ],
            }
            explanation = (
                self.bedrock.generate_explanation(pattern_data)
                if score.flagged
                else "Pattern within normal parameters."
            )

            pattern_record = {
                "id": str(uuid.uuid4()),
                "home_id": home_id,
                "pattern_type": score.pattern_type,
                "fingerprint": fingerprint,
                "salience_score": score.final_salience,
                "novelty_score": score.novelty,
                "adaptation_score": score.adaptation,
                "temporal_weight": score.temporal_weight,
                "competition_score": score.competition,
                "flagged": score.flagged,
                "explanation": explanation,
                "detected_at": datetime.utcnow().isoformat(),
                "event_ids": [item.event_id for item in window],
            }
            with get_db() as db:
                repo.save_pattern(db, pattern_record)
                if score.final_salience < 4.0:
                    repo.upsert_baseline(db, home_id, fingerprint, score.pattern_type)
                    self.motif.add_baseline(window)

            if score.flagged:
                self.alexa.send_alert(home_id, pattern_record)