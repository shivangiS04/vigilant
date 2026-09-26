"""Entry point — starts the Ring event simulator + FastAPI server."""

import asyncio
import uvicorn
from backend.api.routes import app, motif, bedrock
from backend.ring_integration.api_client import RingAPIClient
from backend.motif_engine.motif_core import RingEvent as MotifRingEvent
from backend.database.session import get_db
from backend.database import repository as repo
from datetime import datetime
import uuid

_pending_events: list = []
SEQUENCE_WINDOW = 5
HOME_ID = "home_001"


async def handle_ring_event(event):
    event_dict = {
        "id": event.event_id,
        "camera_id": event.camera_name,
        "type": event.type,
        "confidence": event.confidence,
        "timestamp": event.timestamp.isoformat(),
        "home_id": event.home_id,
    }

    with get_db() as db:
        repo.save_event(db, event_dict)

    _pending_events.append(event)

    if len(_pending_events) >= SEQUENCE_WINDOW:
        window = _pending_events[-SEQUENCE_WINDOW:]
        motif_events = [
            MotifRingEvent(
                camera=e.camera_name,
                type=e.type,
                timestamp=e.timestamp,
                confidence=e.confidence,
            )
            for e in window
        ]

        score = motif.score_pattern(motif_events)
        fingerprint = motif._fingerprint(motif_events)

        if score.flagged:
            pattern_data = {
                "pattern_type": score.pattern_type,
                "confidence": sum(e.confidence for e in motif_events) / len(motif_events),
                "novelty_score": score.novelty,
                "salience_score": score.final_salience,
                "events": [
                    {"timestamp": str(e.timestamp), "camera": e.camera, "type": e.type, "confidence": e.confidence}
                    for e in motif_events
                ],
            }
            explanation = bedrock.generate_explanation(pattern_data)
            print(f"[VIGILANT] FLAGGED {score.pattern_type} salience={score.final_salience:.1f}")
            print(f"           {explanation}")
        else:
            explanation = "Pattern within normal parameters."

        pattern_record = {
            "id": str(uuid.uuid4()),
            "home_id": HOME_ID,
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
            "event_ids": [e.event_id for e in window],
        }

        with get_db() as db:
            repo.save_pattern(db, pattern_record)
            if score.final_salience < 4.0:
                repo.upsert_baseline(db, HOME_ID, fingerprint, score.pattern_type)
                motif.add_baseline(motif_events)


async def run_ring_simulator():
    client = RingAPIClient.simulator(home_id=HOME_ID)
    client.on_event(handle_ring_event)
    print("[Ring] Simulator started (polling every 5s)")
    async for event in client.stream_events():
        print(f"[Ring] {event.camera_name}: {event.type} ({event.confidence:.0%})")


async def run_api():
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    print("[API]  http://localhost:8000")
    await server.serve()


async def main():
    await asyncio.gather(run_ring_simulator(), run_api())


if __name__ == "__main__":
    asyncio.run(main())
