# VIGILANT — Feature Requests for Ring
**Submitted by:** Shivangi Singh, Archisha Srivastava
**Hackathon:** Amazon Developer Hackathon 2026 — Ring Track
**Date:** October 2026

---

## Ring Partner API — Feature Requests

### FR-R1: Webhook simulator CLI tool
**Urgency: Critical**

Ship a `ring webhook forward` command (or equivalent) that:
- Listens for events from a staging account
- Forwards them as properly signed webhooks to a local URL

Or at minimum: provide a curl command in the docs that sends a valid, HMAC-signed v1.1 test payload to any URL, with the signing logic shown explicitly.

**Why:** Every Ring Partner developer needs to test their webhook handler before going to production. Without a simulator, developers have to either deploy to a public URL first (which slows the dev loop by 10–30 minutes per test cycle) or build their own simulator (which takes days). Stripe, GitHub, Shopify, and Twilio all ship this as a first-class developer tool. It is the single most important developer-experience improvement Ring could make for the Partner API.

**Impact:** Reduces time-to-first-signed-webhook from hours/days to minutes.

---

### FR-R2: Complete payload schema documentation for all event types
**Urgency: High**

Publish a complete JSON schema (or at minimum a table) for every webhook event type:
- `motion_detected`
- `button_press` / `ding`
- `app_integration_removed`
- `app_integration_added`
- Any other types that may exist

For each: list all fields, their types, which are required vs. optional, and the full enumeration of sub_type values.

**Why:** Developers implementing normalization and routing logic need to know the exact shape of every payload. Undocumented types and undocumented fields cause real bugs — we had a test failure traced to `app_integration_removed` having empty attributes, which was not in the docs.

---

### FR-R3: Clarify HMAC Signature Key lifecycle and rotation policy
**Urgency: High**

In the Portal and in the docs, explicitly state:
1. The HMAC Signature Key is a stable deployment secret (not per-session or per-flow)
2. Whether it ever rotates, and if so, how (manual, automatic, on what events)
3. What happens to signed payloads after rotation (grace period?)

**Why:** "One-time" is ambiguous. Developers who misread it as "rotates each flow" will implement incorrect signature verification. Developers who use it for both nonce signing and webhook signing may be confused about scope.

---

### FR-R4: Staging webhook delivery confirmation
**Urgency: Medium**

On the Developer Portal Test page, show:
- Whether the webhook URL was called
- The HTTP status code returned
- The response body (truncated)
- The timestamp of delivery

**Why:** There is currently no way to know if a webhook was delivered during a test flow. A developer cannot distinguish "webhooks not delivered" from "my handler is down" without external logging. Even a simple "last delivery: 2 minutes ago — HTTP 200" in the Portal would save hours of debugging.

---

### FR-R5: Partner API rate limits in documentation
**Urgency: Medium**

Publish the rate limits for the Partner API:
- Webhook delivery: max events per second per account, per app
- Account API: max requests per minute per token
- Token exchange: max requests per hour

**Why:** We don't know if our MOTIF processing pipeline (which may take 200–500ms) could back up under load. We can't design appropriate rate-limit handling without knowing the limits.

---

### FR-R6: Webhook delivery retry policy in documentation
**Urgency: Low**

Document:
- How many times Ring retries a webhook on failure (non-200 response)
- The retry interval (immediate? exponential backoff?)
- Whether Ring drops events after N retries

**Why:** We implemented deduplication by `meta.request_id` because Ring may retry. But we don't know the retry behavior in detail, which makes it hard to reason about our event-loss risk in edge cases.

---

*Submitted as part of the Amazon Developer Hackathon 2026 Ring track.*
