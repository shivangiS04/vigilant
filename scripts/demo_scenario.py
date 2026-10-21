#!/usr/bin/env python3
"""
VIGILANT demo data builder — Phase 2.

Sends HMAC-signed webhooks through the real /ring/webhook code path to build
a believable 7-day home history, then adds three flagged demo events for the
recording session.

Usage:
    # Start backend first (simulator mode):
    #   RING_INTEGRATION_MODE=simulator RING_HMAC_SIGNING_KEY=demo-key-32chars \
    #   DATABASE_URL=sqlite:///./demo.db uvicorn api.index:app --reload --port 8000
    #
    # Then run this script:
    python scripts/demo_scenario.py --reset

    # With a different backend:
    python scripts/demo_scenario.py --reset --backend http://localhost:8000

Required env vars (or pass as args):
    RING_HMAC_SIGNING_KEY   Shared HMAC key (matches the running backend)
    HOME_TIMEZONE           IANA tz name (default: Asia/Kolkata)
    HOME_ID                 Home ID (default: home_001)
"""

import argparse
import hashlib
import hmac
import json
import os
import random
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    import httpx
except ImportError:
    sys.exit("httpx is required: pip install httpx")

try:
    from zoneinfo import ZoneInfo
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    except ImportError:
        sys.exit("zoneinfo or backports.zoneinfo is required")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ACCOUNT_ID  = "sim_account_001"
WINDOW_SIZE = 5   # matches RingEventPipeline.window_size

# Camera IDs.  Use friendly names directly as camera IDs so the MOTIF engine's
# hard-coded camera name checks ("side_door", "front_door" …) work correctly and
# fingerprints produced by the pipeline match fingerprints produced in this script.
CAMERAS = {
    "front_door":  "front_door",
    "driveway":    "driveway",
    "side_door":   "side_door",
    "backyard":    "backyard",
}


# ---------------------------------------------------------------------------
# HMAC signing (identical to verify_webhook_signature in security.py)
# ---------------------------------------------------------------------------

def _sign(raw_body: bytes, key: str) -> str:
    digest = hmac.new(key.encode(), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _build_payload(
    camera_id: str,
    event_type: str,
    ts_dt: datetime,
    sub_type: Optional[str] = None,
    event_id: Optional[str] = None,
) -> dict:
    """Build a Ring Partner API v1.1 webhook payload with a custom timestamp."""
    ts_ms = int(ts_dt.timestamp() * 1000)
    eid = event_id or f"demo_{camera_id}_{ts_ms}_{random.randint(1000, 9999)}"
    return {
        "meta": {
            "version": "1.1",
            "time": int(time.time() * 1000),
            "request_id": str(uuid.uuid4()),
            "account_id": ACCOUNT_ID,
        },
        "data": {
            "id": eid,
            "type": event_type,
            "attributes": {
                "source": camera_id,
                "timestamp": ts_ms,
                **({"sub_type": sub_type} if sub_type else {}),
            },
        },
    }


def _send(client: httpx.Client, payload: dict, url: str, key: str) -> int:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    sig  = _sign(raw, key)
    r = client.post(
        url,
        content=raw,
        headers={"Content-Type": "application/json", "X-Signature": sig},
        timeout=15.0,
    )
    return r.status_code


# ---------------------------------------------------------------------------
# Event sequence builders
# ---------------------------------------------------------------------------

def _ts(base_day: datetime, hour: int, minute: int, second: int = 0) -> datetime:
    """Return a timezone-aware datetime on base_day at the given local time."""
    return base_day.replace(hour=hour, minute=minute, second=second, microsecond=0)


def routine_day_events(day: datetime) -> list:
    """
    One normal day at home (all times in home local timezone):
      07:45  front_door  motion          (outdoor check before leaving)
      08:15  front_door  person          (morning departure)
      08:16  front_door  motion          (door motion as person leaves)
      10:05  backyard    motion          (wind / animal — no sub_type)
      12:30  driveway    vehicle         (delivery truck)
      12:32  front_door  button_press    (delivery person rings bell)
      12:33  front_door  person (human)  (resident answers door)
      15:10  backyard    motion          (afternoon animal)
      18:15  front_door  motion          (arrival motion)
      18:17  front_door  person (human)  (evening return)
    """
    return [
        (_ts(day,  7, 45), "front_door",  "motion_detected", None),
        (_ts(day,  8, 15), "front_door",  "motion_detected", "human"),
        (_ts(day,  8, 16), "front_door",  "motion_detected", None),
        (_ts(day, 10,  5), "backyard",    "motion_detected", None),
        (_ts(day, 12, 30), "driveway",    "motion_detected", "vehicle"),
        (_ts(day, 12, 32), "front_door",  "button_press",    None),
        (_ts(day, 12, 33), "front_door",  "motion_detected", "human"),
        (_ts(day, 15, 10), "backyard",    "motion_detected", None),
        (_ts(day, 18, 15), "front_door",  "motion_detected", None),
        (_ts(day, 18, 17), "front_door",  "motion_detected", "human"),
    ]


def rapid_return_sequence(day: datetime) -> list:
    """
    Person leaves via front_door at 08:15, returns via side_door 8 min later.
    Window of 5 events that the MOTIF pipeline will score as rapid_return.
    """
    return [
        (_ts(day,  8, 13), "front_door",  "motion_detected", None),
        (_ts(day,  8, 15), "front_door",  "motion_detected", "human"),   # departure
        (_ts(day,  8, 16), "front_door",  "motion_detected", None),
        (_ts(day,  8, 23), "side_door",   "motion_detected", "human"),   # rapid return
        (_ts(day,  8, 24), "side_door",   "motion_detected", None),
    ]


def unusual_entrance_sequence(day: datetime) -> list:
    """
    Person enters via side_door at 23:15 — odd hour, non-primary camera first.
    Exactly one person_detected so rapid_return (requires ≥2) doesn't fire first.
    """
    return [
        (_ts(day, 23, 12), "side_door",   "motion_detected", None),
        (_ts(day, 23, 13), "side_door",   "motion_detected", None),
        (_ts(day, 23, 15), "side_door",   "motion_detected", "human"),   # unusual entrance
        (_ts(day, 23, 16), "side_door",   "motion_detected", None),
        (_ts(day, 23, 17), "side_door",   "motion_detected", None),
    ]


def late_first_activity_sequence(day: datetime) -> list:
    """
    No activity until 14:30 — caretaking scenario (late first activity of day).
    Only motion events (no person), front_door.  Triggers late_first_activity.
    Must be sent AFTER /demo/reset-daily to ensure daily_events is empty.
    """
    return [
        (_ts(day, 14, 28), "front_door",  "motion_detected", None),
        (_ts(day, 14, 29), "front_door",  "motion_detected", None),
        (_ts(day, 14, 30), "front_door",  "motion_detected", None),
        (_ts(day, 14, 31), "front_door",  "motion_detected", None),
        (_ts(day, 14, 32), "front_door",  "motion_detected", None),
    ]


# ---------------------------------------------------------------------------
# DB stats (via the API — no direct DB access needed)
# ---------------------------------------------------------------------------

def _api_get(client: httpx.Client, url: str) -> dict:
    r = client.get(url, timeout=10.0)
    r.raise_for_status()
    return r.json()


def report_counts(client: httpx.Client, base: str, home_id: str) -> dict:
    events   = _api_get(client, f"{base}/events?home_id={home_id}&hours=168&limit=200")
    patterns = _api_get(client, f"{base}/patterns?home_id={home_id}&days=7")
    baseline = _api_get(client, f"{base}/baseline?home_id={home_id}")
    total_e  = len(events)
    total_p  = len(patterns)
    flagged  = sum(1 for p in patterns if p["flagged"])
    suppressed = total_p - flagged
    noise_pct = round((suppressed / total_p * 100)) if total_p > 0 else 0
    return {
        "raw_events_7d":      total_e,
        "patterns_7d":        total_p,
        "flagged":            flagged,
        "noise_suppressed":   suppressed,
        "noise_suppression_%": noise_pct,
        "baseline_entries":   baseline.get("pattern_count", 0),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="VIGILANT demo data builder")
    parser.add_argument("--reset",   action="store_true", help="Wipe all demo data first")
    parser.add_argument("--backend", default=os.getenv("WEBHOOK_URL", "http://localhost:8000"),
                        help="Backend base URL (default: http://localhost:8000)")
    parser.add_argument("--key",     default=os.getenv("RING_HMAC_SIGNING_KEY", ""),
                        help="HMAC signing key (must match RING_HMAC_SIGNING_KEY on the server)")
    parser.add_argument("--home",    default=os.getenv("HOME_ID", "home_001"),
                        help="Home ID (default: home_001)")
    parser.add_argument("--tz",      default=os.getenv("HOME_TIMEZONE", "Asia/Kolkata"),
                        help="Home timezone (default: Asia/Kolkata)")
    args = parser.parse_args()

    if not args.key:
        sys.exit(
            "ERROR: RING_HMAC_SIGNING_KEY not set.\n"
            "  export RING_HMAC_SIGNING_KEY=demo-key-32chars\n"
            "  (Must match the value the running backend was started with.)"
        )

    tz   = ZoneInfo(args.tz)
    base = args.backend.rstrip("/")
    wurl = f"{base}/ring/webhook"

    print(f"\n{'='*60}")
    print(f"VIGILANT demo scenario builder")
    print(f"  Backend : {base}")
    print(f"  Home    : {args.home}")
    print(f"  TZ      : {args.tz}")
    print(f"{'='*60}\n")

    with httpx.Client() as client:
        # ------------------------------------------------------------------
        # 0. Verify backend is reachable
        # ------------------------------------------------------------------
        try:
            health = _api_get(client, f"{base}/health")
        except Exception as exc:
            sys.exit(f"Backend not reachable at {base}: {exc}\nIs the server running?")

        mode = health.get("features", {}).get("ring_integration_mode", "?")
        if mode != "simulator":
            sys.exit(
                f"Backend is in mode='{mode}' — demo scenario requires simulator mode.\n"
                f"Start with: RING_INTEGRATION_MODE=simulator"
            )
        print(f"Backend OK  (mode={mode})\n")

        # ------------------------------------------------------------------
        # 1. Reset if requested
        # ------------------------------------------------------------------
        if args.reset:
            print("Resetting all demo data…")
            r = client.post(f"{base}/demo/reset?home_id={args.home}", timeout=15.0)
            if r.status_code != 200:
                sys.exit(f"Reset failed: {r.status_code} {r.text}")
            d = r.json()["deleted"]
            print(f"  Cleared: {d['events']} events, {d['patterns']} patterns, "
                  f"{d['baselines']} baselines, {d['receipts']} receipts\n")

        # ------------------------------------------------------------------
        # 2. Seed the simulator account
        # ------------------------------------------------------------------
        print("Seeding simulator account…")
        r = client.post(
            f"{base}/ring/simulator/seed-account",
            json={"account_id": ACCOUNT_ID, "home_id": args.home},
            timeout=10.0,
        )
        if r.status_code != 200:
            sys.exit(f"Account seed failed: {r.status_code} {r.text}")
        print(f"  Account {ACCOUNT_ID} → home {args.home}\n")

        # ------------------------------------------------------------------
        # 3. Build 7-day baseline (days -7 through -1)
        # ------------------------------------------------------------------
        now_local = datetime.now(tz)
        today_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

        print("Sending 7-day baseline events…")
        total_sent = 0
        errors     = 0
        for days_back in range(7, 0, -1):   # 7, 6, 5, 4, 3, 2, 1
            day_local = today_local - timedelta(days=days_back)

            if days_back == 1:
                # Yesterday: normal routine + rapid_return + unusual_entrance
                sequences = (
                    routine_day_events(day_local)
                    + rapid_return_sequence(day_local)
                    + unusual_entrance_sequence(day_local)
                )
            else:
                sequences = routine_day_events(day_local)

            label = f"  Day -{days_back} ({day_local.strftime('%a %d %b')}): "
            sent_day = 0
            for (ts_local, cam_id, ring_type, sub_type) in sequences:
                ts_utc = ts_local.astimezone(timezone.utc)
                payload = _build_payload(cam_id, ring_type, ts_utc, sub_type)
                code = _send(client, payload, wurl, args.key)
                if code in (200, 202):
                    sent_day += 1
                else:
                    errors += 1
            total_sent += sent_day
            print(f"{label}{sent_day} events → webhook ({errors} errors so far)")

            # Small pause so background tasks can process before the next day
            time.sleep(0.4)

        print(f"\n  Total sent: {total_sent} events, {errors} errors")

        # ------------------------------------------------------------------
        # 4. Mark non-flagged patterns as 'normal' to build the baseline
        # ------------------------------------------------------------------
        print("\nBuilding baseline from non-flagged patterns…")
        time.sleep(1.5)   # let background tasks finish
        patterns = _api_get(client, f"{base}/patterns?home_id={args.home}&days=7")
        normal_fed = 0
        for p in patterns:
            if not p["flagged"]:
                r = client.post(
                    f"{base}/patterns/{p['id']}/feedback",
                    json={"pattern_id": p["id"], "feedback": "normal", "home_id": args.home},
                    timeout=10.0,
                )
                if r.status_code == 200:
                    normal_fed += 1
        print(f"  Marked {normal_fed} patterns as 'normal' → baseline strengthened")

        # ------------------------------------------------------------------
        # 5. Reset daily state so today looks like a fresh day
        # ------------------------------------------------------------------
        print("\nResetting daily MOTIF state (clearing daily_events + pipeline window)…")
        r = client.post(f"{base}/demo/reset-daily", timeout=10.0)
        if r.status_code != 200:
            print(f"  Warning: reset-daily returned {r.status_code}")
        else:
            print(f"  OK — {r.json()['cleared']}")

        # ------------------------------------------------------------------
        # 6. Today's demo events
        # ------------------------------------------------------------------
        print("\nSending today's demo events…\n")
        demo_sequences = [
            ("Rapid Return",         rapid_return_sequence(today_local)),
            ("Unusual Entrance",     unusual_entrance_sequence(today_local)),
            ("Late First Activity",  late_first_activity_sequence(today_local)),
        ]

        # For late_first_activity: we need a completely fresh day (no rapid_return
        # events already in the pipeline window). Reset daily state before it.
        for i, (label, seq) in enumerate(demo_sequences):
            if label == "Late First Activity":
                # Reset daily so this appears as the first activity of the day
                client.post(f"{base}/demo/reset-daily", timeout=10.0)
                time.sleep(0.3)

            print(f"  → {label}")
            for (ts_local, cam_id, ring_type, sub_type) in seq:
                ts_utc = ts_local.astimezone(timezone.utc)
                payload = _build_payload(cam_id, ring_type, ts_utc, sub_type)
                code = _send(client, payload, wurl, args.key)
                cam_name = CAMERAS.get(cam_id, cam_id)
                disp_type = sub_type or ring_type
                print(f"     {ts_local.strftime('%H:%M')} {cam_name:12s} {disp_type:18s} → HTTP {code}")
            time.sleep(0.8)

        # ------------------------------------------------------------------
        # 7. Wait for background tasks, then report
        # ------------------------------------------------------------------
        print("\nWaiting for pipeline to finish…")
        time.sleep(2.5)

        counts = report_counts(client, base, args.home)

        print(f"\n{'='*60}")
        print("DEMO DATA REPORT")
        print(f"{'='*60}")
        print(f"  Raw events (last 7 days): {counts['raw_events_7d']}")
        print(f"  Patterns detected:        {counts['patterns_7d']}")
        print(f"  Flagged for attention:    {counts['flagged']}")
        print(f"  Noise-suppressed:         {counts['noise_suppressed']}")
        print(f"  Noise suppression:        {counts['noise_suppression_%']}%")
        print(f"  Baseline entries learned: {counts['baseline_entries']}")
        print(f"{'='*60}\n")

        # ------------------------------------------------------------------
        # 8. Feedback demo: before/after scores on rapid_return
        # ------------------------------------------------------------------
        print("Feedback demo — rapid_return before/after 'This was normal':")
        patterns_now = _api_get(client, f"{base}/patterns?home_id={args.home}&days=1")
        rr = next(
            (p for p in patterns_now if p["pattern_type"] == "rapid_return" and p["flagged"]),
            None,
        )
        if rr:
            score_before = rr["salience_score"]
            print(f"  Before feedback: salience = {score_before:.1f}/10  (flagged)")
            # Submit 'normal' feedback
            r = client.post(
                f"{base}/patterns/{rr['id']}/feedback",
                json={"pattern_id": rr["id"], "feedback": "normal", "home_id": args.home},
                timeout=10.0,
            )
            msg = r.json().get("effect", "—") if r.status_code == 200 else r.text

            def _norm_type(ring_type: str, sub_type: Optional[str]) -> str:
                if sub_type == "human":   return "person_detected"
                if sub_type == "vehicle": return "vehicle_detected"
                if ring_type == "button_press": return "doorbell"
                return "motion_detected"

            # Re-score a similar sequence through /patterns/score to show the drop.
            # camera field must match what the pipeline stored (camera_id = friendly name).
            # Timestamps must be naive UTC strings (what MotifEngine expects).
            rescore_events = [
                {
                    "camera":     e[1],   # e.g. "front_door" — same as pipeline stores
                    "type":       _norm_type(e[2], e[3]),
                    "timestamp":  e[0].astimezone(timezone.utc).replace(tzinfo=None).isoformat(),
                    "confidence": 0.9,
                }
                for e in rapid_return_sequence(today_local)
            ]
            r2 = client.post(
                f"{base}/patterns/score",
                json={"home_id": args.home, "events": rescore_events},
                timeout=15.0,
            )
            if r2.status_code == 200:
                score_after = r2.json()["final_salience"]
                flagged_after = r2.json()["flagged"]
                print(f"  After feedback:  salience = {score_after:.1f}/10  "
                      f"(flagged={flagged_after}) — {msg}")
            else:
                print(f"  Re-score failed: {r2.status_code}")
        else:
            print("  No rapid_return pattern found in today's data (check pipeline logs).")

        print(f"\nDone. Use these numbers in your voiceover:")
        print(f"  '{counts['raw_events_7d']} raw events, {counts['patterns_7d']} patterns, "
              f"{counts['flagged']} flagged — {counts['noise_suppression_%']}% noise suppressed'")


if __name__ == "__main__":
    main()
