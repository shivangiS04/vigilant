from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass(frozen=True)
class NormalizedRingEvent:
    event_id: str
    account_id: str
    camera_id: str
    camera_name: str
    type: str
    timestamp: datetime
    confidence: None = None

    def as_event_dict(self, home_id: str) -> dict[str, Any]:
        return {
            "id": self.event_id,
            "home_id": home_id,
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
            "type": self.type,
            "timestamp": self.timestamp.isoformat(),
            "confidence": None,
            "raw_payload": None,
        }


def _normalized_type(event_type: str, subtype: Optional[str] = None) -> Optional[str]:
    kind = event_type
    if event_type == "motion_detected":
        kind = subtype or "motion"
    elif event_type.startswith("motion."):
        kind = event_type.split(".", 1)[1]

    if event_type in {"button_press", "ding"}:
        return "doorbell"
    return {
        "motion": "motion_detected",
        "human": "person_detected",
        "vehicle": "vehicle_detected",
        "animal": "animal_detected",
        "other_motion": "motion_detected",
    }.get(kind)


def normalize_ring_event(
    *,
    event_id: str,
    account_id: str,
    device_id: str,
    event_type: str,
    timestamp_ms: Any,
    device_name: Optional[str] = None,
    subtype: Optional[str] = None,
) -> Optional[NormalizedRingEvent]:
    normalized_type = _normalized_type(event_type, subtype)
    if normalized_type is None:
        return None

    try:
        occurred_at = datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError) as exc:
        raise ValueError("Ring event timestamp must be epoch milliseconds") from exc

    return NormalizedRingEvent(
        event_id=event_id,
        account_id=account_id,
        camera_id=device_id,
        camera_name=device_name or device_id,
        type=normalized_type,
        timestamp=occurred_at.replace(tzinfo=None),
    )


def normalize_webhook_event(payload: dict[str, Any]) -> Optional[NormalizedRingEvent]:
    try:
        event = payload["data"]
        attributes = event["attributes"]
        account_id = payload["meta"]["account_id"]
        device_id = attributes["source"]
        event_id = event["id"]
        event_type = event["type"]
        timestamp_ms = attributes["timestamp"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Malformed Ring webhook payload") from exc

    return normalize_ring_event(
        event_id=event_id,
        account_id=account_id,
        device_id=device_id,
        event_type=event_type,
        timestamp_ms=timestamp_ms,
        subtype=attributes.get("sub_type"),
    )


def normalize_history_event(
    event: dict[str, Any], account_id: str, device_name: Optional[str] = None
) -> Optional[NormalizedRingEvent]:
    try:
        attributes = event["attributes"]
        event_id = event["id"]
        source = event["relationships"]["source"]["data"]["id"]
        event_type = attributes["event_type"]
        timestamp_ms = attributes["start"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Malformed Ring history event") from exc

    return normalize_ring_event(
        event_id=event_id,
        account_id=account_id,
        device_id=source,
        event_type=event_type,
        timestamp_ms=timestamp_ms,
        device_name=device_name,
    )