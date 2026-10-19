"""
FastAPI routes for VIGILANT dashboard.
All state is persisted to SQLite (dev) or Postgres (prod).
"""

import hmac
import json
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from html import escape
from typing import List, Optional
from urllib.parse import parse_qs

logger = logging.getLogger("vigilant.ring")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

from backend.motif_engine.motif_core import MotifEngine, RingEvent as MotifRingEvent
from backend.explanation.explainer import RuleBasedExplainer
from backend.database.session import get_db, init_db
from backend.database import repository as repo
from backend.database.models import Pattern as PatternModel, RingEvent as RingEventModel
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
explainer = RuleBasedExplainer()
alexa = AlexaClient()
ring_pipeline = RingEventPipeline(motif, explainer, alexa)

# In-memory: last 5 link attempts for /ring/status visibility.
# Not persisted across restarts but survives within one Vercel function instance.
_link_attempts: list = []


def _record_link_attempt(correlation_id: str, step: str, ok: bool, error: str = "") -> None:
    entry = {
        "at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "correlation_id": correlation_id,
        "step": step,
        "ok": ok,
        "error": error,
    }
    _link_attempts.append(entry)
    if len(_link_attempts) > 5:
        _link_attempts.pop(0)


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
    from backend.database.session import get_db as _get_db
    # Ring
    ring_configured = bool(
        os.getenv("RING_CLIENT_ID") and os.getenv("RING_CLIENT_SECRET") and os.getenv("RING_HMAC_SIGNING_KEY")
    )
    ring_link_configured = bool(
        os.getenv("RING_TOKEN_ENCRYPTION_KEY")
        and os.getenv("RING_SESSION_SECRET")
        and os.getenv("VIGILANT_ACCOUNT_EMAIL")
        and os.getenv("VIGILANT_ACCOUNT_PASSWORD_HASH")
    )
    # DB
    db_ok = False
    try:
        with _get_db() as db:
            db.execute(__import__("sqlalchemy").text("SELECT 1"))
            db_ok = True
    except Exception:
        pass
    # Ring accounts
    linked_accounts = 0
    try:
        with _get_db() as db:
            from backend.database.models import RingAccount
            linked_accounts = db.query(RingAccount).filter(RingAccount.status == "completed").count()
    except Exception:
        pass

    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "features": {
            "ring_webhook": {
                "enabled": ring_configured,
                "reason": None if ring_configured else "RING_CLIENT_ID / RING_CLIENT_SECRET / RING_HMAC_SIGNING_KEY not set",
            },
            "ring_account_linking": {
                "enabled": ring_link_configured,
                "reason": None if ring_link_configured else "RING_TOKEN_ENCRYPTION_KEY / RING_SESSION_SECRET / VIGILANT_ACCOUNT_EMAIL / VIGILANT_ACCOUNT_PASSWORD_HASH not set",
                "linked_accounts": linked_accounts,
            },
            "explanations": {
                "enabled": True,
                "type": "rule_based",
            },
            "database": {
                "ok": db_ok,
                "url_type": "postgres" if (os.getenv("DATABASE_URL") or "").startswith("postgresql") else "sqlite",
            },
            "ring_integration_mode": os.getenv("RING_INTEGRATION_MODE", "official"),
            "warnings": (
                ["RING_INTEGRATION_MODE=simulator — production should use official mode"]
                if os.getenv("RING_INTEGRATION_MODE", "official").lower() == "simulator"
                else []
            ),
        },
    }


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
    cid = uuid.uuid4().hex[:8]
    logger.info("[%s] ring/link: callback received time=%s nonce_len=%d", cid, time, len(nonce))
    if not _partner_signin_ready():
        logger.error("[%s] ring/link: partner sign-in not configured (RING_SESSION_SECRET/VIGILANT_ACCOUNT_EMAIL/VIGILANT_ACCOUNT_PASSWORD_HASH)", cid)
        _record_link_attempt(cid, "account_link_callback", False, "partner sign-in not configured")
        raise HTTPException(status_code=503, detail="Vigilant account sign-in is not configured")
    request.session["pending_ring_link"] = {"time": time, "nonce": nonce, "cid": cid}
    _csrf_token(request)
    logger.info("[%s] ring/link: nonce stored in session, showing sign-in page", cid)
    _record_link_attempt(cid, "account_link_callback", True)
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
    pending = request.session.get("pending_ring_link") or {}
    cid = pending.get("cid") or uuid.uuid4().hex[:8]
    if not request.session.get("partner_user_id"):
        logger.warning("[%s] ring/link/claim: no partner_user_id in session (sign-in not completed)", cid)
        _record_link_attempt(cid, "claim", False, "not signed in to Vigilant")
        raise HTTPException(status_code=401, detail="Sign in to Vigilant before linking Ring")
    form = await _read_form(request)
    if not _valid_csrf(request, str(form.get("csrf_token", ""))):
        logger.warning("[%s] ring/link/claim: CSRF mismatch", cid)
        _record_link_attempt(cid, "claim", False, "CSRF mismatch")
        raise HTTPException(status_code=403, detail="Invalid account-link request")
    if not pending:
        logger.warning("[%s] ring/link/claim: no pending_ring_link in session", cid)
        _record_link_attempt(cid, "claim", False, "no pending link in session")
        raise HTTPException(status_code=400, detail="No Ring account-link request is pending")

    logger.info("[%s] ring/link/claim: starting claim (time=%s)", cid, pending.get("time"))
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
        logger.info("[%s] ring/link/claim: account %s… linked ok", cid, account_id[:4] if account_id else "?")
        _record_link_attempt(cid, "claim", True)
    except ValueError as exc:
        eid = uuid.uuid4().hex[:8]
        logger.error("[%s] ring/link/claim: nonce/account error eid=%s — %s", cid, eid, exc, exc_info=True)
        _record_link_attempt(cid, "claim", False, str(exc))
        raise HTTPException(status_code=400, detail=f"Linking failed (err:{eid})") from exc
    except RuntimeError as exc:
        eid = uuid.uuid4().hex[:8]
        logger.error("[%s] ring/link/claim: config error eid=%s — %s", cid, eid, exc, exc_info=True)
        _record_link_attempt(cid, "claim", False, str(exc))
        raise HTTPException(status_code=503, detail=f"Service unavailable (err:{eid})") from exc
    except RingPartnerAPIError as exc:
        eid = uuid.uuid4().hex[:8]
        logger.error("[%s] ring/link/claim: Ring API error eid=%s — %s", cid, eid, exc, exc_info=True)
        _record_link_attempt(cid, "claim", False, str(exc))
        raise HTTPException(status_code=502, detail=f"Ring API error (err:{eid})") from exc

    request.session.pop("pending_ring_link", None)
    return HTMLResponse(_ring_homepage(request, "Ring account linked: " + escape(account_id)))


def _receive_ring_code(code: str) -> str:  # returns account_id
    with get_db() as db:
        return receive_authorization_code(code, db)


@app.post("/ring/token")
async def ring_token_exchange(request: Request):
    cid = uuid.uuid4().hex[:8]
    logger.info("[%s] ring/token: request received from %s", cid, request.client.host if request.client else "unknown")
    values = await _read_form(request)
    expected_client_id = os.getenv("RING_CLIENT_ID", "")
    supplied_client_id = values.get("client_id")
    if not expected_client_id or not isinstance(supplied_client_id, str):
        logger.warning("[%s] ring/token: missing client_id", cid)
        _record_link_attempt(cid, "token_exchange", False, "missing client_id")
        raise HTTPException(status_code=401, detail="Missing Ring client ID")
    if not hmac.compare_digest(supplied_client_id, expected_client_id):
        logger.warning("[%s] ring/token: client_id mismatch (len=%d vs expected len=%d)", cid, len(supplied_client_id), len(expected_client_id))
        _record_link_attempt(cid, "token_exchange", False, "client_id mismatch")
        raise HTTPException(status_code=401, detail="Unexpected Ring client ID")
    code = values.get("code") or values.get("authorization_code")
    if not isinstance(code, str) or not code:
        logger.warning("[%s] ring/token: missing authorization code", cid)
        _record_link_attempt(cid, "token_exchange", False, "missing authorization code")
        raise HTTPException(status_code=400, detail="Missing Ring authorization code")

    logger.info("[%s] ring/token: client_id ok, code present (len=%d), calling Ring OAuth", cid, len(code))
    try:
        account_id = await run_in_threadpool(_receive_ring_code, code)
        logger.info("[%s] ring/token: tokens stored for account %s…", cid, account_id[:4] if account_id else "?")
        _record_link_attempt(cid, "token_exchange", True)
    except RuntimeError as exc:
        eid = uuid.uuid4().hex[:8]
        logger.error("[%s] ring/token: config error eid=%s — %s", cid, eid, exc, exc_info=True)
        _record_link_attempt(cid, "token_exchange", False, str(exc))
        raise HTTPException(status_code=503, detail=f"Service unavailable (err:{eid})") from exc
    except RingPartnerAPIError as exc:
        eid = uuid.uuid4().hex[:8]
        logger.error("[%s] ring/token: Ring API error eid=%s — %s", cid, eid, exc, exc_info=True)
        _record_link_attempt(cid, "token_exchange", False, str(exc))
        raise HTTPException(status_code=502, detail=f"Ring API error (err:{eid})") from exc
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
        eid = uuid.uuid4().hex[:8]
        logger.error("ring/webhook: persistence error eid=%s — %s", eid, exc, exc_info=True)
        raise HTTPException(status_code=503, detail=f"Webhook processing failed (err:{eid})") from exc

    if pipeline_event is not None:
        request_id = payload["meta"]["request_id"]
        # On Vercel serverless functions BackgroundTasks may be killed after the
        # response is returned. Process synchronously on Vercel; use background
        # tasks elsewhere so the response stays fast.
        if os.getenv("VERCEL"):
            await run_in_threadpool(
                _process_ring_event_background, pipeline_event, home_id, request_id
            )
        else:
            background_tasks.add_task(
                _process_ring_event_background, pipeline_event, home_id, request_id
            )

    return {"status": status}


@app.get("/ring/status")
def ring_status():
    """Returns Ring connection status for the dashboard panel. Never exposes credentials."""
    linked_accounts = []
    last_webhook = None
    devices = []

    try:
        with get_db() as db:
            from backend.database.models import RingAccount, RingWebhookReceipt
            accounts = (
                db.query(RingAccount)
                .filter(RingAccount.status == "completed")
                .all()
            )
            for acc in accounts:
                linked_accounts.append({
                    "account_id": acc.account_id,
                    "account_identifier": acc.account_identifier,
                    "home_id": acc.home_id,
                    "linked_at": acc.created_at.isoformat() if acc.created_at else None,
                })
            # Most recent webhook receipt
            receipt = (
                db.query(RingWebhookReceipt)
                .order_by(RingWebhookReceipt.received_at.desc())
                .first()
            )
            if receipt:
                last_webhook = {
                    "received_at": receipt.received_at.isoformat(),
                    "processed": receipt.processed_at is not None,
                    "request_id": receipt.request_id[:8] + "…",
                }
            # Cameras (=devices)
            from backend.database.models import Camera
            cameras = db.query(Camera).all()
            devices = [
                {"id": c.id, "name": c.name, "home_id": c.home_id}
                for c in cameras
            ]
    except Exception as _e:
        logger.warning("ring_status DB query failed: %s", _e)

    return {
        "ring_configured": bool(
            os.getenv("RING_CLIENT_ID")
            and os.getenv("RING_CLIENT_SECRET")
            and os.getenv("RING_HMAC_SIGNING_KEY")
        ),
        "account_link_configured": _partner_signin_ready(),
        "linked_accounts": linked_accounts,
        "linked_account_count": len(linked_accounts),
        "devices": devices,
        "last_webhook": last_webhook,
        "last_link_attempt": _link_attempts[-1] if _link_attempts else None,
        "mode": os.getenv("RING_INTEGRATION_MODE", "official"),
    }


@app.post("/ring/simulator/seed-account")
def simulator_seed_account(request_data: dict):
    """
    Simulator-only: seed a completed RingAccount so the webhook handler can
    route events to a home without a real OAuth flow.
    Only available when RING_INTEGRATION_MODE=simulator.
    """
    if os.getenv("RING_INTEGRATION_MODE", "official").lower() != "simulator":
        raise HTTPException(status_code=404, detail="Not available in official mode")
    account_id = request_data.get("account_id", "sim_account_001")
    home_id = request_data.get("home_id", os.getenv("HOME_ID", "home_001"))
    from backend.database.models import RingAccount
    with get_db() as db:
        account = db.query(RingAccount).filter(RingAccount.account_id == account_id).first()
        if account is None:
            account = RingAccount(
                account_id=account_id,
                partner_user_id="sim_user",
                home_id=home_id,
                account_identifier="sim@example.com",
                access_token_encrypted="sim",
                refresh_token_encrypted="sim",
                access_token_expires_at=datetime(2099, 1, 1),
                status="completed",
            )
            db.add(account)
        elif account.status != "completed":
            account.home_id = home_id
            account.status = "completed"
        repo.get_or_create_home(db, home_id)
    return {"account_id": account_id, "home_id": home_id, "status": "seeded"}


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
        explanation = explainer.generate_explanation(pattern_data)
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
            "detected_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
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


@app.get("/daily-summary")
def get_daily_summary(home_id: str = Query("home_001")):
    """One-day digest: event counts, flagged patterns, noise reduction, top alert."""
    with get_db() as db:
        events = repo.get_events(db, home_id, hours=24, limit=500)
        patterns = repo.get_patterns(db, home_id, days=1)

    total_events = len(events)
    flagged = [p for p in patterns if p.flagged]

    breakdown: dict = {}
    for p in patterns:
        breakdown[p.pattern_type] = breakdown.get(p.pattern_type, 0) + 1

    top = max(patterns, key=lambda p: p.salience_score, default=None)
    avg_sal = round(sum(p.salience_score for p in patterns) / len(patterns), 1) if patterns else 0.0
    noise_pct = round(((total_events - len(flagged)) / total_events) * 100) if total_events > 0 else None

    return {
        "home_id": home_id,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "period_hours": 24,
        "total_events": total_events,
        "total_patterns": len(patterns),
        "flagged_count": len(flagged),
        "noise_reduction_pct": noise_pct,
        "avg_salience": avg_sal,
        "pattern_breakdown": breakdown,
        "top_pattern": {
            "id": top.id,
            "type": top.pattern_type,
            "salience": top.salience_score,
            "explanation": top.explanation,
        } if top else None,
    }


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


def _require_demo_token(token: Optional[str]) -> None:
    """Allow demo endpoints in simulator mode, or in official mode when DEMO_SEED_TOKEN matches.
    Returns 404 in all failure cases — don't reveal the endpoint exists to scanners."""
    if os.getenv("RING_INTEGRATION_MODE", "official").lower() == "simulator":
        return
    expected = os.getenv("DEMO_SEED_TOKEN", "")
    if not expected or not secrets.compare_digest(token or "", expected):
        raise HTTPException(status_code=404, detail="Not found")


@app.post("/demo/seed")
def seed_demo_data(
    home_id: str = Query("home_001"),
    token: Optional[str] = Query(None),
):
    _require_demo_token(token)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    h = home_id  # short alias for id prefixing
    _ex = RuleBasedExplainer()
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
        # caretaking / late_first_activity seed: motion at front_door around 14:30 local, first activity of day
        {"id": f"{h}_e11", "camera_id": "front_door",  "type": "motion_detected",  "confidence": 0.80, "timestamp": (now - timedelta(hours=5, minutes=30)).isoformat(), "home_id": home_id},
        {"id": f"{h}_e12", "camera_id": "front_door",  "type": "motion_detected",  "confidence": 0.77, "timestamp": (now - timedelta(hours=5, minutes=25)).isoformat(), "home_id": home_id},
    ]

    demo_patterns = [
        {"id": f"{h}_p1", "home_id": home_id, "pattern_type": "rapid_return",        "fingerprint": "fp1", "salience_score": 8.2, "novelty_score": 9.0, "adaptation_score": 10.0, "temporal_weight": 0.8, "competition_score": 10.0, "flagged": True,  "explanation": _ex.generate_explanation({"pattern_type": "rapid_return",        "novelty_score": 9.0, "adaptation_score": 10.0, "salience_score": 8.2, "events": [{"timestamp": (now - timedelta(hours=2, minutes=5)).isoformat(), "camera": "front_door", "type": "person_detected"}, {"timestamp": (now - timedelta(hours=2, minutes=4)).isoformat(), "camera": "front_door", "type": "motion_detected"}, {"timestamp": (now - timedelta(hours=1, minutes=30)).isoformat(), "camera": "side_door", "type": "person_detected"}]}), "detected_at": (now - timedelta(hours=2)).isoformat(),            "event_ids": [f"{h}_e1", f"{h}_e2", f"{h}_e4"]},
        {"id": f"{h}_p2", "home_id": home_id, "pattern_type": "delivery",            "fingerprint": "fp2", "salience_score": 5.1, "novelty_score": 5.0, "adaptation_score": 5.0,  "temporal_weight": 0.8, "competition_score": 7.0,  "flagged": False, "explanation": _ex.generate_explanation({"pattern_type": "delivery",            "novelty_score": 5.0, "adaptation_score": 5.0,  "salience_score": 5.1, "events": [{"timestamp": (now - timedelta(hours=1, minutes=45)).isoformat(), "camera": "driveway",   "type": "vehicle_detected"}, {"timestamp": (now - timedelta(minutes=45)).isoformat(),          "camera": "front_door", "type": "doorbell"},         {"timestamp": (now - timedelta(minutes=44)).isoformat(),          "camera": "front_door", "type": "person_detected"}]}), "detected_at": (now - timedelta(hours=1, minutes=40)).isoformat(), "event_ids": [f"{h}_e3", f"{h}_e5", f"{h}_e6"]},
        {"id": f"{h}_p3", "home_id": home_id, "pattern_type": "unusual_entrance",    "fingerprint": "fp3", "salience_score": 7.5, "novelty_score": 8.0, "adaptation_score": 9.0,  "temporal_weight": 1.0, "competition_score": 5.0,  "flagged": True,  "explanation": _ex.generate_explanation({"pattern_type": "unusual_entrance",    "novelty_score": 8.0, "adaptation_score": 9.0,  "salience_score": 7.5, "events": [{"timestamp": (now - timedelta(minutes=8)).isoformat(),            "camera": "side_door",  "type": "person_detected"}]}),                                                                                                                                                                                                                                                                                           "detected_at": (now - timedelta(minutes=10)).isoformat(),           "event_ids": [f"{h}_e8"]},
        {"id": f"{h}_p4", "home_id": home_id, "pattern_type": "standard_activity",   "fingerprint": "fp4", "salience_score": 2.8, "novelty_score": 2.0, "adaptation_score": 3.0,  "temporal_weight": 0.8, "competition_score": 3.0,  "flagged": False, "explanation": _ex.generate_explanation({"pattern_type": "standard_activity",   "novelty_score": 2.0, "adaptation_score": 3.0,  "salience_score": 2.8, "events": [{"timestamp": (now - timedelta(minutes=20)).isoformat(),           "camera": "backyard",   "type": "motion_detected"}]}),                                                                                                                                                                                                                                                                                           "detected_at": (now - timedelta(minutes=22)).isoformat(),           "event_ids": [f"{h}_e7"]},
        {"id": f"{h}_p5", "home_id": home_id, "pattern_type": "late_first_activity", "fingerprint": "fp5", "salience_score": 6.8, "novelty_score": 7.0, "adaptation_score": 8.0,  "temporal_weight": 0.5, "competition_score": 5.0,  "flagged": True,  "explanation": _ex.generate_explanation({"pattern_type": "late_first_activity", "novelty_score": 7.0, "adaptation_score": 8.0,  "salience_score": 6.8, "events": [{"timestamp": (now - timedelta(hours=5, minutes=30)).isoformat(),  "camera": "front_door", "type": "motion_detected"}, {"timestamp": (now - timedelta(hours=5, minutes=25)).isoformat(),  "camera": "front_door", "type": "motion_detected"}]}),                                                                                                               "detected_at": (now - timedelta(hours=5, minutes=28)).isoformat(),  "event_ids": [f"{h}_e11", f"{h}_e12"]},
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


@app.post("/demo/clear")
def clear_demo_data(
    home_id: str = Query("home_001"),
    token: Optional[str] = Query(None),
):
    """Remove only the seeded demo records for this home (IDs prefixed with home_id)."""
    _require_demo_token(token)
    prefix = f"{home_id}_%"
    with get_db() as db:
        deleted_p = (
            db.query(PatternModel)
            .filter(PatternModel.home_id == home_id, PatternModel.id.like(prefix))
            .delete(synchronize_session=False)
        )
        deleted_e = (
            db.query(RingEventModel)
            .filter(RingEventModel.home_id == home_id, RingEventModel.id.like(prefix))
            .delete(synchronize_session=False)
        )
    return {"deleted_patterns": deleted_p, "deleted_events": deleted_e}


class FeedbackRequest(BaseModel):
    pattern_id: str
    feedback: str  # "normal" | "concerning"
    home_id: str = "home_001"


@app.post("/patterns/{pattern_id}/feedback")
def submit_pattern_feedback(pattern_id: str, req: FeedbackRequest):
    """
    User feedback on a flagged pattern. 'normal' feeds it into the baseline
    so similar future patterns score lower. 'concerning' is logged but has no
    immediate model effect (future work: increase adaptation weight).
    """
    with get_db() as db:
        pattern = repo.get_pattern_by_id(db, pattern_id)
        if not pattern:
            raise HTTPException(status_code=404, detail="Pattern not found")
        if req.feedback not in ("normal", "concerning"):
            raise HTTPException(status_code=400, detail="feedback must be 'normal' or 'concerning'")

        if req.feedback == "normal" and pattern.fingerprint:
            repo.upsert_baseline(db, pattern.home_id, pattern.fingerprint, pattern.pattern_type)
            # Also hydrate the in-memory engine so it takes effect immediately
            motif.baseline_patterns[pattern.fingerprint] = type(
                "BaselinePattern", (),
                {
                    "fingerprint": pattern.fingerprint,
                    "count": 5,  # treat as "seen several times" → lower novelty
                    "last_seen": None,
                    "first_seen": None,
                },
            )()

    return {
        "pattern_id": pattern_id,
        "feedback": req.feedback,
        "effect": "Added to baseline — similar patterns will score lower." if req.feedback == "normal"
                  else "Noted. Patterns like this will continue to be flagged.",
    }


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
