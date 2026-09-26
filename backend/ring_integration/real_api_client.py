"""
Real Ring API client using the ring_doorbell library.
Requires: pip install ring-doorbell
Env vars: RING_EMAIL, RING_PASSWORD
"""

import asyncio
import os
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class RingDeviceEvent:
    event_id: str
    camera_id: str
    camera_name: str
    type: str
    timestamp: datetime
    confidence: float
    home_id: str


def _map_ring_kind(kind: str) -> str:
    return {
        "motion": "motion_detected",
        "ding": "doorbell",
        "on_demand": "doorbell",
        "person": "person_detected",
        "vehicle": "vehicle_detected",
        "package_delivered": "person_detected",
        "package_retrieved": "person_detected",
        "animal": "animal_detected",
    }.get(kind, "motion_detected")


class RealRingClient:
    """Connect to real Ring API via ring_doorbell library."""

    def __init__(self, email: str, password: str, home_id: str = "home_001"):
        self.email = email
        self.password = password
        self.home_id = home_id
        self._ring = None
        self.connected = False

    async def connect(self) -> bool:
        try:
            from ring_doorbell import Ring, Auth
            from pathlib import Path

            cache_file = Path("/tmp/ring_token.cache")

            # Auth with Ring using OAuth
            auth = Auth("VIGILANT/1.0", None, self._token_update)
            if cache_file.exists():
                import json
                auth = Auth("VIGILANT/1.0", json.loads(cache_file.read_text()), self._token_update)

            self._ring = Ring(auth)

            # Run sync Ring calls in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._ring.update_data)

            self.connected = True
            devices = self._ring.devices()
            total = sum(len(v) for v in devices.values())
            print(f"[Ring] Connected as {self.email} — {total} device(s) found")
            return True

        except ImportError:
            print("[Ring] ring_doorbell library not installed — run: pip install ring-doorbell")
            return False
        except Exception as e:
            print(f"[Ring] Connection failed: {e}")
            self.connected = False
            return False

    def _token_update(self, token):
        from pathlib import Path
        import json
        Path("/tmp/ring_token.cache").write_text(json.dumps(token))

    async def get_events(self, limit: int = 50) -> List[RingDeviceEvent]:
        if not self.connected or not self._ring:
            return []

        try:
            loop = asyncio.get_event_loop()
            devices = await loop.run_in_executor(None, self._ring.devices)

            all_events: List[RingDeviceEvent] = []
            all_devices = []
            for kind_list in devices.values():
                all_devices.extend(kind_list)

            for device in all_devices:
                if not hasattr(device, "history"):
                    continue
                try:
                    history = await loop.run_in_executor(None, lambda d=device: d.history(limit=limit))
                    for ev in history:
                        created = ev.get("created_at", datetime.utcnow().isoformat())
                        all_events.append(RingDeviceEvent(
                            event_id=f"{device.id}_{ev.get('id', 'unknown')}",
                            camera_id=str(device.id),
                            camera_name=device.description.get("device_name", device.id),
                            type=_map_ring_kind(ev.get("kind", "")),
                            timestamp=datetime.fromisoformat(created.replace("Z", "")),
                            confidence=0.95,
                            home_id=self.home_id,
                        ))
                except Exception as e:
                    print(f"[Ring] Could not fetch history for {device.id}: {e}")

            return sorted(all_events, key=lambda x: x.timestamp, reverse=True)

        except Exception as e:
            print(f"[Ring] Error fetching events: {e}")
            return []

    @classmethod
    def from_env(cls, home_id: str = "home_001") -> Optional["RealRingClient"]:
        email = os.getenv("RING_EMAIL")
        password = os.getenv("RING_PASSWORD")
        if not email or not password:
            return None
        return cls(email, password, home_id)
