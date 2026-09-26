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
│   │   ├── api_client.py           ← Ring event poller + full simulator (fires every 5s).
│   │   └── real_api_client.py      ← Real Ring API via ring_doorbell library.
│   │                                  Set RING_USE_SIMULATOR=false + credentials to activate.
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
│   └── main.py                     ← Local entry point: real Ring or simulator + API server.
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

Ring simulator fires every 5 seconds. API is live at `http://localhost:8000`. SQLite DB (`vigilant.db`) is created automatically in the project root.

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

Instantly populates 10 events and 4 patterns (2 flagged) so you can see the full UI without waiting for the simulator.

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

## Real Ring API

By default the backend runs the built-in simulator. To connect to a real Ring account:

1. Install the library (already in `requirements.txt`):
   ```bash
   pip install ring-doorbell
   ```

2. Set env vars (locally in `.env`, or in Vercel dashboard):
   ```bash
   RING_USE_SIMULATOR=false
   RING_EMAIL=your-ring-email@gmail.com
   RING_PASSWORD=your-ring-password
   ```

3. Restart the backend — it will attempt real Ring, fall back to simulator on failure.

File: `backend/ring_integration/real_api_client.py`

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
- [x] **Real Ring API client** — `ring_doorbell` library, env-variable switching, graceful fallback to simulator
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
