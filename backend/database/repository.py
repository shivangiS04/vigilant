"""
All DB reads/writes in one place. Routes call these, never touch ORM directly.
"""

from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError

from backend.database.models import (
    Baseline,
    Camera,
    Home,
    Pattern,
    RingAccount,
    RingEvent,
    RingWebhookReceipt,
)


# ------------------------------------------------------------------
# Homes
# ------------------------------------------------------------------

def get_or_create_home(db: Session, home_id: str, address: str = "Unknown") -> Home:
    home = db.query(Home).filter(Home.id == home_id).first()
    if not home:
        home = Home(id=home_id, address=address)
        db.add(home)
        db.flush()
    return home


def get_ring_account(db: Session, account_id: str) -> Optional[RingAccount]:
    return db.query(RingAccount).filter(RingAccount.account_id == account_id).first()


def get_unclaimed_ring_accounts(db: Session) -> List[RingAccount]:
    return db.query(RingAccount).filter(RingAccount.status == "unclaimed").all()


def save_ring_account(db: Session, account_data: dict) -> RingAccount:
    account = get_ring_account(db, account_data["account_id"])
    if account is None:
        account = RingAccount(account_id=account_data["account_id"])
        db.add(account)

    account.access_token_encrypted = account_data["access_token_encrypted"]
    account.refresh_token_encrypted = account_data["refresh_token_encrypted"]
    account.access_token_expires_at = account_data["access_token_expires_at"]
    account.partner_user_id = None
    account.home_id = None
    account.account_identifier = None
    account.status = "unclaimed"
    db.flush()
    return account


def get_webhook_receipt(db: Session, request_id: str) -> Optional[RingWebhookReceipt]:
    return (
        db.query(RingWebhookReceipt)
        .filter(RingWebhookReceipt.request_id == request_id)
        .first()
    )


def save_webhook_receipt(
    db: Session, request_id: str, account_id: str, event_id: str
) -> bool:
    if get_webhook_receipt(db, request_id):
        return False
    db.add(RingWebhookReceipt(request_id=request_id, account_id=account_id, event_id=event_id))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return False
    return True


def mark_webhook_processed(db: Session, request_id: str) -> None:
    receipt = get_webhook_receipt(db, request_id)
    if receipt:
        receipt.processed_at = datetime.utcnow()


def upsert_camera(db: Session, home_id: str, camera_id: str, name: str) -> Camera:
    get_or_create_home(db, home_id)
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if camera is None:
        camera = Camera(id=camera_id, home_id=home_id, name=name)
        db.add(camera)
    else:
        camera.home_id = home_id
        camera.name = name
    db.flush()
    return camera


def get_camera(db: Session, camera_id: str) -> Optional[Camera]:
    return db.query(Camera).filter(Camera.id == camera_id).first()


# ------------------------------------------------------------------
# Events
# ------------------------------------------------------------------

def save_event(db: Session, event_data: dict) -> RingEvent:
    get_or_create_home(db, event_data["home_id"])
    existing = db.query(RingEvent).filter(RingEvent.id == event_data["id"]).first()
    if existing:
        return existing
    ev = RingEvent(
        id=event_data["id"],
        home_id=event_data["home_id"],
        camera_id=event_data.get("camera_id", event_data.get("camera_name", "unknown")),
        type=event_data["type"],
        confidence=event_data.get("confidence"),
        timestamp=datetime.fromisoformat(event_data["timestamp"]),
        raw_payload=event_data,
    )
    db.add(ev)
    return ev


def get_ring_event(db: Session, event_id: str) -> Optional[RingEvent]:
    return db.query(RingEvent).filter(RingEvent.id == event_id).first()


def get_events(db: Session, home_id: str, hours: int = 24, limit: int = 50) -> List[RingEvent]:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    return (
        db.query(RingEvent)
        .filter(RingEvent.home_id == home_id, RingEvent.timestamp >= cutoff)
        .order_by(desc(RingEvent.timestamp))
        .limit(limit)
        .all()
    )


# ------------------------------------------------------------------
# Patterns
# ------------------------------------------------------------------

def save_pattern(db: Session, pattern_data: dict) -> Pattern:
    get_or_create_home(db, pattern_data["home_id"])
    p = Pattern(
        id=pattern_data["id"],
        home_id=pattern_data["home_id"],
        pattern_type=pattern_data["pattern_type"],
        fingerprint=pattern_data.get("fingerprint"),
        salience_score=pattern_data["salience_score"],
        novelty_score=pattern_data.get("novelty_score"),
        adaptation_score=pattern_data.get("adaptation_score"),
        temporal_weight=pattern_data.get("temporal_weight"),
        competition_score=pattern_data.get("competition_score"),
        flagged=pattern_data.get("flagged", False),
        explanation=pattern_data.get("explanation"),
        detected_at=datetime.fromisoformat(pattern_data["detected_at"]),
        event_ids=pattern_data.get("event_ids", []),
    )
    db.add(p)
    return p


def get_patterns(
    db: Session,
    home_id: str,
    days: int = 7,
    flagged_only: bool = False,
    min_salience: float = 0.0,
) -> List[Pattern]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    q = (
        db.query(Pattern)
        .filter(
            Pattern.home_id == home_id,
            Pattern.detected_at >= cutoff,
            Pattern.salience_score >= min_salience,
        )
        .order_by(desc(Pattern.detected_at))
    )
    if flagged_only:
        q = q.filter(Pattern.flagged == True)
    return q.limit(100).all()


def get_pattern_by_id(db: Session, pattern_id: str) -> Optional[Pattern]:
    return db.query(Pattern).filter(Pattern.id == pattern_id).first()


# ------------------------------------------------------------------
# Baseline
# ------------------------------------------------------------------

def upsert_baseline(db: Session, home_id: str, fingerprint: str, pattern_type: str):
    """Increment count if exists, insert if not."""
    get_or_create_home(db, home_id)
    bl = (
        db.query(Baseline)
        .filter(Baseline.home_id == home_id, Baseline.fingerprint == fingerprint)
        .first()
    )
    now = datetime.utcnow()
    if bl:
        bl.occurrence_count += 1
        bl.last_seen = now
    else:
        bl = Baseline(
            home_id=home_id,
            fingerprint=fingerprint,
            pattern_type=pattern_type,
            occurrence_count=1,
            first_seen=now,
            last_seen=now,
        )
        db.add(bl)
    return bl


def get_baseline(db: Session, home_id: str) -> List[Baseline]:
    return db.query(Baseline).filter(Baseline.home_id == home_id).all()


def get_baseline_comparison(db: Session, home_id: str, days: int = 7) -> dict:
    """Return per-day activity vs. historical baseline for the last N days."""
    from sqlalchemy import func

    now = datetime.utcnow()
    start_date = now - timedelta(days=days)

    # Actual event counts for the requested window
    recent_counts = (
        db.query(
            func.date(RingEvent.timestamp).label("date"),
            func.count(RingEvent.id).label("event_count"),
        )
        .filter(RingEvent.home_id == home_id, RingEvent.timestamp >= start_date)
        .group_by(func.date(RingEvent.timestamp))
        .all()
    )

    # Flagged pattern counts for the window
    recent_flags = (
        db.query(
            func.date(Pattern.detected_at).label("date"),
            func.count(Pattern.id).label("flags_count"),
        )
        .filter(
            Pattern.home_id == home_id,
            Pattern.detected_at >= start_date,
            Pattern.flagged == True,
        )
        .group_by(func.date(Pattern.detected_at))
        .all()
    )

    # Historical average (all time, per calendar day)
    all_daily = (
        db.query(
            func.date(RingEvent.timestamp).label("date"),
            func.count(RingEvent.id).label("event_count"),
        )
        .filter(RingEvent.home_id == home_id)
        .group_by(func.date(RingEvent.timestamp))
        .all()
    )

    baseline_avg = (
        sum(r.event_count for r in all_daily) / len(all_daily) if all_daily else 0
    )

    counts_by_date = {str(r.date): r.event_count for r in recent_counts}
    flags_by_date = {str(r.date): r.flags_count for r in recent_flags}

    max_count = max(list(counts_by_date.values()) + [baseline_avg * 1.5, 1])

    days_data = []
    for i in range(days):
        day = start_date + timedelta(days=i)
        date_str = day.strftime("%Y-%m-%d")
        count = counts_by_date.get(date_str, 0)
        flags = flags_by_date.get(date_str, 0)
        days_data.append({
            "date": date_str,
            "day_name": day.strftime("%A"),
            "baseline_activity": round((baseline_avg / max_count) * 100, 1),
            "actual_activity": round((count / max_count) * 100, 1),
            "flags_count": flags,
            "event_count": count,
        })

    return {
        "home_id": home_id,
        "baseline_avg": round(baseline_avg, 1),
        "period_days": days,
        "days": days_data,
    }


def load_baselines_into_engine(db: Session, home_id: str, engine) -> int:
    """Hydrate a MotifEngine from stored baselines on startup."""
    rows = get_baseline(db, home_id)
    for row in rows:
        engine.baseline_patterns[row.fingerprint] = type(
            "BaselinePattern", (),
            {
                "fingerprint": row.fingerprint,
                "count": row.occurrence_count,
                "last_seen": row.last_seen,
                "first_seen": row.first_seen,
            },
        )()
    return len(rows)
