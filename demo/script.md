# VIGILANT — Demo Video Script
**Target runtime: 2:40 | ~150 wpm | ~400 words**
*Amazon Developer Hackathon — Alexa + Ring Skills*

---

## Scene 1 — Problem (0:00–0:15) | 15 s
**Screen:** Black title card → "VIGILANT" fades in + tagline

> "Your Ring cameras see everything — but they treat every motion the same.
> A delivery truck. A rapid return. Someone entering through the side door at midnight.
> VIGILANT changes that."

---

## Scene 2 — Dashboard Overview (0:15–0:40) | 25 s
**Screen:** Dashboard — banner stats (91 events, 27 flagged, 67% suppressed), 7-day chart

> "This is the VIGILANT dashboard. In the last seven days, Ring sent 91 events
> to this home. VIGILANT grouped them into 83 behavioral patterns
> and flagged just 27 that actually needed attention —
> suppressing 67% of the noise automatically.
> The seven-day chart shows your home's activity fingerprint at a glance."

---

## Scene 3 — Rapid Return (0:40–1:15) | 35 s
**Screen:** Scroll to flagged cards → click Rapid Return card → PatternDetail opens

> "Here's why that matters. This morning, someone left through the front door
> and came back through the side door — eight minutes later.
> VIGILANT's MOTIF engine scored this pattern 6.4 out of 10 and flagged it.
> The engine uses four layers: novelty, adaptation, temporal weight, and competition —
> inspired by how the Drosophila fly filters sensory noise in real time.
> A sequence your home sees every day scores near zero. This one was new."

---

## Scene 4 — Architecture (1:15–1:35) | 20 s
**Screen:** Architecture diagram (README / static image)

> "Under the hood: Ring sends HMAC-signed webhooks. VIGILANT verifies the signature,
> normalises the payload, deduplicates events, and runs them through
> a sliding window of five. The MOTIF engine scores each window.
> High-salience patterns surface. Everything else is silently learned."

---

## Scene 5 — Learning / Feedback (1:35–1:55) | 20 s
**Screen:** Back on PatternDetail → click "This was normal" feedback button → salience badge updates

> "And VIGILANT learns from you. Mark a pattern as normal —
> and the next time something similar happens, the salience drops from 6.4 to 4.6.
> The pattern leaves your feed. Your baseline grows sharper with every correction."

---

## Scene 6 — Caretaking Scenario (1:55–2:15) | 20 s
**Screen:** Scroll to Late First Activity card → click → PatternDetail

> "Here's the pattern we care most about for this demo.
> No activity at this home until 2:30 in the afternoon.
> VIGILANT flagged it as 'late first activity' — a caretaking signal.
> If you're checking in on an elderly parent or a family member who lives alone,
> this is the alert that tells you something may be off."

---

## Scene 7 — Analytics Close (2:15–2:30) | 15 s
**Screen:** Scroll back up to banner + 7-day chart

> "67% noise suppression. A learned baseline. Caretaking-aware alerts.
> VIGILANT turns your Ring camera feed into behavioral intelligence —
> without ever leaving your own backend."

---

## Scene 8 — Close (2:30–2:40) | 10 s
**Screen:** Title card — "VIGILANT" + "github.com/shivangiS04/vigilant"

> "VIGILANT. Built for the Amazon Developer Hackathon.
> Open source. Try it today."

---

## Timings summary

| # | Scene                  | In    | Out   | Duration |
|---|------------------------|-------|-------|----------|
| 1 | Problem                | 0:00  | 0:15  | 0:15     |
| 2 | Dashboard overview     | 0:15  | 0:40  | 0:25     |
| 3 | Rapid return detail    | 0:40  | 1:15  | 0:35     |
| 4 | Architecture           | 1:15  | 1:35  | 0:20     |
| 5 | Learning / feedback    | 1:35  | 1:55  | 0:20     |
| 6 | Caretaking scenario    | 1:55  | 2:15  | 0:20     |
| 7 | Analytics close        | 2:15  | 2:30  | 0:15     |
| 8 | Title close            | 2:30  | 2:40  | 0:10     |
|   | **Total**              |       |       | **2:40** |

---

## Word count by scene (≈150 wpm)

| Scene | Words | Expected duration |
|-------|-------|-------------------|
| 1     | 36    | ~14 s ✓           |
| 2     | 57    | ~23 s ✓           |
| 3     | 88    | ~35 s ✓           |
| 4     | 51    | ~20 s ✓           |
| 5     | 44    | ~18 s ✓           |
| 6     | 54    | ~22 s ✓           |
| 7     | 35    | ~14 s ✓           |
| 8     | 18    | ~7 s ✓            |
| **Total** | **383** | **~2:33** |

*~7 s buffer for pauses and screen transitions — total ≤ 2:40.*

---

## Recording notes

- All demo data is from the signed simulator (HMAC-verified, same code path as real Ring)
- Do NOT show any real Ring account, credentials, or live device names
- Mention "signed simulator" naturally in Scene 4 — already scripted
- Cursor movements should be smooth and slow (Playwright `mouse.move` with steps)
- Pause 0.5 s on each card before clicking, 1 s on each detail view before scrolling away
