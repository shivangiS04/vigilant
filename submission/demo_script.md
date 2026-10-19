# VIGILANT — Demo Script
**Target runtime:** 2:30–2:45
**Format:** Screen recording with voiceover. No background music needed.

---

## Setup before recording

1. Set `RING_INTEGRATION_MODE=simulator` and `RING_HMAC_SIGNING_KEY=<your key>`
2. Start backend: `python -m backend.main`
3. Start frontend: `cd frontend && npm run dev`
4. Open `http://localhost:3000` in a clean browser window (no other tabs visible)
5. Wait for simulator to send 2–3 webhook events so the Ring status panel shows a recent webhook
6. Confirm AWS credentials are set so Bedrock explanations are live

---

## Shot by shot

### [0:00–0:20] — The problem

**Screen:** Nothing on screen yet. Black or the VIGILANT logo.

**Voiceover:**
> "A typical Ring setup sends 50 motion alerts a day. After a week, most people stop reading them — and that's when a real threat gets missed. VIGILANT fixes this."

---

### [0:20–0:40] — The dashboard

**Screen:** Open `http://localhost:3000`. The dashboard loads showing:
- Noise reduction banner: "42 raw events → 7 patterns → 2 worth your attention — 95% noise suppressed"
- Ring status panel: green dots, linked account, devices, last webhook received and verified

**Voiceover:**
> "VIGILANT watches Ring events in sequences, not individually. It learns what's normal at your specific home and only surfaces the patterns that actually matter. Right now it's suppressing 95% of events — those are automatically filed as normal. Two patterns need attention."

**Pause 2 seconds on the noise reduction number.**

---

### [0:40–1:05] — Ring connection panel

**Screen:** Zoom in on the Ring status panel.

**Voiceover:**
> "The Ring connection is live. Account is linked via the official Ring Partner OAuth flow — no passwords stored. Devices are registered. The last webhook arrived 12 seconds ago and the HMAC signature was verified."

**Screen:** Switch to terminal briefly to show the simulator output:
```
[Ring] front_door: human  → webhook 200 (sig verified, request_id=a3f8b2c1…)
```

**Voiceover:**
> "Every incoming event is a properly signed Ring v1.1 webhook, verified before any processing happens."

---

### [1:05–1:35] — Flagged patterns

**Screen:** Back to dashboard. Click on the first flagged pattern card — "rapid return" with salience 8.2.

**Voiceover:**
> "This is a rapid return. Someone left through the front door and came back 8 minutes later — through the side door. That's unusual. The MOTIF engine scores it on four axes."

**Screen:** PatternDetail view is now visible. Walk through the score breakdown.

**Voiceover:**
> "Novelty: 9 out of 10 — no similar sequence in the baseline. Adaptation: 10 — first time ever. The final salience is 8.2 out of 10, which triggers an explanation from AWS Bedrock."

**Pause on the Bedrock explanation text.**

**Voiceover:**
> "That explanation was generated live by Claude 3.5 Haiku on AWS Bedrock — not pre-written."

---

### [1:35–2:00] — Feedback loop

**Screen:** Still in PatternDetail. The "Was this correct?" feedback box is visible.

**Voiceover:**
> "Here's the learning loop. If the homeowner recognizes this as normal — maybe they forgot their keys — they click 'This was normal.'"

**Action:** Click "This was normal."

**Screen:** Shows "✓ Marked as normal — Added to baseline. Similar patterns will score lower next time."

**Voiceover:**
> "VIGILANT immediately adds it to the baseline. The same pattern tomorrow will score lower, and eventually won't be flagged at all. The system gets smarter with every correction."

---

### [2:00–2:20] — Analytics tab

**Screen:** Navigate to Analytics tab. The 7-day baseline comparison chart loads.

**Voiceover:**
> "The Analytics tab shows 7-day activity versus the learned baseline. Today is a quiet day. Last Thursday spiked — two flagged patterns. The chart makes the noise reduction visible over time."

---

### [2:20–2:35] — Close

**Screen:** Back to Patterns tab. Both flagged patterns visible.

**Voiceover:**
> "VIGILANT turns a daily flood of Ring notifications into two things you actually need to see — with an explanation of why, and a way to teach it when it's wrong. Built on Ring's Partner API, AWS Bedrock, and a fruit-fly-inspired attention model."

**Screen:** Hold on VIGILANT logo in the header for 3 seconds.

---

## Notes

- If Bedrock isn't configured, pre-run a `/patterns/score` call that generates and caches one real explanation so at least one pattern in the demo has a live explanation. Or set up credentials — the demo is much stronger with real Bedrock output.
- The simulator generates events at a variable rate. If the dashboard is empty at start time, run `curl -X POST http://localhost:8000/demo/seed` to populate it instantly (patterns will show "[Sample]" label on explanations — mention it or switch to live mode).
- Keep the browser at 1280×720 or wider. The layout is responsive.
- Record at 60fps if possible — the salience bars animate on load and look good.
