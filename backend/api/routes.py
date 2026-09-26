"""
FastAPI routes for VIGILANT dashboard.

Endpoints:
  GET  /events          — recent Ring events (paginated)
  GET  /patterns        — detected patterns with salience scores
  GET  /patterns/{id}   — single pattern + explanation
  POST /patterns/score  — score a new sequence ad-hoc
  GET  /baseline        — learned baseline for a home
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List, Optional
import uuid

from backend.motif_engine.motif_core import MotifEngine, RingEvent as MotifRingEvent
from backend.bedrock_integration.explanation_generator import ExplanationGenerator

app = FastAPI(title="VIGILANT API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Module-level singletons (swap for DI / DB-backed versions later)
_motif = MotifEngine()
_bedrock = ExplanationGenerator()


# ------------------------------------------------------------------
# Request / Response models
# ------------------------------------------------------------------

class EventOut(BaseModel):
    id: str
    camera_name: str
    type: str
    confidence: float
    timestamp: datetime
    home_id: str


class PatternOut(BaseModel):
    id: str
    pattern_type: str
    salience_score: float
    flagged: bool
    explanation: Optional[str]
    detected_at: datetime
    event_count: int


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
# In-memory stores (replace with DB queries later)
# ------------------------------------------------------------------
_events_store: List[dict] = []
_patterns_store: List[dict] = []


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.get("/events", response_model=List[EventOut])
def get_events(
    home_id: str = Query("home_001"),
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(50, ge=1, le=200),
):
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    filtered = [
        e for e in _events_store
        if e["home_id"] == home_id and datetime.fromisoformat(e["timestamp"]) > cutoff
    ]
    return filtered[-limit:]


@app.get("/patterns", response_model=List[PatternOut])
def get_patterns(
    home_id: str = Query("home_001"),
    days: int = Query(7, ge=1, le=30),
    flagged_only: bool = Query(False),
    min_salience: float = Query(0.0, ge=0, le=10),
):
    cutoff = datetime.utcnow() - timedelta(days=days)
    results = [
        p for p in _patterns_store
        if p["home_id"] == home_id
        and datetime.fromisoformat(p["detected_at"]) > cutoff
        and p["salience_score"] >= min_salience
        and (not flagged_only or p["flagged"])
    ]
    results.sort(key=lambda x: x["detected_at"], reverse=True)
    return results


@app.get("/patterns/{pattern_id}", response_model=PatternOut)
def get_pattern(pattern_id: str):
    for p in _patterns_store:
        if p["id"] == pattern_id:
            return p
    raise HTTPException(status_code=404, detail="Pattern not found")


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

    score = _motif.score_pattern(motif_events)

    pattern_data = {
        "pattern_type": score.pattern_type,
        "confidence": sum(e.get("confidence", 1.0) for e in req.events) / len(req.events),
        "novelty_score": score.novelty,
        "salience_score": score.final_salience,
        "events": req.events,
    }
    explanation = _bedrock.generate_explanation(pattern_data)

    # persist to in-memory store
    pattern_record = {
        "id": str(uuid.uuid4()),
        "home_id": req.home_id,
        "pattern_type": score.pattern_type,
        "salience_score": score.final_salience,
        "flagged": score.flagged,
        "explanation": explanation,
        "detected_at": datetime.utcnow().isoformat(),
        "event_count": len(req.events),
    }
    _patterns_store.append(pattern_record)

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


@app.post("/demo/seed")
def seed_demo_data(home_id: str = Query("home_001")):
    """Instantly populate the dashboard with realistic demo data for testing."""
    now = datetime.utcnow()

    demo_events = [
        {"id": "demo_e1", "camera_name": "front_door",  "type": "person_detected",  "confidence": 0.95, "timestamp": (now - timedelta(hours=2, minutes=5)).isoformat(), "home_id": home_id},
        {"id": "demo_e2", "camera_name": "front_door",  "type": "motion_detected",  "confidence": 0.91, "timestamp": (now - timedelta(hours=2, minutes=4)).isoformat(), "home_id": home_id},
        {"id": "demo_e3", "camera_name": "driveway",    "type": "vehicle_detected", "confidence": 0.88, "timestamp": (now - timedelta(hours=1, minutes=45)).isoformat(), "home_id": home_id},
        {"id": "demo_e4", "camera_name": "side_door",   "type": "person_detected",  "confidence": 0.90, "timestamp": (now - timedelta(hours=1, minutes=30)).isoformat(), "home_id": home_id},
        {"id": "demo_e5", "camera_name": "front_door",  "type": "doorbell",         "confidence": 1.00, "timestamp": (now - timedelta(minutes=45)).isoformat(), "home_id": home_id},
        {"id": "demo_e6", "camera_name": "front_door",  "type": "person_detected",  "confidence": 0.93, "timestamp": (now - timedelta(minutes=44)).isoformat(), "home_id": home_id},
        {"id": "demo_e7", "camera_name": "backyard",    "type": "motion_detected",  "confidence": 0.78, "timestamp": (now - timedelta(minutes=20)).isoformat(), "home_id": home_id},
        {"id": "demo_e8", "camera_name": "side_door",   "type": "person_detected",  "confidence": 0.86, "timestamp": (now - timedelta(minutes=8)).isoformat(), "home_id": home_id},
        {"id": "demo_e9", "camera_name": "front_door",  "type": "motion_detected",  "confidence": 0.82, "timestamp": (now - timedelta(minutes=5)).isoformat(), "home_id": home_id},
        {"id": "demo_e10","camera_name": "driveway",    "type": "vehicle_detected", "confidence": 0.85, "timestamp": (now - timedelta(minutes=2)).isoformat(), "home_id": home_id},
    ]

    demo_patterns = [
        {
            "id": "demo_p1",
            "home_id": home_id,
            "pattern_type": "rapid_return",
            "salience_score": 8.2,
            "flagged": True,
            "explanation": "Someone returned home just 8 minutes after leaving — far shorter than the usual 4+ hours — and entered through the side door instead of the front. Worth a quick check.",
            "detected_at": (now - timedelta(hours=2)).isoformat(),
            "event_count": 3,
        },
        {
            "id": "demo_p2",
            "home_id": home_id,
            "pattern_type": "delivery",
            "salience_score": 5.1,
            "flagged": False,
            "explanation": "A vehicle pulled up and a person approached the front door — likely a package delivery around the usual midday window.",
            "detected_at": (now - timedelta(hours=1, minutes=40)).isoformat(),
            "event_count": 3,
        },
        {
            "id": "demo_p3",
            "home_id": home_id,
            "pattern_type": "unusual_entrance",
            "salience_score": 7.5,
            "flagged": True,
            "explanation": "Activity detected at the side door during an unusual time — this entrance is rarely used and wasn't part of any expected pattern today.",
            "detected_at": (now - timedelta(minutes=10)).isoformat(),
            "event_count": 2,
        },
        {
            "id": "demo_p4",
            "home_id": home_id,
            "pattern_type": "standard_activity",
            "salience_score": 2.8,
            "flagged": False,
            "explanation": "Backyard motion — consistent with wind or an animal. No person detected.",
            "detected_at": (now - timedelta(minutes=22)).isoformat(),
            "event_count": 1,
        },
    ]

    existing_event_ids = {e["id"] for e in _events_store}
    for e in demo_events:
        if e["id"] not in existing_event_ids:
            _events_store.append(e)

    existing_pattern_ids = {p["id"] for p in _patterns_store}
    for p in demo_patterns:
        if p["id"] not in existing_pattern_ids:
            _patterns_store.append(p)

    return {"seeded_events": len(demo_events), "seeded_patterns": len(demo_patterns)}


@app.get("/baseline")
def get_baseline(home_id: str = Query("home_001")):
    patterns = _motif.baseline_patterns
    return {
        "home_id": home_id,
        "pattern_count": len(patterns),
        "patterns": [
            {
                "fingerprint": fp,
                "count": bp.count,
                "last_seen": bp.last_seen.isoformat() if bp.last_seen else None,
            }
            for fp, bp in patterns.items()
        ],
    }
