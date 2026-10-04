"""
FastAPI routes for VIGILANT dashboard.
All state is persisted to SQLite (dev) or Postgres (prod).
"""

import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta
from html import escape
from typing import List, Optional
from urllib.parse import parse_qs

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

from backend.motif_engine.motif_core import MotifEngine, RingEvent as MotifRingEvent
from backend.bedrock_integration.explanation_generator import ExplanationGenerator
from backend.database.session import get_db, init_db
from backend.database import repository as repo
from backend.alexa_integration.client import AlexaClient
from backend.ring_integration.normalization import normalize_webhook_event
from backend.ring_integration.oauth import (
    claim_ring_account,
    mask_account_email,
    partner_user_id_from_email,
    receive_authorization_code,
)
from backend.ring_integration.official_client import RingPartnerAPIError
from backend.ring_integration.partner_auth import verify_partner_credentials
from backend.ring_integration.pipeline import RingEventPipeline
from backend.ring_integration.security import verify_webhook_signature

app = FastAPI(title="VIGILANT API", version="0.2.0")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("RING_SESSION_SECRET") or secrets.token_urlsafe(32),
    session_cookie="vigilant_session",
    same_site="lax",
    https_only=os.getenv("RING_COOKIE_SECURE", "false").lower() == "true",
)

_ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)

motif = MotifEngine()
bedrock = ExplanationGenerator()
alexa = AlexaClient()
ring_pipeline = RingEventPipeline(motif, bedrock, alexa)


@app.on_event("startup")
def startup():
    init_db()
    with get_db() as db:
        count = repo.load_baselines_into_engine(
            db, os.getenv("HOME_ID", "home_001"), motif
        )
        if count:
            print(f"[VIGILANT] Loaded {count} baseline patterns from DB")


# ------------------------------------------------------------------
# Models
# ------------------------------------------------------------------

class EventOut(BaseModel):
    id: str
    camera_name: str
    type: str
    confidence: Optional[float] = None
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


def _partner_signin_ready() -> bool:
    required = (
        "RING_SESSION_SECRET",
        "VIGILANT_ACCOUNT_EMAIL",
        "VIGILANT_ACCOUNT_PASSWORD_HASH",
    )
    return all(os.getenv(name) for name in required)


def _csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def _valid_csrf(request: Request, supplied: str) -> bool:
    expected = request.session.get("csrf_token", "")
    return bool(expected) and hmac.compare_digest(expected, supplied)


async def _read_form(request: Request) -> dict:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    body = await request.body()
    if content_type == "application/json":
        try:
            values = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail="Malformed JSON body") from exc
        if not isinstance(values, dict):
            raise HTTPException(status_code=400, detail="Expected an object body")
        return values
    if content_type != "application/x-www-form-urlencoded":
        raise HTTPException(status_code=415, detail="Expected URL-encoded form or JSON body")
    try:
        parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Malformed form body") from exc
    return {key: values[-1] for key, values in parsed.items()}


def _signin_form(csrf_token: str) -> str:
    return (
        "<!doctype html><html><head><title>Vigilant sign in</title></head><body>"
        "<main><h1>Sign in to Vigilant</h1>"
        "<form method=post action=/ring/login>"
        f"<input type=hidden name=csrf_token value=\"{escape(csrf_token, quote=True)}\">"
        "<label>Email <input type=email name=email required autocomplete=username></label>"
        "<label>Password <input type=password name=password required autocomplete=current-password></label>"
        "<button type=submit>Sign in</button></form></main></body></html>"
    )


def _ring_homepage(request: Request, message: str = "") -> str:
    if not request.session.get("partner_user_id"):
        return _signin_form(_csrf_token(request))

    csrf = escape(_csrf_token(request), quote=True)
    pending = request.session.get("pending_ring_link")
    if pending:
        return (
            "<!doctype html><html><head><title>Link Ring to Vigilant</title></head><body>"
            "<main><h1>Link Ring to Vigilant</h1>"
            "<p>Confirm linking the Ring account authorized in the Ring app.</p>"
            f"<form method=post action=/ring/link/claim><input type=hidden name=csrf_token value=\"{csrf}\">"
            "<button type=submit>Confirm Ring account link</button></form></main></body></html>"
        )

    with get_db() as db:
        accounts = (
            db.query(repo.RingAccount)
            .filter(repo.RingAccount.partner_user_id == request.session["partner_user_id"])
            .all()
        )
    connected = sum(1 for account in accounts if account.status == "completed")
    status = escape(message or "Connected Ring account(s): {0}".format(connected))
    return (
        "<!doctype html><html><head><title>Vigilant Ring settings</title></head><body>"
        f"<main><h1>Vigilant</h1><p>{status}</p>"
        "<p>Manage device access in the Ring app.</p></main></body></html>"
    )


@app.get("/ring", response_class=HTMLResponse)
def ring_homepage(request: Request):
    if not _partner_signin_ready():
        return HTMLResponse("<h1>Ring linking is not configured</h1>", status_code=503)
    return HTMLResponse(_ring_homepage(request))


@app.get("/ring/link", response_class=HTMLResponse)
def ring_account_link(request: Request, time: str = Query(...), nonce: str = Query(...)):
    if not _partner_signin_ready():
        raise HTTPException(status_code=503, detail="Vigilant account sign-in is not configured")
    request.session["pending_ring_link"] = {"time": time, "nonce": nonce}
    _csrf_token(request)
    return HTMLResponse(_ring_homepage(request))


@app.post("/ring/login")
async def ring_partner_login(request: Request):
    if not _partner_signin_ready():
        raise HTTPException(status_code=503, detail="Vigilant account sign-in is not configured")
    form = await _read_form(request)
    if not _valid_csrf(request, str(form.get("csrf_token", ""))):
        raise HTTPException(status_code=403, detail="Invalid sign-in request")

    email = str(form.get("email", ""))
    password = str(form.get("password", ""))
    if not verify_partner_credentials(email, password):
        raise HTTPException(status_code=401, detail="Invalid Vigilant credentials")

    configured_email = os.getenv("VIGILANT_ACCOUNT_EMAIL", email)
    pending = request.session.get("pending_ring_link")
    request.session.clear()
    request.session["partner_user_id"] = partner_user_id_from_email(configured_email)
    request.session["account_identifier"] = mask_account_email(configured_email)
    request.session["csrf_token"] = secrets.token_urlsafe(32)
    if pending:
        request.session["pending_ring_link"] = pending
    return RedirectResponse("/ring", status_code=303)


@app.post("/ring/link/claim", response_class=HTMLResponse)
async def ring_link_claim(request: Request):
    if not request.session.get("partner_user_id"):
        raise HTTPException(status_code=401, detail="Sign in to Vigilant before linking Ring")
    form = await _read_form(request)
    if not _valid_csrf(request, str(form.get("csrf_token", ""))):
        raise HTTPException(status_code=403, detail="Invalid account-link request")
    pending = request.session.get("pending_ring_link")
    if not pending:
        raise HTTPException(status_code=400, detail="No Ring account-link request is pending")

    try:
        with get_db() as db:
            account = await run_in_threadpool(
                claim_ring_account,
                pending["time"],
                pending["nonce"],
                request.session["partner_user_id"],
                request.session["account_identifier"],
                db,
            )
            account_id = account.account_id
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RingPartnerAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    request.session.pop("pending_ring_link", None)
    return HTMLResponse(_ring_homepage(request, "Ring account linked: " + escape(account_id)))


def _receive_ring_code(code: str) -> str:
    with get_db() as db:
        return receive_authorization_code(code, db)


@app.post("/ring/token")
async def ring_token_exchange(request: Request):
    values = await _read_form(request)
    expected_client_id = os.getenv("RING_CLIENT_ID", "")
    supplied_client_id = values.get("client_id")
    if not expected_client_id or not isinstance(supplied_client_id, str):
        raise HTTPException(status_code=401, detail="Missing Ring client ID")
    if not hmac.compare_digest(supplied_client_id, expected_client_id):
        raise HTTPException(status_code=401, detail="Unexpected Ring client ID")
    code = values.get("code") or values.get("authorization_code")
    if not isinstance(code, str) or not code:
        raise HTTPException(status_code=400, detail="Missing Ring authorization code")

    try:
        await run_in_threadpool(_receive_ring_code, code)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RingPartnerAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"status": "accepted"}


def _persist_ring_webhook(payload: dict, normalized_event):
    meta = payload["meta"]
    request_id = meta["request_id"]
    account_id = meta["account_id"]
    event_id = payload["data"]["id"]
    with get_db() as db:
        receipt_created = repo.save_webhook_receipt(db, request_id, account_id, event_id)
        if not receipt_created:
            receipt = repo.get_webhook_receipt(db, request_id)
            if receipt is None or receipt.processed_at is not None:
                return "duplicate", None, None

        pipeline_event = None
        home_id = None
        if normalized_event is not None:
            account = repo.get_ring_account(db, account_id)
            if account is None or account.status != "completed" or not account.home_id:
                raise RuntimeError("Ring account is not linked to a Vigilant account")
            home_id = account.home_id
            camera = repo.get_camera(db, normalized_event.camera_id)
            camera_name = camera.name if camera else normalized_event.camera_name
            repo.upsert_camera(
                db,
                home_id,
                normalized_event.camera_id,
                camera_name,
            )
            stored_event = repo.get_ring_event(db, event_id)
            if stored_event is None:
                pipeline_event = normalized_event.as_event_dict(home_id)
                pipeline_event["camera_name"] = camera_name
                pipeline_event["raw_payload"] = payload
                repo.save_event(db, pipeline_event)
            elif not receipt_created:
                camera = repo.get_camera(db, stored_event.camera_id)
                pipeline_event = {
                    "id": stored_event.id,
                    "home_id": stored_event.home_id,
                    "camera_id": stored_event.camera_id,
                    "camera_name": camera.name if camera else stored_event.camera_id,
                    "type": stored_event.type,
                    "timestamp": stored_event.timestamp.isoformat(),
                    "confidence": stored_event.confidence,
                }
        elif payload["data"].get("type") == "app_integration_removed":
            account = repo.get_ring_account(db, account_id)
            if account:
                account.status = "removed"
                account.access_token_encrypted = ""
                account.refresh_token_encrypted = ""
        if pipeline_event is None:
            repo.mark_webhook_processed(db, request_id)
    return "accepted", pipeline_event, home_id


def _process_ring_event_background(event: dict, home_id: str, request_id: str) -> None:
    try:
        ring_pipeline.process(event, home_id)
    except Exception as exc:
        print(f"[Ring] Event processing failed for request {request_id}: {type(exc).__name__}")
        return
    with get_db() as db:
        repo.mark_webhook_processed(db, request_id)


@app.post("/ring/webhook")
async def ring_webhook(request: Request, background_tasks: BackgroundTasks):
    signing_key = os.getenv("RING_HMAC_SIGNING_KEY")
    if not signing_key:
        raise HTTPException(status_code=503, detail="Ring webhook signing key is not configured")
    raw_body = await request.body()
    if not verify_webhook_signature(
        signing_key, raw_body, request.headers.get("x-signature", "")
    ):
        raise HTTPException(status_code=401, detail="Invalid Ring webhook signature")

    try:
        payload = json.loads(raw_body)
        if not isinstance(payload, dict):
            raise ValueError("Webhook body must be an object")
        meta = payload["meta"]
        data = payload["data"]
        if not meta["request_id"] or not meta["account_id"]:
            raise ValueError("Missing Ring webhook request/account ID")
        if not data["id"] or not data["type"]:
            raise ValueError("Missing Ring webhook event ID/type")
        normalized_event = normalize_webhook_event(payload)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Malformed Ring webhook payload") from exc

    try:
        status, pipeline_event, home_id = await run_in_threadpool(
            _persist_ring_webhook, payload, normalized_event
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if pipeline_event is not None:
        background_tasks.add_task(
            _process_ring_event_background,
            pipeline_event,
            home_id,
            payload["meta"]["request_id"],
        )
    return {"status": status}


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

    if score.flagged:
        alexa.send_alert(req.home_id, {
            "pattern_type": score.pattern_type,
            "explanation": explanation,
            "salience_score": score.final_salience,
        })

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


@app.get("/baseline-comparison")
def get_baseline_comparison(
    home_id: str = Query("home_001"),
    days: int = Query(7, ge=1, le=30),
):
    """7-day activity vs. historical baseline."""
    with get_db() as db:
        return repo.get_baseline_comparison(db, home_id, days)


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
    if os.getenv("RING_INTEGRATION_MODE", "official").lower() != "simulator":
        raise HTTPException(status_code=404, detail="Demo seeding is disabled outside simulator mode")
    now = datetime.utcnow()

    h = home_id  # short alias for id prefixing
    demo_events = [
        {"id": f"{h}_e1",  "camera_id": "front_door",  "type": "person_detected",  "confidence": 0.95, "timestamp": (now - timedelta(hours=2, minutes=5)).isoformat(),  "home_id": home_id},
        {"id": f"{h}_e2",  "camera_id": "front_door",  "type": "motion_detected",  "confidence": 0.91, "timestamp": (now - timedelta(hours=2, minutes=4)).isoformat(),  "home_id": home_id},
        {"id": f"{h}_e3",  "camera_id": "driveway",    "type": "vehicle_detected", "confidence": 0.88, "timestamp": (now - timedelta(hours=1, minutes=45)).isoformat(), "home_id": home_id},
        {"id": f"{h}_e4",  "camera_id": "side_door",   "type": "person_detected",  "confidence": 0.90, "timestamp": (now - timedelta(hours=1, minutes=30)).isoformat(), "home_id": home_id},
        {"id": f"{h}_e5",  "camera_id": "front_door",  "type": "doorbell",         "confidence": 1.00, "timestamp": (now - timedelta(minutes=45)).isoformat(),          "home_id": home_id},
        {"id": f"{h}_e6",  "camera_id": "front_door",  "type": "person_detected",  "confidence": 0.93, "timestamp": (now - timedelta(minutes=44)).isoformat(),          "home_id": home_id},
        {"id": f"{h}_e7",  "camera_id": "backyard",    "type": "motion_detected",  "confidence": 0.78, "timestamp": (now - timedelta(minutes=20)).isoformat(),          "home_id": home_id},
        {"id": f"{h}_e8",  "camera_id": "side_door",   "type": "person_detected",  "confidence": 0.86, "timestamp": (now - timedelta(minutes=8)).isoformat(),           "home_id": home_id},
        {"id": f"{h}_e9",  "camera_id": "front_door",  "type": "motion_detected",  "confidence": 0.82, "timestamp": (now - timedelta(minutes=5)).isoformat(),           "home_id": home_id},
        {"id": f"{h}_e10", "camera_id": "driveway",    "type": "vehicle_detected", "confidence": 0.85, "timestamp": (now - timedelta(minutes=2)).isoformat(),           "home_id": home_id},
    ]

    demo_patterns = [
        {"id": f"{h}_p1", "home_id": home_id, "pattern_type": "rapid_return",      "fingerprint": "fp1", "salience_score": 8.2, "novelty_score": 9.0, "adaptation_score": 10.0, "temporal_weight": 0.8, "competition_score": 10.0, "flagged": True,  "explanation": "Someone returned home just 8 minutes after leaving — far shorter than the usual 4+ hours — and entered through the side door instead of the front. Worth a quick check.", "detected_at": (now - timedelta(hours=2)).isoformat(), "event_ids": [f"{h}_e1", f"{h}_e2", f"{h}_e4"]},
        {"id": f"{h}_p2", "home_id": home_id, "pattern_type": "delivery",          "fingerprint": "fp2", "salience_score": 5.1, "novelty_score": 5.0, "adaptation_score": 5.0,  "temporal_weight": 0.8, "competition_score": 7.0,  "flagged": False, "explanation": "A vehicle pulled up and a person approached the front door — likely a package delivery around the usual midday window.", "detected_at": (now - timedelta(hours=1, minutes=40)).isoformat(), "event_ids": [f"{h}_e3", f"{h}_e5", f"{h}_e6"]},
        {"id": f"{h}_p3", "home_id": home_id, "pattern_type": "unusual_entrance",  "fingerprint": "fp3", "salience_score": 7.5, "novelty_score": 8.0, "adaptation_score": 9.0,  "temporal_weight": 1.0, "competition_score": 5.0,  "flagged": True,  "explanation": "Activity detected at the side door during an unusual time — this entrance is rarely used and wasn't part of any expected pattern today.", "detected_at": (now - timedelta(minutes=10)).isoformat(), "event_ids": [f"{h}_e8"]},
        {"id": f"{h}_p4", "home_id": home_id, "pattern_type": "standard_activity", "fingerprint": "fp4", "salience_score": 2.8, "novelty_score": 2.0, "adaptation_score": 3.0,  "temporal_weight": 0.8, "competition_score": 3.0,  "flagged": False, "explanation": "Backyard motion — consistent with wind or an animal. No person detected.", "detected_at": (now - timedelta(minutes=22)).isoformat(), "event_ids": [f"{h}_e7"]},
    ]

    seeded_p = 0
    with get_db() as db:
        for e in demo_events:
            repo.save_event(db, e)
        for p in demo_patterns:
            if not repo.get_pattern_by_id(db, p["id"]):
                repo.save_pattern(db, p)
                seeded_p += 1

    return {"seeded_events": len(demo_events), "seeded_patterns": seeded_p}


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
