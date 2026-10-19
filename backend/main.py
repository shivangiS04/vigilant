"""Start Vigilant's API and an explicitly selected development simulator."""

import asyncio
import os
import uvicorn
from backend.api.routes import app
from backend.ring_integration.webhook_simulator import run_simulator

HOME_ID = os.getenv("HOME_ID", "home_001")


async def run_api():
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    print("[API]  http://localhost:8000")
    await server.serve()


async def main():
    mode = os.getenv("RING_INTEGRATION_MODE", "official").lower()
    if mode == "simulator":
        signing_key = os.getenv("RING_HMAC_SIGNING_KEY", "simulator-dev-key")
        print("[Ring] Simulator mode — sending HMAC-signed webhooks to /ring/webhook")
        # Give the API a moment to bind before the simulator starts sending
        api_task = asyncio.create_task(run_api())
        await asyncio.sleep(1.5)
        sim_task = asyncio.create_task(
            run_simulator(signing_key, "http://localhost:8000/ring/webhook")
        )
        await asyncio.gather(api_task, sim_task)
        return
    if mode != "official":
        raise RuntimeError("RING_INTEGRATION_MODE must be 'official' or 'simulator'")

    print("[Ring] Official Partner API mode; waiting for Ring webhooks")
    await run_api()


if __name__ == "__main__":
    asyncio.run(main())
