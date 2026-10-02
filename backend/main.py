"""Start Vigilant's API and an explicitly selected development simulator."""

import asyncio
import os
import uvicorn
from backend.api.routes import app, ring_pipeline
from backend.ring_integration.api_client import RingAPIClient
from backend.database.session import get_db
from backend.database import repository as repo
HOME_ID = os.getenv("HOME_ID", "home_001")


async def handle_ring_event(event):
    event_dict = {
        "id": event.event_id,
        "camera_id": event.camera_id,
        "camera_name": event.camera_name,
        "type": event.type,
        "confidence": event.confidence,
        "timestamp": event.timestamp.isoformat(),
        "home_id": event.home_id,
    }

    with get_db() as db:
        repo.upsert_camera(db, event.home_id, event.camera_id, event.camera_name)
        repo.save_event(db, event_dict)
    ring_pipeline.process(event_dict, event.home_id)


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
    mode = os.getenv("RING_INTEGRATION_MODE", "official").lower()
    if mode == "simulator":
        await asyncio.gather(run_ring_simulator(), run_api())
        return
    if mode != "official":
        raise RuntimeError("RING_INTEGRATION_MODE must be 'official' or 'simulator'")

    print("[Ring] Official Partner API mode; waiting for Ring webhooks")
    await run_api()


if __name__ == "__main__":
    asyncio.run(main())
