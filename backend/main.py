"""Entry point — starts the Ring event simulator + FastAPI server."""

import asyncio
import uvicorn
from backend.api.routes import app, _events_store, _patterns_store
from backend.ring_integration.api_client import RingAPIClient
from backend.motif_engine.motif_core import MotifEngine, RingEvent as MotifRingEvent
from backend.bedrock_integration.explanation_generator import ExplanationGenerator
from datetime import datetime
import uuid

motif = MotifEngine()
bedrock = ExplanationGenerator()

# rolling window: last N events to form a sequence
_pending_events: list = []
SEQUENCE_WINDOW = 5  # group up to 5 events into one pattern


async def handle_ring_event(event):
    _pending_events.append(event)

    # store raw event for dashboard
    _events_store.append({
        "id": event.event_id,
        "camera_name": event.camera_name,
        "type": event.type,
        "confidence": event.confidence,
        "timestamp": event.timestamp.isoformat(),
        "home_id": event.home_id,
    })

    # score pattern once we have enough events
    if len(_pending_events) >= SEQUENCE_WINDOW:
        motif_events = [
            MotifRingEvent(
                camera=e.camera_name,
                type=e.type,
                timestamp=e.timestamp,
                confidence=e.confidence,
            )
            for e in _pending_events[-SEQUENCE_WINDOW:]
        ]

        score = motif.score_pattern(motif_events)

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
        else:
            explanation = None

        _patterns_store.append({
            "id": str(uuid.uuid4()),
            "home_id": event.home_id,
            "pattern_type": score.pattern_type,
            "salience_score": score.final_salience,
            "flagged": score.flagged,
            "explanation": explanation,
            "detected_at": datetime.utcnow().isoformat(),
            "event_count": SEQUENCE_WINDOW,
        })

        if score.flagged:
            print(f"[VIGILANT] FLAGGED pattern: {score.pattern_type} "
                  f"(salience={score.final_salience:.1f})")
            if explanation:
                print(f"           {explanation}")


async def run_ring_simulator():
    client = RingAPIClient.simulator()
    client.on_event(handle_ring_event)
    print("[Ring] Simulator started")
    async for event in client.stream_events():
        print(f"[Ring] {event.camera_name}: {event.type} ({event.confidence:.0%})")


async def run_api():
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    print("[API] Starting on http://localhost:8000")
    await server.serve()


async def main():
    await asyncio.gather(run_ring_simulator(), run_api())


if __name__ == "__main__":
    asyncio.run(main())
