"""
Rule-based explanation engine.
Every sentence is derived from real MOTIF score data and event sequences.
No LLM, no network calls, no external dependencies.
"""

import os
from datetime import datetime, timezone
from typing import Dict, List

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]


def _home_tz() -> ZoneInfo:
    tz_name = os.getenv("HOME_TIMEZONE", "Asia/Kolkata")
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("UTC")


def _fmt_local(iso_ts: str) -> str:
    """Return 'H:MM AM/PM' in the home timezone from an ISO timestamp string."""
    try:
        dt = datetime.fromisoformat(iso_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(_home_tz())
        return local.strftime("%-I:%M %p")
    except Exception:
        return iso_ts[:16]


def _span_minutes(events: list) -> int:
    """Minutes between first and last event in the list."""
    if len(events) < 2:
        return 0
    try:
        t0 = datetime.fromisoformat(events[0]["timestamp"])
        t1 = datetime.fromisoformat(events[-1]["timestamp"])
        return max(0, int((t1 - t0).total_seconds() / 60))
    except Exception:
        return 0


class RuleBasedExplainer:
    """
    Deterministic pattern explainer. Every sentence is backed by real MOTIF
    score data: novelty (how rare vs. baseline), adaptation (how often seen),
    and the actual event sequence. No LLM, no network calls.
    """

    def generate_explanation(self, pattern_data: Dict) -> str:
        ptype = pattern_data.get("pattern_type", "standard_activity")
        events = pattern_data.get("events", [])
        novelty = float(pattern_data.get("novelty_score", 5.0))
        adaptation = float(pattern_data.get("adaptation_score", 5.0))
        salience = float(pattern_data.get("salience_score", 5.0))

        cameras = [e.get("camera", "unknown") for e in events]
        types = [e.get("type", "unknown") for e in events]
        first_time = _fmt_local(events[0]["timestamp"]) if events else "unknown time"
        span = _span_minutes(events)

        core = self._core_sentence(ptype, cameras, types, first_time, span, events)
        signal = self._signal_sentence(novelty, adaptation, salience)
        if signal:
            return f"{core} {signal}"
        return core

    def generate_daily_summary(self, patterns: List[Dict], date: str, location: str = "") -> str:
        if not patterns:
            return f"No patterns detected on {date}."

        total = len(patterns)
        flagged = [p for p in patterns if p.get("flagged")]
        type_counts: Dict[str, int] = {}
        for p in patterns:
            t = p.get("pattern_type", "standard_activity")
            type_counts[t] = type_counts.get(t, 0) + 1

        lines = [f"{total} pattern{'s' if total != 1 else ''} detected on {date}."]
        if flagged:
            top = max(flagged, key=lambda p: float(p.get("salience_score", 0)))
            top_type = top.get("pattern_type", "unknown").replace("_", " ")
            top_sal = float(top.get("salience_score", 0))
            lines.append(
                f"{len(flagged)} flagged for attention — "
                f"highest: {top_type} ({top_sal:.1f}/10)."
            )
        sorted_types = sorted(type_counts.items(), key=lambda x: -x[1])
        type_parts = [f"{count} {t.replace('_', ' ')}" for t, count in sorted_types[:4]]
        lines.append("Breakdown: " + ", ".join(type_parts) + ".")
        return " ".join(lines)

    # ------------------------------------------------------------------
    # Pattern-specific core sentences
    # ------------------------------------------------------------------

    def _core_sentence(
        self,
        ptype: str,
        cameras: list,
        types: list,
        first_time: str,
        span: int,
        events: list,
    ) -> str:
        cam0 = cameras[0].replace("_", " ") if cameras else "a camera"
        cam_last = cameras[-1].replace("_", " ") if cameras else cam0
        motion_count = types.count("motion_detected")

        if ptype == "rapid_return":
            span_str = f"{span} minute{'s' if span != 1 else ''}"
            return (
                f"Someone returned to {cam_last} at {first_time} — "
                f"just {span_str} after the start of this sequence, "
                f"far shorter than the learned return time."
            )
        if ptype == "unusual_entrance":
            return (
                f"First activity at {cam0} at {first_time} — "
                f"this entrance rarely appears first in the learned baseline."
            )
        if ptype == "loitering":
            span_str = f"{span} minute{'s' if span != 1 else ''}"
            count_str = str(motion_count) if motion_count > 0 else "Repeated"
            return (
                f"{count_str} motion event{'s' if motion_count != 1 else ''} at {cam0} "
                f"over {span_str} starting at {first_time} — "
                f"sustained movement without a clear departure."
            )
        if ptype == "late_night_activity":
            return (
                f"Person detected at {cam0} at {first_time} — "
                f"between 11 PM and 5 AM local time, outside the home's usual activity window."
            )
        if ptype == "delivery":
            vehicle_cam = next(
                (
                    e.get("camera", cameras[0]).replace("_", " ")
                    for e in events
                    if e.get("type") == "vehicle_detected"
                ),
                cam0,
            )
            person_cam = next(
                (
                    e.get("camera", cameras[0]).replace("_", " ")
                    for e in events
                    if e.get("type") == "person_detected"
                ),
                cam0,
            )
            if vehicle_cam != person_cam:
                return (
                    f"Vehicle at {vehicle_cam} followed by a person at "
                    f"{person_cam} at {first_time} — matches a delivery pattern."
                )
            return (
                f"Vehicle and person detected at {cam0} at {first_time} "
                f"— matches a delivery pattern."
            )
        if ptype == "multi_camera_activity":
            unique = list(dict.fromkeys(cameras))
            cam_str = ", ".join(c.replace("_", " ") for c in unique[:3])
            return (
                f"Activity across {len(unique)} camera{'s' if len(unique) != 1 else ''} "
                f"({cam_str}) in a short window starting at {first_time} — "
                f"unusually wide spread."
            )
        if ptype == "late_first_activity":
            return (
                f"First movement of the day at {cam0} detected at {first_time} — "
                f"later than the usual morning pattern. Consider a check-in."
            )
        # standard_activity fallback
        return f"Activity at {cam0} at {first_time} — consistent with the learned baseline."

    # ------------------------------------------------------------------
    # Score-based signal context
    # ------------------------------------------------------------------

    def _signal_sentence(self, novelty: float, adaptation: float, salience: float) -> str:
        parts = []
        if novelty >= 8.0:
            parts.append("No matching sequence in the learned baseline")
        elif novelty >= 6.0:
            parts.append("Rarely seen in the baseline")
        elif novelty >= 4.0:
            parts.append("Seen occasionally in the baseline")

        if adaptation >= 9.0:
            parts.append("first time this sequence has been recorded")
        elif adaptation >= 7.0:
            parts.append("seen only once or twice before")

        if not parts:
            return ""
        sentence = parts[0]
        if len(parts) > 1:
            sentence += " — " + parts[1]
        sentence += f" (salience {salience:.1f}/10)."
        return sentence
