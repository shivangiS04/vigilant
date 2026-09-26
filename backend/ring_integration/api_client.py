import asyncio
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import AsyncGenerator, Callable, List, Optional


@dataclass
class RingEvent:
    event_id: str
    camera_id: str
    camera_name: str
    type: str           # person_detected | motion_detected | vehicle_detected | doorbell
    timestamp: datetime
    confidence: float   # 0.0 - 1.0
    home_id: str


class RingAPIClient:
    """
    Ring API client with built-in simulator for development.

    Usage:
        client = RingAPIClient(token="YOUR_TOKEN")
        async for event in client.stream_events():
            process(event)

    Development (no Ring device needed):
        client = RingAPIClient.simulator()
        async for event in client.stream_events():
            process(event)
    """

    POLL_INTERVAL_SECONDS = 180  # Ring rate limit: ~100 req/hour → 1 req/36s safe margin
    DEV_POLL_INTERVAL_SECONDS = 5  # fast mode for local dev

    def __init__(self, token: str, home_id: str = "home_001"):
        self._token = token
        self._home_id = home_id
        self._simulate = False
        self._dev_mode = False
        self._event_handlers: List[Callable] = []

    @classmethod
    def simulator(cls, home_id: str = "home_001", dev_mode: bool = True) -> "RingAPIClient":
        client = cls(token="SIMULATOR", home_id=home_id)
        client._simulate = True
        client._dev_mode = dev_mode
        return client

    # ------------------------------------------------------------------
    # Event streaming
    # ------------------------------------------------------------------

    async def stream_events(self) -> AsyncGenerator[RingEvent, None]:
        """Yield Ring events as they arrive. Handles rate limiting internally."""
        interval = self.DEV_POLL_INTERVAL_SECONDS if self._dev_mode else self.POLL_INTERVAL_SECONDS
        while True:
            try:
                events = await self._fetch_events()
                for event in events:
                    yield event
                    for handler in self._event_handlers:
                        await handler(event)
                await asyncio.sleep(interval)
            except RateLimitError:
                await asyncio.sleep(self.POLL_INTERVAL_SECONDS * 2)
            except RingAuthError:
                raise
            except Exception:
                await asyncio.sleep(60)

    def on_event(self, handler: Callable):
        """Register a callback for new events."""
        self._event_handlers.append(handler)
        return handler

    # ------------------------------------------------------------------
    # Fetch (real or simulated)
    # ------------------------------------------------------------------

    async def _fetch_events(self) -> List[RingEvent]:
        if self._simulate:
            return self._simulate_events()
        return await self._fetch_real_events()

    async def _fetch_real_events(self) -> List[RingEvent]:
        """
        Replace with actual Ring API call.
        Ring doesn't have a public API — use ring_doorbell library or
        reverse-engineered endpoints. For hackathon, simulator is fine.
        """
        raise NotImplementedError(
            "Real Ring API integration not yet implemented. "
            "Use RingAPIClient.simulator() for development."
        )

    def _simulate_events(self) -> List[RingEvent]:
        """Generate realistic fake Ring events for development."""
        now = datetime.utcnow()
        hour = now.hour

        # probability of events by time of day
        if 7 <= hour <= 9 or 17 <= hour <= 19:
            event_probability = 0.8  # morning/evening rush
        elif 22 <= hour or hour <= 6:
            event_probability = 0.1  # night
        else:
            event_probability = 0.4

        if random.random() > event_probability:
            return []

        cameras = [
            ("cam_001", "front_door"),
            ("cam_002", "driveway"),
            ("cam_003", "side_door"),
            ("cam_004", "backyard"),
        ]

        event_types = [
            ("person_detected", 0.5),
            ("motion_detected", 0.3),
            ("vehicle_detected", 0.15),
            ("doorbell", 0.05),
        ]

        camera_id, camera_name = random.choice(cameras)
        event_type = random.choices(
            [t for t, _ in event_types],
            weights=[w for _, w in event_types],
        )[0]

        return [
            RingEvent(
                event_id=f"sim_{int(now.timestamp())}_{random.randint(1000, 9999)}",
                camera_id=camera_id,
                camera_name=camera_name,
                type=event_type,
                timestamp=now,
                confidence=random.uniform(0.75, 0.99),
                home_id=self._home_id,
            )
        ]

    # ------------------------------------------------------------------
    # Parse raw Ring API response → RingEvent
    # ------------------------------------------------------------------

    @staticmethod
    def parse_event(raw: dict, home_id: str) -> RingEvent:
        return RingEvent(
            event_id=raw.get("id", ""),
            camera_id=raw.get("doorbot_id", ""),
            camera_name=raw.get("description", {}).get("device_name", "unknown"),
            type=_map_ring_event_type(raw.get("kind", "")),
            timestamp=datetime.fromisoformat(raw.get("created_at", datetime.utcnow().isoformat())),
            confidence=raw.get("confidence", 1.0),
            home_id=home_id,
        )


def _map_ring_event_type(ring_kind: str) -> str:
    mapping = {
        "motion": "motion_detected",
        "ding": "doorbell",
        "on_demand": "doorbell",
        "person": "person_detected",
        "vehicle": "vehicle_detected",
        "package_delivered": "person_detected",
        "package_retrieved": "person_detected",
    }
    return mapping.get(ring_kind, "motion_detected")


class RateLimitError(Exception):
    pass


class RingAuthError(Exception):
    pass


# ------------------------------------------------------------------
# Smoke test
# ------------------------------------------------------------------
if __name__ == "__main__":
    async def main():
        client = RingAPIClient.simulator()

        @client.on_event
        async def handle(event: RingEvent):
            print(f"  → handler got: {event.type} on {event.camera_name}")

        print("Simulating 3 poll cycles...")
        count = 0
        async for event in client.stream_events():
            print(f"[{event.timestamp.strftime('%H:%M:%S')}] {event.camera_name}: {event.type} ({event.confidence:.0%})")
            count += 1
            if count >= 5:
                break

    asyncio.run(main())
