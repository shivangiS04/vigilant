# VIGILANT — Behavioral Intelligence for Connected Homes

**Track:** Ring (Primary)
**Team:** Shivangi Singh, Archisha Srivastava
**Built:** September 26 – October 24, 2026

---

## The Problem

The average Ring setup generates 50+ motion alerts per day. Most homeowners stop reading them within a week. Real threats — a stranger loitering for 20 minutes, a family member not following their usual routine, an unusual late-night entry — get buried in noise.

Individual-event alerts are the wrong unit of analysis. A motion alert means nothing. A *sequence* — vehicle detected, then unfamiliar person, then front door opened 3 minutes later, all outside normal hours — means something.

---

## What VIGILANT Does

VIGILANT watches Ring events in sequences, not individually. It learns what "normal" looks like at a specific home over time and surfaces only the patterns that meaningfully deviate from that baseline.

The result: **90%+ of Ring events are silently classified as normal.** The homeowner sees only the handful of sequences that actually warrant attention, with a plain-language explanation of why — generated deterministically from the actual MOTIF score data.

---

## How It Works

```
Ring webhooks → MOTIF Engine → Salience Score → Rule-Based Explanation → Dashboard
```

### The MOTIF Engine

The core algorithm is inspired by how a fruit fly's nervous system tunes out repeated stimuli and snaps to attention when something genuinely new happens (Barlow 1961, "Possible principles underlying the transformations of sensory messages"). We implemented that same principle as a four-layer attention model:

| Layer | What it asks | Weight |
|---|---|---|
| **Novelty** | How different is this from the learned baseline? (Jaccard similarity on event fingerprints) | 40% |
| **Adaptation** | How many times have we seen this exact sequence before? | 30% |
| **Temporal** | How recent is this? | 20% |
| **Competition** | How many other patterns fired today? | 10% |

The final salience score (0–10) determines whether a pattern is flagged (≥ 6.0) or silently auto-learned as "normal" (< 4.0). Low-salience patterns are automatically written to the baseline database, so the system gets smarter with every day of use.

### Ring Integration

VIGILANT uses the Ring Partner API for the full production integration:
- **OAuth 2.0 account linking** — Ring customers authorize VIGILANT in the Ring app. Ring POSTs a short-lived code to our Token Exchange URL. We exchange it server-to-server and store encrypted tokens (Fernet) in the database.
- **HMAC-signed webhooks** — Ring delivers real-time motion and doorbell events to `/ring/webhook`. Every payload is verified against the HMAC-SHA256 signature before processing.
- **Webhook deduplication** — Ring may retry deliveries. We deduplicate by Ring's `meta.request_id`.
- **Account link nonce** — We validate Ring's time-bound (10-minute) HMAC nonce before completing the account link.

### Explainable by Design

Explanations are generated deterministically by `backend/explanation/explainer.py` — a rule-based engine that produces a 1–2 sentence explanation from the actual MOTIF score data: the pattern type, the camera names and local timestamps, and the novelty/adaptation scores vs. the learned baseline. No API keys, no network calls, no external dependencies.

---

## Who It's For

**Families with elderly or solo-living parents.** A parent who always opens the front door by 8:30 AM and hasn't by noon is an important signal. VIGILANT detects that change in routine (the `late_first_activity` pattern) and flags it — not because someone triggered a sensor, but because the expected pattern is absent.

**People who've stopped reading Ring alerts.** If you've ever turned off Ring notifications because they were too frequent, VIGILANT is designed for you. It reads all 50 daily alerts so you don't have to.

**Anyone in a home with a specific daily rhythm.** VIGILANT learns your rhythm — not a generic "usual pattern" — and flags deviations from it.

---

## What We Built

- **Ring Partner API integration** — OAuth account linking, HMAC webhook verification, signed-payload deduplication, encrypted token storage. All the production plumbing.
- **MOTIF engine** — Four-layer salience scoring with Jaccard fuzzy novelty and auto-learning baseline.
- **HMAC-signed simulator** — Exercises the real Ring code path locally: builds v1.1 payloads, signs them, and POSTs to `/ring/webhook`. No bypassing of any real code.
- **React dashboard** — Live noise-reduction stats (X events → Y patterns → Z flagged), Ring connection status panel, 7-day baseline comparison chart, pattern score breakdown, and a feedback loop ("This was normal") that teaches the system.
- **Rule-based explanation engine** — deterministic explanations from real MOTIF score data; no LLM, no API keys, always available.
- **Daily digest** — `GET /daily-summary` surfaces a 24h digest card in the Analytics tab: total events, patterns, flagged count, noise reduction %, avg salience, and the top alert explanation.
- **Full test suite** — 80 tests including HMAC verification, webhook normalization against official payload shapes, deduplication, timezone edge cases, and end-to-end webhook → pipeline tests.
- **CI pipeline** — GitHub Actions, runs on every push.

---

## Challenges

The two biggest friction points:
1. **Ring has no official webhook simulator.** We built one from scratch that produces HMAC-signed v1.1 payloads, because the Playground does not deliver webhooks and we needed to test the full code path locally.
2. **Vercel serverless kills BackgroundTasks after the response.** FastAPI's background tasks don't survive the process termination. We detect `VERCEL=1` and switch to synchronous processing to ensure Ring's 5-second acknowledgement window is met while still processing every event.

See `FRICTION_LOG.md` for the full record of what we hit and how we solved it.

---

## What's Next

- **Alexa Proactive Events** — Voice announcements on flagged patterns. The Lambda handler and AlexaClient are built; the Proactive Events skill permissions and Alexa account setup are the remaining steps.
- **Multi-user identity** — The current account-link flow supports one configured Vigilant account. A full multi-user deployment needs an identity provider (Cognito, Auth0).
- **Push notifications** — SMS/email via SNS for flagged patterns when the homeowner is away.
- **Caretaking preset** — A configured profile for monitoring a specific person's daily routine, with its own baseline separate from the home-level baseline.

---

*VIGILANT was built during the Amazon Developer Hackathon 2026, September 26 – October 24.*
