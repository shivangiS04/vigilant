"""
FastAPI routes for VIGILANT dashboard.
All state is persisted to SQLite (dev) or Postgres (prod).
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List, Optional
import uuid

from backend.motif_engine.motif_core import MotifEngine, RingEvent as MotifRingEvent
from backend.bedrock_integration.explanation_generator import ExplanationGenerator
from backend.database.session import get_db, init_db
from backend.database import repository as repo

app = FastAPI(title="VIGILANT API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

motif = MotifEngine()
bedrock = ExplanationGenerator()


@app.on_event("startup")
def startup():
    init_db()
    # hydrate MOTIF engine from stored baselines
    with get_db() as db:
        count = repo.load_baselines_into_engine(db, "home_001", motif)
        if count:
            print(f"[VIGILANT] Loaded {count} baseline patterns from DB")


# ------------------------------------------------------------------
# Models
# ------------------------------------------------------------------

class EventOut(BaseModel):
    id: str
    camera_name: str
    type: str
    confidence: float
    timestamp: str
    home_id: str

    class Config:
        from_attributes = True


class PatternOut(BaseModel):
    id: str
    pattern_type: str
    salience_score: float
    novelty_score: Optional[float] = None
    adaptation_score: Optional[float] = None
    flagged: bool
    explanation: Optional[str] = None
    detected_at: str
    event_count: int

    class Config:
        from_attributes = True


class ScoreRequest(BaseModel):
    home_id: str
    events: List[dict]


class ScoreResponse(BaseModel):
    pattern_type: str
    novelty: float
    adaptation: float
    temporal_weight: float
    competition: float
    final_salience: float
    flagged: bool
    explanation: str


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.get("/events")
def get_events(
    home_id: str = Query("home_001"),
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(50, ge=1, le=200),
):
    with get_db() as db:
        rows = repo.get_events(db, home_id, hours, limit)
        return [
            {
                "id": r.id,
                "camera_name": r.camera_id,
                "type": r.type,
                "confidence": r.confidence,
                "timestamp": r.timestamp.isoformat(),
                "home_id": r.home_id,
            }
            for r in rows
        ]


@app.get("/patterns")
def get_patterns(
    home_id: str = Query("home_001"),
    days: int = Query(7, ge=1, le=30),
    flagged_only: bool = Query(False),
    min_salience: float = Query(0.0, ge=0, le=10),
):
    with get_db() as db:
        rows = repo.get_patterns(db, home_id, days, flagged_only, min_salience)
        return [_pattern_to_dict(r) for r in rows]


@app.get("/patterns/{pattern_id}")
def get_pattern(pattern_id: str):
    with get_db() as db:
        row = repo.get_pattern_by_id(db, pattern_id)
        if not row:
            raise HTTPException(status_code=404, detail="Pattern not found")
        return _pattern_to_dict(row)


@app.post("/patterns/score", response_model=ScoreResponse)
def score_pattern(req: ScoreRequest):
    motif_events = [
        MotifRingEvent(
            camera=e["camera"],
            type=e["type"],
            timestamp=datetime.fromisoformat(e["timestamp"]),
            confidence=e.get("confidence", 1.0),
        )
        for e in req.events
    ]

    score = motif.score_pattern(motif_events)
    fingerprint = motif._fingerprint(motif_events)

    pattern_data = {
        "pattern_type": score.pattern_type,
        "confidence": sum(e.get("confidence", 1.0) for e in req.events) / len(req.events),
        "novelty_score": score.novelty,
        "salience_score": score.final_salience,
        "events": req.events,
    }

    if score.flagged:
        explanation = bedrock.generate_explanation(pattern_data)
    else:
        explanation = "Pattern within normal parameters."

    pattern_id = str(uuid.uuid4())
    with get_db() as db:
        repo.save_pattern(db, {
            "id": pattern_id,
            "home_id": req.home_id,
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
            "event_ids": [e.get("id", "") for e in req.events],
        })

        # auto-learn: low-salience patterns are "normal" — feed into baseline
        if score.final_salience < 4.0:
            repo.upsert_baseline(db, req.home_id, fingerprint, score.pattern_type)
            motif.add_baseline(motif_events)

    return ScoreResponse(
        pattern_type=score.pattern_type,
        novelty=score.novelty,
        adaptation=score.adaptation,
        temporal_weight=score.temporal_weight,
        competition=score.competition,
        final_salience=score.final_salience,
        flagged=score.flagged,
        explanation=explanation,
    )


@app.get("/baseline")
def get_baseline(home_id: str = Query("home_001")):
    with get_db() as db:
        rows = repo.get_baseline(db, home_id)
        return {
            "home_id": home_id,
            "pattern_count": len(rows),
            "patterns": [
                {
                    "fingerprint": r.fingerprint,
                    "pattern_type": r.pattern_type,
                    "count": r.occurrence_count,
                    "last_seen": r.last_seen.isoformat() if r.last_seen else None,
                }
                for r in rows
            ],
        }


@app.post("/demo/seed")
def seed_demo_data(home_id: str = Query("home_001")):
    now = datetime.utcnow()

    demo_events = [
        {"id": "demo_e1",  "camera_id": "front_door",  "type": "person_detected",  "confidence": 0.95, "timestamp": (now - timedelta(hours=2, minutes=5)).isoformat(),  "home_id": home_id},
        {"id": "demo_e2",  "camera_id": "front_door",  "type": "motion_detected",  "confidence": 0.91, "timestamp": (now - timedelta(hours=2, minutes=4)).isoformat(),  "home_id": home_id},
        {"id": "demo_e3",  "camera_id": "driveway",    "type": "vehicle_detected", "confidence": 0.88, "timestamp": (now - timedelta(hours=1, minutes=45)).isoformat(), "home_id": home_id},
        {"id": "demo_e4",  "camera_id": "side_door",   "type": "person_detected",  "confidence": 0.90, "timestamp": (now - timedelta(hours=1, minutes=30)).isoformat(), "home_id": home_id},
        {"id": "demo_e5",  "camera_id": "front_door",  "type": "doorbell",         "confidence": 1.00, "timestamp": (now - timedelta(minutes=45)).isoformat(),          "home_id": home_id},
        {"id": "demo_e6",  "camera_id": "front_door",  "type": "person_detected",  "confidence": 0.93, "timestamp": (now - timedelta(minutes=44)).isoformat(),          "home_id": home_id},
        {"id": "demo_e7",  "camera_id": "backyard",    "type": "motion_detected",  "confidence": 0.78, "timestamp": (now - timedelta(minutes=20)).isoformat(),          "home_id": home_id},
        {"id": "demo_e8",  "camera_id": "side_door",   "type": "person_detected",  "confidence": 0.86, "timestamp": (now - timedelta(minutes=8)).isoformat(),           "home_id": home_id},
        {"id": "demo_e9",  "camera_id": "front_door",  "type": "motion_detected",  "confidence": 0.82, "timestamp": (now - timedelta(minutes=5)).isoformat(),           "home_id": home_id},
        {"id": "demo_e10", "camera_id": "driveway",    "type": "vehicle_detected", "confidence": 0.85, "timestamp": (now - timedelta(minutes=2)).isoformat(),           "home_id": home_id},
    ]

    demo_patterns = [
        {"id": "demo_p1", "home_id": home_id, "pattern_type": "rapid_return",      "fingerprint": "fp1", "salience_score": 8.2, "novelty_score": 9.0, "adaptation_score": 10.0, "temporal_weight": 0.8, "competition_score": 10.0, "flagged": True,  "explanation": "Someone returned home just 8 minutes after leaving — far shorter than the usual 4+ hours — and entered through the side door instead of the front. Worth a quick check.", "detected_at": (now - timedelta(hours=2)).isoformat(), "event_ids": ["demo_e1","demo_e2","demo_e4"]},
        {"id": "demo_p2", "home_id": home_id, "pattern_type": "delivery",          "fingerprint": "fp2", "salience_score": 5.1, "novelty_score": 5.0, "adaptation_score": 5.0,  "temporal_weight": 0.8, "competition_score": 7.0,  "flagged": False, "explanation": "A vehicle pulled up and a person approached the front door — likely a package delivery around the usual midday window.", "detected_at": (now - timedelta(hours=1, minutes=40)).isoformat(), "event_ids": ["demo_e3","demo_e5","demo_e6"]},
        {"id": "demo_p3", "home_id": home_id, "pattern_type": "unusual_entrance",  "fingerprint": "fp3", "salience_score": 7.5, "novelty_score": 8.0, "adaptation_score": 9.0,  "temporal_weight": 1.0, "competition_score": 5.0,  "flagged": True,  "explanation": "Activity detected at the side door during an unusual time — this entrance is rarely used and wasn't part of any expected pattern today.", "detected_at": (now - timedelta(minutes=10)).isoformat(), "event_ids": ["demo_e8"]},
        {"id": "demo_p4", "home_id": home_id, "pattern_type": "standard_activity", "fingerprint": "fp4", "salience_score": 2.8, "novelty_score": 2.0, "adaptation_score": 3.0,  "temporal_weight": 0.8, "competition_score": 3.0,  "flagged": False, "explanation": "Backyard motion — consistent with wind or an animal. No person detected.", "detected_at": (now - timedelta(minutes=22)).isoformat(), "event_ids": ["demo_e7"]},
    ]

    with get_db() as db:
        for e in demo_events:
            repo.save_event(db, e)
        for p in demo_patterns:
            existing = repo.get_pattern_by_id(db, p["id"])
            if not existing:
                repo.save_pattern(db, p)

    return {"seeded_events": len(demo_events), "seeded_patterns": len(demo_patterns)}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _pattern_to_dict(row) -> dict:
    return {
        "id": row.id,
        "pattern_type": row.pattern_type,
        "salience_score": row.salience_score,
        "novelty_score": row.novelty_score,
        "adaptation_score": row.adaptation_score,
        "flagged": row.flagged,
        "explanation": row.explanation,
        "detected_at": row.detected_at.isoformat() if isinstance(row.detected_at, datetime) else row.detected_at,
        "event_count": len(row.event_ids) if row.event_ids else 0,
    }
