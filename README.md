# VIGILANT
### Behavioral Intelligence for Connected Homes

> A Ring-powered smart home security system that learns what "normal" looks like at your home and surfaces only the patterns that actually matter — powered by a drosophila-inspired attention model, explainable by design.

---

## Live Deployment

| | URL |
|---|---|
| **Dashboard** | https://vigilant-frontend-lac.vercel.app |
| **API** | https://vigilant-backend-omega.vercel.app |
| **GitHub** | https://github.com/shivangiS04/vigilant |

Seed the live backend with demo data (requires `DEMO_SEED_TOKEN` set in Vercel env vars):
```bash
curl -X POST "https://vigilant-backend-omega.vercel.app/demo/seed?token=YOUR_DEMO_SEED_TOKEN"
# Clear demo data after the demo:
curl -X POST "https://vigilant-backend-omega.vercel.app/demo/clear?token=YOUR_DEMO_SEED_TOKEN"
```

---

## Branch Structure

| Branch | What's on it |
|---|---|
| `main` | Stable, tagged releases only |
| `ring-live-integration` | Sprint integration — all sprint work merged here |
| `security/secrets-gitleaks` | Gitleaks pre-commit + CI scan, `.db` files untracked, secrets scrubbed from docs |
| `fix/motif-loitering-timezone` | MOTIF engine: loitering fix, timezone-aware classification, 12 new tests |
| `feat/daily-summary-demo-seed` | `GET /daily-summary` route + Analytics digest card; demo seed token protection + `/demo/clear` + caretaking pattern |
| `docs/sprint-3-updates` | README API table, test count, submission files (final_report, description) |

---

## What This Is

Most Ring setups send 50+ daily alerts. People stop reading them. Real threats get buried in noise.

VIGILANT fixes this by watching *sequences* of events instead of individual triggers. It learns your home's normal behavior over time (person leaves at 8 AM, returns at 5:30 PM, always through the front door) and only alerts you when something meaningfully deviates from that baseline.

The core idea comes from neuroscience: Barlow (1961) proposed that sensory neurons are efficient encoders — they respond strongly to novel stimuli and suppress responses to repeated, predictable ones. The fruit fly olfactory system is a well-studied example of this: the fly's mushroom body rapidly habituates to familiar odors and snaps to attention when a genuinely new smell appears, even after hours of the familiar one. We implemented that same four-layer attention model (called **MOTIF**) on top of Ring event data — the system habituates to your home's normal rhythms and fires only when something deviates in a way that would have mattered in a real nervous system. A rule-based explainer then turns that score into a plain-language explanation derived from the actual scoring data.

---

## How It Works — End to End

![VIGILANT architecture diagram](submission/architecture.png)

```mermaid
flowchart LR
    subgraph Ring["Ring"]
        RA["Ring Partner API\nOAuth · account linking\ndevices API\n(not verified live)"]
        SIM["Signed Simulator\nHMAC-signed v1.1 payloads"]
    end

    subgraph Backend["Backend — FastAPI — Vercel"]
        WH["POST /ring/webhook"]
        HMAC["HMAC\nsignature check"]
        NORM["Normalize\nevent type · camera · timestamp"]
        DEDUP["Dedup\nby request_id"]
        MOTIF["MOTIF Engine\n5-event sliding window\nnovelty · adaptation\ntemporal · competition\nsalience + pattern type"]
        EXPL["Rule-based Explainer\npattern → plain-language why"]
        API["REST API\n/events · /patterns\n/ring/status · /daily-summary"]
        FB["User Feedback\n'this was normal'\nupserts baseline"]
    end

    subgraph Data["Data"]
        DB[("Neon Postgres\nevents · patterns\nbaselines\nRing tokens encrypted")]
    end

    subgraph Frontend["Frontend — React — Vercel"]
        DASH["Dashboard\nPatterns · Analytics · Events\nRing Status · Daily Digest"]
    end

    RA -->|"OAuth / account link"| DB
    RA -->|"real webhooks"| WH
    SIM -->|"signed webhook POST"| WH
    WH --> HMAC
    HMAC -->|"verified"| NORM
    NORM -->|"normalized event"| DEDUP
    DEDUP -->|"save event"| DB
    DEDUP -->|"5-event window"| MOTIF
    MOTIF -->|"salience > 6: flag"| EXPL
    EXPL -->|"save flagged pattern"| DB
    MOTIF -->|"salience < 4: auto-learn"| DB
    DB -.->|"load baseline on startup"| MOTIF
    DASH -->|"'this was normal'"| FB
    FB -->|"upsert baseline"| DB
    DASH -->|"GET /events /patterns\n/ring/status /daily-summary"| API
    API -->|"query"| DB
    DB -->|"results"| API
    API -->|"responses"| DASH

    style MOTIF fill:#4f46e5,color:#fff,stroke:#3730a3
```

1. **Ring Integration** delivers events (person, motion, vehicle, doorbell) via signed webhooks across all cameras.
2. **MOTIF Engine** groups events into sequences and scores each on four axes.
3. If salience > 6.0, the pattern is **flagged** and the rule-based explainer generates a natural-language explanation from the actual score data.
4. Low-salience patterns (< 4.0) are **auto-learned** as "normal" and written to the baseline DB.
5. The **React dashboard** shows flagged patterns with explanations, score breakdowns, and the raw event timeline.

---

## The MOTIF Engine

MOTIF scores how much a pattern deserves attention using four layers. Final score is a weighted sum:

| Layer | What It Asks | Weight |
|---|---|---|
| **Novelty** | How different is this from the learned baseline? (Jaccard similarity) | 40% |
| **Adaptation** | How many times have we seen this exact sequence before? | 30% |
| **Temporal** | How recent are these events? | 20% |
| **Competition** | How many other patterns fired today? | 10% |

```
Salience = (Novelty × 0.4) + (Adaptation × 0.3) + (Temporal × 0.2) + (Competition × 0.1)
```

**Example:** Person returns home 8 minutes after leaving (baseline is 4+ hours), enters through side door.
- Novelty: 9/10 (no match in baseline — Jaccard similarity near zero)
- Adaptation: 10/10 (first time ever)
- Temporal: 1.0× (just happened)
- Competition: 10/10 (only alert today)
- **Salience: 8.2 → FLAGGED**

Patterns ≥ 6.0 get flagged and explained. Everything below is recorded silently and fed back into the baseline so the system gets smarter over time.

### Pattern Types

| Pattern | Description |
|---|---|
| `rapid_return` | Person left and came back in < 15 minutes |
| `unusual_entrance` | First event on side/back/garage camera |
| `loitering` | 3+ motion events with no clear departure |
| `delivery` | Vehicle detected → person detected sequence |
| `multi_camera_activity` | Activity across 3+ cameras in a short window |
| `late_first_activity` | First event of the day at a primary entrance after 2 PM with no person detected — useful for caretaking |
| `late_night_activity` | Person detected between 11 PM and 5 AM |
| `standard_activity` | Normal, unclassified sequence |

---

## Who This Is For

**Families with elderly or solo-living parents.** A parent who always opens the front door by 8:30 AM and hasn't by noon is an important signal. VIGILANT detects that change in routine (the `late_first_activity` pattern) and flags it — not because someone triggered a sensor, but because the expected pattern is absent.

**People who've stopped reading Ring alerts.** If you've turned off Ring notifications because they were too frequent, VIGILANT is designed for you. It reads all 50 daily alerts so you don't have to, and surfaces only the sequences that actually deviate.

**Anyone in a home with a specific daily rhythm.** VIGILANT learns your rhythm — not a generic "usual pattern" — and flags deviations from it. It gets more accurate with every correction you make.

---

## Project Structure

```
vigilant/
├── api/
│   └── index.py                    ← Vercel serverless entry point (wraps FastAPI app)
│
├── backend/
│   ├── motif_engine/
│   │   └── motif_core.py           ← The brain. All four scoring layers + Jaccard novelty.
│   ├── explanation/
│   │   └── explainer.py            ← Rule-based explainer. Templates per pattern
│   │                                  type, driven by real MOTIF score data.
│   ├── ring_integration/
│   │   ├── api_client.py           ← Development simulator, only when explicitly selected.
│   │   ├── official_client.py      ← Official Ring Partner API HTTP/OAuth client.
│   │   ├── oauth.py                ← Encrypted tokens and one-way account linking.
│   │   ├── normalization.py        ← Ring webhook/history to Vigilant event mapping.
│   │   ├── security.py             ← Ring HMAC nonce and webhook signature checks.
│   │   └── pipeline.py             ← Shared event-to-MOTIF/explainer/Alexa pipeline.
│   ├── alexa_integration/
│   │   ├── client.py               ← AlexaClient: invokes Lambda on flagged patterns.
│   │   └── lambda_handler.py       ← Deploy as a Lambda (vigilant-alexa-announcer).
│   ├── database/
│   │   ├── models.py               ← SQLAlchemy ORM: homes, cameras, events,
│   │   │                              patterns, baselines (SQLite + Postgres compatible)
│   │   ├── session.py              ← DB session factory. SQLite default, Postgres via env.
│   │   └── repository.py           ← All CRUD operations + baseline comparison query.
│   ├── api/
│   │   └── routes.py               ← FastAPI endpoints. All wired to DB.
│   └── main.py                     ← API server; simulator starts only when explicitly selected.
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx                 ← Root. Patterns / Analytics / Events tabs.
│   │   ├── components/
│   │   │   ├── PatternCard.jsx     ← Clickable card: salience bar + flagged badge.
│   │   │   ├── PatternDetail.jsx   ← Detail view: score breakdown + explanation.
│   │   │   ├── EventTimeline.jsx   ← Raw Ring event list.
│   │   │   ├── DailySummary.jsx    ← Today's digest: stat tiles, salience bar, top alert.
│   │   │   └── BaselineComparison.jsx ← 7-day activity vs. baseline AreaChart (Recharts).
│   │   ├── hooks/
│   │   │   └── useEvents.js        ← useEvents + usePatterns polling hooks (30s interval).
│   │   └── utils/
│   │       └── api.js              ← Fetch wrappers. Reads VITE_API_URL for prod.
│   ├── .env.production             ← Points frontend at live Vercel backend.
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
│
├── prompts/
│   └── VIGILANT_Prompts_QuickRef.md ← Quick reference by task / day.
│
├── vercel.json                     ← Vercel build + routing config.
├── requirements.txt
├── .env.example
└── README.md
```

---

## Local Setup

### Prerequisites

- Python 3.11+
- Node.js 18+

### 1. Clone & configure

```bash
git clone https://github.com/shivangiS04/vigilant.git
cd vigilant
cp .env.example .env
```

### 2. Backend

```bash
pip install -r requirements.txt
python -m backend.main
```

Official mode is the default and waits for Ring webhooks; Ring cannot reach localhost without a public HTTPS tunnel. The API is available at `http://localhost:8000`, and SQLite (`vigilant.db`) is created automatically. To run generated events locally, explicitly select simulator mode:

```powershell
$env:RING_INTEGRATION_MODE = "simulator"
python -m backend.main
```

The simulator is never used as an automatic fallback for official Ring mode.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard at `http://localhost:3000`.

### 4. Seed demo data

In simulator mode (local dev — no token needed):
```bash
curl -X POST "http://localhost:8000/demo/seed"
```

In official mode (live judge demo — requires `DEMO_SEED_TOKEN` set in env):
```bash
curl -X POST "http://localhost:8000/demo/seed?token=YOUR_DEMO_SEED_TOKEN"
# Clear after the demo:
curl -X POST "http://localhost:8000/demo/clear?token=YOUR_DEMO_SEED_TOKEN"
```

---

## Deploying to Vercel

Both frontend and backend are deployed as separate Vercel projects.

### Prerequisites

```bash
npm install -g vercel
vercel login
```

### Deploy backend

```bash
cd vigilant   # project root
vercel --prod --yes
```

### Deploy frontend

```bash
cd frontend
vercel --prod --yes
```

After both are deployed, set the backend URL in `frontend/.env.production`:

```
VITE_API_URL=https://your-backend.vercel.app
```

Then redeploy the frontend:

```bash
cd frontend && vercel --prod --yes
```

### Upgrading to persistent Postgres

The live deploy uses SQLite on `/tmp` (resets on cold start). To make data permanent:

1. Create a free Postgres on [Supabase](https://supabase.com) or [Neon](https://neon.tech)
2. In Vercel dashboard → vigilant-backend → Settings → Environment Variables, set:
   ```
   DATABASE_URL = postgresql://user:pass@host:5432/dbname
   ```
3. Redeploy — no code changes needed

---

## API Reference

Base URL (local): `http://localhost:8000`
Base URL (prod): `https://vigilant-backend-omega.vercel.app`

| Method | Endpoint | What It Does |
|---|---|---|
| GET | `/health` | Liveness check |
| GET | `/events?home_id=&hours=` | Recent Ring events |
| GET | `/patterns?home_id=&days=&flagged_only=` | Detected patterns |
| GET | `/patterns/{id}` | Single pattern with full score breakdown |
| POST | `/patterns/score` | Score an event sequence on demand |
| GET | `/baseline?home_id=` | Learned baseline patterns for a home |
| GET | `/baseline-comparison?home_id=&days=` | 7-day activity vs. historical baseline |
| GET | `/daily-summary?home_id=` | 24h digest: event/pattern counts, noise reduction %, top alert |
| POST | `/demo/seed?home_id=&token=` | Seed dashboard with sample data (simulator, or token in official mode) |
| POST | `/demo/clear?home_id=&token=` | Remove seeded demo records |

### Score a pattern manually

```bash
curl -X POST https://vigilant-backend-omega.vercel.app/patterns/score \
  -H "Content-Type: application/json" \
  -d '{
    "home_id": "home_001",
    "events": [
      {"camera":"front_door","type":"person_detected","timestamp":"2026-09-26T14:30:00","confidence":0.95},
      {"camera":"side_door","type":"person_detected","timestamp":"2026-09-26T14:32:00","confidence":0.89},
      {"camera":"side_door","type":"motion_detected","timestamp":"2026-09-26T14:33:00","confidence":0.84}
    ]
  }'
```

---

## Official Ring Partner API

Vigilant uses Ring's Ring-driven one-way account-linking flow. Ring customers authorize the app and choose devices in the Ring app; Vigilant never requests or stores a Ring email or password. Ring sends a short-lived authorization code to `/ring/token`. Vigilant exchanges it server-to-server, gets the account ID from `/v1/users/me`, and encrypts the access and refresh tokens in the database. The customer then signs into Vigilant at `/ring/link`; after explicit confirmation, Vigilant validates Ring's time-bound HMAC nonce and calls Ring's required app-integration `POST` and `PATCH` operations.

### Ring Developer Portal setup

1. Register a Ring app and select the Cameras and Doorbells access group needed for motion and doorbell events. Complete the Ring developer account verification and app setup required by the Portal.
2. Copy the `Client ID`, `Client Secret`, and one-time `HMAC Signature Key` into backend-only secret configuration. The HMAC key is used for account-link nonce validation and webhook verification.
3. Configure the HTTPS endpoints below in the Ring Portal's staging settings, then configure production after deployment. Ring requires all four URLs to be publicly reachable over HTTPS.

For the current backend deployment shown above, use:

| Ring Portal field | HTTPS URL |
|---|---|
| Account Link URL | `https://vigilant-backend-omega.vercel.app/ring/link` |
| App Homepage URL | `https://vigilant-backend-omega.vercel.app/ring` |
| Token Exchange URL | `https://vigilant-backend-omega.vercel.app/ring/token` |
| Webhook URL | `https://vigilant-backend-omega.vercel.app/ring/webhook` |

If the backend domain changes, update all four Portal URLs. Do not configure the frontend domain for these backend endpoints.

Ring's public reference says it POSTs the one-time authorization code to the Token Exchange URL and requires exchange within 60 seconds, but does not specify the inbound callback's content type or exact field names on the pages available. `/ring/token` accepts JSON or URL-encoded bodies with `code` or `authorization_code`; verify the actual staging callback shape in the Ring Portal's Test flow before production.

### Backend environment

Set these values in local `.env` or the backend deployment's secret settings. Do not put real credentials in `.env.example` or frontend variables.

```text
RING_INTEGRATION_MODE=official
RING_CLIENT_ID=<Ring Developer Portal Client ID>
RING_CLIENT_SECRET=<Ring Developer Portal Client Secret>
RING_HMAC_SIGNING_KEY=<Ring Developer Portal HMAC Signature Key>
RING_TOKEN_ENCRYPTION_KEY=<Fernet key generated for this deployment>
RING_SESSION_SECRET=<stable random session-signing secret>
RING_COOKIE_SECURE=true
VIGILANT_ACCOUNT_EMAIL=<Vigilant account email>
VIGILANT_ACCOUNT_PASSWORD_HASH=<PBKDF2 hash for the Vigilant account>
DATABASE_URL=<durable PostgreSQL connection URL>
HOME_ID=home_001
```

Generate the token-encryption key and session secret:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Generate a PBKDF2 password hash for the **Vigilant** sign-in used to claim the Ring nonce:

```powershell
python -c "from getpass import getpass; from backend.ring_integration.partner_auth import create_password_hash; print(create_password_hash(getpass()))"
```

Use the output as `VIGILANT_ACCOUNT_PASSWORD_HASH`. This is not a Ring password. The current backend foundation supports one configured Vigilant account; connect a full multi-user identity provider before offering account linking to multiple unrelated Vigilant users.

### Local and production behavior

- `RING_INTEGRATION_MODE=official` is the default. It never generates fake Ring events and waits for signed Ring webhooks.
- `RING_INTEGRATION_MODE=simulator` explicitly enables the local development generator and `/demo/seed`.
- Ring sends real-time motion and button-press notifications to `/ring/webhook`. Verified events are persisted and normalized, then passed through MOTIF; flagged patterns get a rule-based explanation and trigger Alexa if enabled.
- Ring does not provide an event confidence value in these webhook payloads, so Vigilant stores and displays confidence as unavailable.
- Deploy this FastAPI backend before entering its HTTPS URLs in the Portal. Configure a durable PostgreSQL database before enabling real Ring accounts; Vercel's `/tmp` SQLite filesystem is ephemeral and unsuitable for Ring tokens or webhook deduplication.
- Webhook acknowledgement is separated from MOTIF/explanation processing. For production reliability across process restarts, deploy a durable background queue/worker; Ring may retry deliveries, and Vigilant deduplicates them by Ring's `meta.request_id`.

Official endpoint, token, nonce, event and signature behavior is documented at [Ring API Documentation](https://developer.amazon.com/docs/ring/api-documentation.html), [Configure](https://developer.amazon.com/docs/ring/configure.html), and [Getting Started](https://developer.amazon.com/docs/ring/get-started.html).

---

## Planned: Alexa Voice Announcements

The Lambda handler (`backend/alexa_integration/lambda_handler.py`) and client (`backend/alexa_integration/client.py`) are written and tested locally. The integration is **disabled by default** (`ALEXA_ENABLED=false`) and makes no Alexa calls in the current deployment.

Completing the integration requires:
1. Alexa Developer Console: create a skill with Proactive Events permissions and submit it for certification
2. Ring Portal: register the Alexa skill link under the app's Alexa integration settings
3. AWS Lambda: deploy `lambda_handler.py` as `vigilant-alexa-announcer`
4. Set `ALEXA_ENABLED=true` in backend env vars once the skill is certified

This is tracked as future work. The core detection pipeline (Ring → MOTIF → rule-based explanation) is fully functional without it.

---

## Explainable by Design

File: `backend/explanation/explainer.py`

Every flagged pattern comes with a plain-language explanation derived entirely from the MOTIF score data — no LLM, no network calls, no external API keys required.

The `RuleBasedExplainer` generates two types of output:

**Pattern explanation** (`generate_explanation(pattern_data)`): builds a 1–2 sentence explanation from the actual event sequence and scores.

| Layer | What drives the explanation |
|---|---|
| `pattern_type` | Template sentence specific to rapid_return, loitering, delivery, etc. |
| `novelty_score ≥ 8` | "No matching sequence in the learned baseline" |
| `novelty_score 6–8` | "Rarely seen in the baseline" |
| `adaptation_score ≥ 9` | "First time this sequence has been recorded" |
| cameras + timestamps | Real camera names and local time from `HOME_TIMEZONE` |

**Daily digest** (`generate_daily_summary(patterns, date)`): total counts, flagged count with highest-salience pattern, breakdown by type.

No API keys, environment variables, or internet access needed for explanations to work.

---

## Database

File: `backend/database/models.py`

Works with SQLite (zero setup, default) and PostgreSQL (set `DATABASE_URL`).

| Table | Purpose |
|---|---|
| `homes` | One row per property |
| `cameras` | Cameras per home |
| `ring_events` | Raw Ring events (indexed by home + timestamp) |
| `patterns` | MOTIF-scored sequences with score breakdown + explanation |
| `baselines` | Auto-learned normal fingerprints per home |

Local Postgres (Docker):
```bash
docker run -e POSTGRES_PASSWORD=vigilant -e POSTGRES_DB=vigilant -p 5432:5432 postgres
# then set in .env:
DATABASE_URL=postgresql://postgres:vigilant@localhost:5432/vigilant
```

---

## What's Done vs. What's Next

### Done
- [x] MOTIF engine — all four scoring layers with real logic
- [x] Novelty scoring upgraded to Jaccard similarity (fuzzy, not just exact match)
- [x] Baseline auto-learning — low-salience patterns written to DB automatically
- [x] Baseline hydration on startup — MOTIF engine loads from DB on every boot
- [x] Pattern classification (rapid_return, unusual_entrance, delivery, loitering, etc.)
- [x] Rule-based explanation engine — deterministic, no API keys, driven by real MOTIF scores
- [x] Ring simulator — realistic events every 5s, no hardware needed
- [x] **Official Ring Partner API foundation** — one-way account linking, signed webhooks, encrypted token storage, no automatic simulator fallback
- [x] FastAPI backend fully wired to SQLite/Postgres via SQLAlchemy
- [x] React dashboard — Patterns / Analytics / Events tabs, 30s polling
- [x] Pattern detail view — click any card for score breakdown + explanation
- [x] **7-day baseline comparison chart** — AreaChart with color-coded dots, flag badges, responsive
- [x] Demo seed endpoint — simulator mode (no token) or official mode (DEMO_SEED_TOKEN); `/demo/clear` to clean up after judge demos
- [x] **Daily digest** — `GET /daily-summary` + Analytics tab digest card (stat tiles, noise %, top alert, pattern breakdown)
- [x] Vercel deployment — frontend + backend both live
- [x] CI pipeline — GitHub Actions, 80 tests passing
- [x] FRICTION_LOG.md — real dev issues documented

### Next Up / Planned
- [ ] **Alexa voice announcements** — Lambda handler + AlexaClient are written; skill certification and Proactive Events API setup are the remaining steps (see [Planned: Alexa Voice Announcements](#planned-alexa-voice-announcements))
- [x] Persistent Postgres on Vercel — set `DATABASE_URL` to your Neon connection string in Vercel settings; no code changes needed
- [ ] Push notifications via SNS for flagged patterns when homeowner is away

---

## Key Files to Read First

1. `backend/motif_engine/motif_core.py` — the core algorithm
2. `backend/explanation/explainer.py` — how explanations are built from MOTIF scores
3. `backend/database/repository.py` — all DB reads/writes
4. `backend/api/routes.py` — all API endpoints
5. `frontend/src/App.jsx` + `frontend/src/components/PatternCard.jsx` — UI entry points

---

## Hackathon Notes

- **Track:** Ring (Primary)
- **Build period:** Sept 26 – Oct 24, 2026 (28 days)
- **Bonus:** Fill `FRICTION_LOG.md` as you hit issues — worth up to +10% on judging score
- The `prompts/` folder has ready-to-paste templates for Ring integration, DB schema, dashboard components, and more
