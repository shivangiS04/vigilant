# VIGILANT
### Behavioral Intelligence for Connected Homes

> A Ring-powered smart home security system that learns what "normal" looks like at your home and surfaces only the patterns that actually matter — powered by a drosophila-inspired attention model and AWS Bedrock.

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
2. **MOTIF Engine** groups events into sequences and scores each sequence on four axes.
3. If salience > 6.0, the pattern is **flagged** and sent to **AWS Bedrock** (Claude 3 Sonnet) for a natural-language explanation.
4. The **React dashboard** shows flagged patterns with explanations and the raw event timeline.

---

## The MOTIF Engine

MOTIF stands for the four scoring layers that produce a final **salience score (0–10)**:

| Layer | What It Asks | Weight |
|---|---|---|
| **Novelty** | How different is this from the learned baseline? | 40% |
| **Adaptation** | How many times have we seen this exact sequence before? | 30% |
| **Temporal** | How recent are these events? | 20% |
| **Competition** | How many other patterns fired today? | 10% |

```
Salience = (Novelty × 0.4) + (Adaptation × 0.3) + (Temporal × 0.2) + (Competition × 0.1)
```

**Example:** Person returns home 8 minutes after leaving (baseline is 4+ hours), enters through side door instead of front.
- Novelty: 9/10 (never matches baseline)
- Adaptation: 10/10 (first time ever)
- Temporal: 1.0× (just happened)
- Competition: 10/10 (only alert today)
- **Salience: 8.2 → FLAGGED**

Patterns with salience ≥ 6.0 get flagged and sent to Bedrock for an explanation. Everything below that is recorded but silent.

### Pattern Types

The engine classifies sequences into:

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
├── backend/
│   ├── motif_engine/
│   │   └── motif_core.py           ← The brain. All four scoring layers live here.
│   ├── bedrock_integration/
│   │   └── explanation_generator.py ← Builds prompts + calls AWS Bedrock.
│   │                                  Caches by pattern type (6h TTL) to cut latency.
│   ├── ring_integration/
│   │   └── api_client.py           ← Ring event poller + full simulator for dev.
│   │                                  No Ring hardware needed to develop.
│   ├── database/
│   │   └── models.py               ← SQLAlchemy ORM: homes, cameras, events,
│   │                                  patterns, baselines tables.
│   ├── api/
│   │   └── routes.py               ← FastAPI endpoints the dashboard hits.
│   └── main.py                     ← Entry point. Runs simulator + API server together.
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx                 ← Root component. Patterns / Events tab nav.
│   │   ├── components/
│   │   │   ├── PatternCard.jsx     ← Pattern with salience bar + flagged badge.
│   │   │   └── EventTimeline.jsx   ← Scrollable list of raw Ring events.
│   │   ├── hooks/
│   │   │   └── useEvents.js        ← useEvents + usePatterns polling hooks (30s).
│   │   └── utils/
│   │       └── api.js              ← Thin fetch wrappers for all API calls.
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
│
├── prompts/
│   ├── VIGILANT_Exact_Prompts.md   ← All Bedrock prompt templates with code.
│   └── VIGILANT_Prompts_QuickRef.md ← Quick reference by task / day.
│
├── requirements.txt
├── .env.example
└── README.md
```

---

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- AWS account with Bedrock access (for live explanations — not required for dev)
- PostgreSQL (optional for now — backend uses in-memory stores until wired up)

### 1. Clone & configure

```bash
git clone <repo-url>
cd vigilant
cp .env.example .env
# fill in your AWS creds if you have them — backend works without them
```

### 2. Backend

```bash
pip install -r requirements.txt
python -m backend.main
```

You'll see Ring simulator events printing every 5 seconds. API is live at `http://localhost:8000`.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard opens at `http://localhost:3000`.

---

## Testing Without AWS or Ring Hardware

The Ring simulator fires realistic fake events every 5 seconds in dev mode. To instantly populate the dashboard with demo patterns (instead of waiting for the simulator to accumulate enough events):

```bash
curl -X POST "http://localhost:8000/demo/seed?home_id=home_001"
```

This seeds 10 events and 4 patterns (2 flagged, 2 informational) with pre-written explanations so you can see the full UI immediately.

---

## API Reference

| Method | Endpoint | What It Does |
|---|---|---|
| GET | `/health` | Liveness check |
| GET | `/events?home_id=&hours=` | Recent Ring events |
| GET | `/patterns?home_id=&days=&flagged_only=` | Detected patterns |
| GET | `/patterns/{id}` | Single pattern detail |
| POST | `/patterns/score` | Score an event sequence on demand |
| GET | `/baseline?home_id=` | Learned baseline patterns for a home |
| POST | `/demo/seed?home_id=` | Seed dashboard with demo data |

### Score a pattern manually

```bash
curl -X POST http://localhost:8000/patterns/score \
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

Returns pattern type, all four layer scores, final salience, flagged status, and Bedrock explanation.

---

## AWS Bedrock Integration

File: `backend/bedrock_integration/explanation_generator.py`

- Model: `anthropic.claude-3-sonnet-20240229-v1:0`
- Max tokens: 150 (keeps explanations tight)
- Temperature: 0.3 (consistent, not creative)
- Tone is automatically adjusted by salience:
  - Salience > 7 → "Worth checking into" (alert, not alarmist)
  - Salience 4–7 → "This is different from usual" (informational)
  - Salience < 4 → "Just flagged as slightly unusual" (FYI)
- Explanations are cached by `(pattern_type, salience_bucket)` for 6 hours to avoid redundant Bedrock calls
- If Bedrock is unavailable, the dashboard degrades gracefully — pattern is still shown, explanation is just empty

To wire up Bedrock, add to `.env`:
```
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_DEFAULT_REGION=us-east-1
```

---

## Database (PostgreSQL)

File: `backend/database/models.py`

Five tables:

| Table | Purpose |
|---|---|
| `homes` | One row per property |
| `cameras` | Cameras per home |
| `ring_events` | Raw Ring events (indexed by home + timestamp) |
| `patterns` | MOTIF-scored sequences with explanation text |
| `baselines` | Learned normal fingerprints per home |

To spin up a local Postgres with Docker:
```bash
docker run -e POSTGRES_PASSWORD=vigilant -e POSTGRES_DB=vigilant -p 5432:5432 postgres
```

Then set `DATABASE_URL=postgresql://postgres:vigilant@localhost:5432/vigilant` in `.env` and run:
```bash
python -m backend.database.models
```

**Note:** The backend currently uses in-memory Python lists (`_events_store`, `_patterns_store` in `routes.py`) while the DB layer isn't wired up yet. That's the next thing to connect.

---

## What's Done vs. What's Next

### Done
- [x] MOTIF engine — all four scoring layers with real logic (not stubs)
- [x] Pattern classification (rapid_return, unusual_entrance, delivery, loitering, etc.)
- [x] Bedrock integration with prompt templates, caching, and graceful fallback
- [x] Ring simulator — generates realistic events, no hardware needed
- [x] FastAPI backend with all endpoints
- [x] React dashboard — Patterns tab + Events tab, polling, salience bar, flagged badge
- [x] PostgreSQL schema (ORM defined, not yet wired to routes)
- [x] Demo seed endpoint for instant UI testing

### Next Up
- [ ] Wire SQLAlchemy models to API routes (replace in-memory stores)
- [ ] Baseline learning: feed normal events into `engine.add_baseline()` over time
- [ ] MOTIF novelty using fingerprint similarity (not just exact match)
- [ ] Real Ring API or `ring_doorbell` library integration
- [ ] Pattern detail page (click a card → see the full event sequence)
- [ ] 7-day baseline comparison chart on dashboard
- [ ] Alexa skill integration for voice alerts

---

## Key Files to Read First

If you're jumping in, read these in order:

1. `backend/motif_engine/motif_core.py` — the core algorithm, fully commented
2. `backend/bedrock_integration/explanation_generator.py` — how prompts are built
3. `backend/api/routes.py` — all API endpoints in one file
4. `frontend/src/App.jsx` + `frontend/src/components/PatternCard.jsx` — UI entry points
5. `prompts/VIGILANT_Exact_Prompts.md` — the full Bedrock prompt reference

---

## Hackathon Notes

- **Track:** Ring (Primary) + AWS Builder (Mini Challenge)
- **Build period:** Sept 26 – Oct 24, 2026 (28 days)
- **Bonus:** Fill `FRICTION_LOG.md` as you hit issues — it's worth up to +10% on the judging score
- The `prompts/` folder has ready-to-paste templates for asking Claude for help on specific tasks (Ring integration, DB schema, dashboard components, etc.)
