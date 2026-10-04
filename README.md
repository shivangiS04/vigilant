# VIGILANT
### Behavioral Intelligence for Connected Homes

> A Ring-powered smart home security system that learns what "normal" looks like at your home and surfaces only the patterns that actually matter — powered by a drosophila-inspired attention model and AWS Bedrock.

---

## Live Deployment

| | URL |
|---|---|
| **Dashboard** | https://vigilant-frontend-lac.vercel.app |
| **API** | https://vigilant-backend-omega.vercel.app |
| **GitHub** | https://github.com/shivangiS04/vigilant |

Seed the live backend with demo data:
```bash
curl -X POST "https://vigilant-backend-omega.vercel.app/demo/seed"
```

> **Note on persistence:** The live backend uses SQLite on Vercel's `/tmp` filesystem, which resets on cold starts (~15 min of inactivity). Re-run the seed curl if patterns disappear. To make it permanent, set `DATABASE_URL` to a hosted Postgres (e.g. Supabase free tier) in the Vercel project settings — no code changes needed.

---

## What This Is

Most Ring setups send 50+ daily alerts. People stop reading them. Real threats get buried in noise.

VIGILANT fixes this by watching *sequences* of events instead of individual triggers. It learns your home's normal behavior over time (person leaves at 8 AM, returns at 5:30 PM, always through the front door) and only alerts you when something meaningfully deviates from that baseline.

The core idea: a fruit fly's brain tunes out boring repeated stimuli and snaps to attention when something genuinely new happens. We implemented that same four-layer attention model (called **MOTIF**) on top of Ring event data, with AWS Bedrock generating the human-readable explanation.

---

## How It Works — End to End

```
Ring Events → MOTIF Engine → Salience Score → Bedrock Explanation → Dashboard
```

1. **Ring Integration** polls for events (person, motion, vehicle, doorbell) across all cameras.
2. **MOTIF Engine** groups events into sequences and scores each on four axes.
3. If salience > 6.0, the pattern is **flagged** and sent to **AWS Bedrock** (Claude 3 Sonnet) for a natural-language explanation.
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
| `standard_activity` | Normal, unclassified sequence |

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
│   ├── bedrock_integration/
│   │   └── explanation_generator.py ← Builds prompts + calls AWS Bedrock.
│   │                                  6h cache by pattern type to cut latency.
│   ├── ring_integration/
│   │   ├── api_client.py           ← Development simulator, only when explicitly selected.
│   │   ├── official_client.py      ← Official Ring Partner API HTTP/OAuth client.
│   │   ├── oauth.py                ← Encrypted tokens and one-way account linking.
│   │   ├── normalization.py        ← Ring webhook/history to Vigilant event mapping.
│   │   ├── security.py             ← Ring HMAC nonce and webhook signature checks.
│   │   └── pipeline.py             ← Shared event-to-MOTIF/Bedrock/Alexa pipeline.
│   ├── alexa_integration/
│   │   ├── client.py               ← AlexaClient: invokes Lambda on flagged patterns.
│   │   └── lambda_handler.py       ← Deploy to AWS Lambda (vigilant-alexa-announcer).
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
│   ├── VIGILANT_Exact_Prompts.md   ← All Bedrock prompt templates with code.
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
- AWS account with Bedrock access (for live explanations — not required for dev)

### 1. Clone & configure

```bash
git clone https://github.com/shivangiS04/vigilant.git
cd vigilant
cp .env.example .env
# optionally add AWS creds — backend works without them
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

```bash
curl -X POST "http://localhost:8000/demo/seed"
```

This endpoint is available only when `RING_INTEGRATION_MODE=simulator`.

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
| POST | `/demo/seed?home_id=` | Seed dashboard with demo data |

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
- Ring sends real-time motion and button-press notifications to `/ring/webhook`. Verified events are persisted and normalized, then passed through MOTIF; flagged patterns still use Bedrock and Alexa.
- Ring does not provide an event confidence value in these webhook payloads, so Vigilant stores and displays confidence as unavailable.
- Deploy this FastAPI backend before entering its HTTPS URLs in the Portal. Configure a durable PostgreSQL database before enabling real Ring accounts; Vercel's `/tmp` SQLite filesystem is ephemeral and unsuitable for Ring tokens or webhook deduplication.
- Webhook acknowledgement is separated from MOTIF/Bedrock processing. For production reliability across process restarts, deploy a durable background queue/worker; Ring may retry deliveries, and Vigilant deduplicates them by Ring's `meta.request_id`.

Official endpoint, token, nonce, event and signature behavior is documented at [Ring API Documentation](https://developer.amazon.com/docs/ring/api-documentation.html), [Configure](https://developer.amazon.com/docs/ring/configure.html), and [Getting Started](https://developer.amazon.com/docs/ring/get-started.html).

---

## Alexa Integration

VIGILANT fires an AWS Lambda (`vigilant-alexa-announcer`) whenever a pattern is flagged (salience ≥ 6.0). The Lambda builds a voice message and can be wired to any Alexa Proactive Events endpoint.

**To deploy:**

1. Create a Lambda function named `vigilant-alexa-announcer` (Python 3.11)
2. Copy `backend/alexa_integration/lambda_handler.py` into the Lambda editor and deploy
3. Set env vars:
   ```bash
   ALEXA_ENABLED=true
   ALEXA_LAMBDA_FUNCTION=vigilant-alexa-announcer
   AWS_ACCESS_KEY_ID=...
   AWS_SECRET_ACCESS_KEY=...
   ```

The integration silently fails if the Lambda is unavailable — core detection is never blocked.

---

## AWS Bedrock Integration

File: `backend/bedrock_integration/explanation_generator.py`

- Model: `anthropic.claude-3-sonnet-20240229-v1:0`
- Max tokens: 150 (keeps explanations tight)
- Temperature: 0.3 (consistent, not creative)
- Tone adjusts automatically by salience:
  - Salience > 7 → alert but not alarmist ("Worth checking into")
  - Salience 4–7 → informational ("This is different from usual")
  - Salience < 4 → low-key FYI ("Just flagged as slightly unusual")
- Explanations cached by `(pattern_type, salience_bucket)` for 6 hours
- If Bedrock is unavailable, dashboard degrades gracefully — pattern shown, explanation blank

Add to `.env` to enable:
```
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_DEFAULT_REGION=us-east-1
```

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
- [x] Bedrock integration with prompt templates, 6h cache, graceful fallback
- [x] Ring simulator — realistic events every 5s, no hardware needed
- [x] **Official Ring Partner API foundation** — one-way account linking, signed webhooks, encrypted token storage, no automatic simulator fallback
- [x] FastAPI backend fully wired to SQLite/Postgres via SQLAlchemy
- [x] React dashboard — Patterns / Analytics / Events tabs, 30s polling
- [x] Pattern detail view — click any card for score breakdown + explanation
- [x] **7-day baseline comparison chart** — AreaChart with color-coded dots, flag badges, responsive
- [x] **Alexa integration** — Lambda function + AlexaClient; fires on every flagged pattern
- [x] Demo seed endpoint for instant UI testing
- [x] Vercel deployment — frontend + backend both live

### Next Up
- [ ] Deploy Alexa Lambda to AWS + enable Proactive Events API in skill
- [ ] Persistent Postgres on Vercel (Supabase/Neon — just set `DATABASE_URL`)

---

## Key Files to Read First

1. `backend/motif_engine/motif_core.py` — the core algorithm
2. `backend/bedrock_integration/explanation_generator.py` — how prompts are built
3. `backend/database/repository.py` — all DB reads/writes
4. `backend/api/routes.py` — all API endpoints
5. `frontend/src/App.jsx` + `frontend/src/components/PatternCard.jsx` — UI entry points
6. `prompts/VIGILANT_Exact_Prompts.md` — full Bedrock prompt reference

---

## Hackathon Notes

- **Track:** Ring (Primary) + AWS Builder (Mini Challenge)
- **Build period:** Sept 26 – Oct 24, 2026 (28 days)
- **Bonus:** Fill `FRICTION_LOG.md` as you hit issues — worth up to +10% on judging score
- The `prompts/` folder has ready-to-paste templates for Ring integration, DB schema, dashboard components, and more
