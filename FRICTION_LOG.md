# VIGILANT — Friction Log

Issues encountered during the Ring track build. Each entry is a real problem we hit.

---

## 1. Ring Partner API — No official webhook simulator

**Task:** Test the full webhook → MOTIF → dashboard pipeline locally before deploying.

**Steps taken:** Searched Ring Developer Portal docs, release notes, and FAQ. Found the Playground (launched May 2026), which generates 30-minute OAuth tokens and tests device/account API calls.

**Expected:** An official way to trigger signed webhooks to a local URL (like Stripe's `stripe listen` CLI).

**Actual:** The Playground explicitly does not deliver webhooks. The Test-page staging-user flow is documented as supporting webhook delivery, but a community forum post reports that the Account Link URL, Token Exchange URL, and Webhook URL are never called during the Test flow. We could not confirm which is correct without live Portal access.

**Severity:** High — blocked end-to-end testing of the most important code path.

**Workaround:** Built our own HMAC-signed webhook simulator (`backend/ring_integration/webhook_simulator.py`) that constructs official v1.1 payloads and POSTs them to `/ring/webhook`. This exercises the full real code path: signature verification, normalization, deduplication, and MOTIF scoring.

**Suggestion for Ring:** Ship a `ring webhook send` CLI tool, similar to Stripe's or GitHub's webhook simulators, that sends a signed test event to any local URL. Even a simple curl snippet with the correct signing logic in the docs would save hours.

---

## 2. Ring webhook — Exact payload field names not fully documented

**Task:** Implement the webhook normalization function to extract device ID, event type, timestamp, and sub-type from the signed POST body.

**Steps taken:** Read Ring Partner API docs (developer.amazon.com/docs/ring/api-documentation.html). The motion detection example shows `attributes.source`, `attributes.timestamp` (milliseconds), and `attributes.sub_type`. The button_press type is mentioned.

**Expected:** A complete payload schema for every event type (motion, button_press, ding, app_integration_removed, etc.) with field names, types, and whether fields are required or optional.

**Actual:** The docs show one motion example. The `app_integration_removed` lifecycle event's payload structure is not shown — we had to infer it has no `source` or `timestamp` in attributes and handle it as a special case. The exact sub_type values (`human`, `vehicle`, `package_delivery`, `animal`) were confirmed only via third-party community projects, not official docs.

**Severity:** Medium — caused a test failure (normalization raised instead of returning None for `app_integration_removed`) and adds uncertainty about edge cases.

**Workaround:** Added explicit handling for known lifecycle event types before attempting to extract sensor data. Added tests against all known event shapes.

**Suggestion for Ring:** Publish a complete payload schema or JSON Schema for each event type in the Partner API docs.

---

## 3. Ring OAuth account linking — HMAC Signature Key is described as "one-time"

**Task:** Verify account-link nonces and webhook signatures using the HMAC Signature Key from the Developer Portal.

**Expected:** A stable key we could configure once and rely on for the lifetime of the deployment.

**Actual:** The Portal displays it as a "one-time" value in the setup UI, which is ambiguous. Does "one-time" mean it's shown once (like a secret), or that it rotates? If it rotates on each OAuth flow, our stored nonce verification would break silently. We proceeded assuming it means "shown once, stable" — the correct interpretation based on how webhook signing keys normally work — but the docs do not explicitly state this.

**Severity:** Medium — ambiguous wording creates risk that the key meaning is misunderstood.

**Suggestion for Ring:** Clarify in the docs that the HMAC Signature Key is a stable deployment secret (not ephemeral), and document its rotation policy if one exists.

---

## 4. Vercel serverless — BackgroundTasks killed after response

**Task:** Process Ring webhook events through MOTIF → Bedrock → database after returning HTTP 200 to Ring within 5 seconds.

**Expected:** FastAPI's `BackgroundTasks` would run after the response is sent.

**Actual:** Vercel serverless functions terminate the process as soon as the response is returned. BackgroundTasks are part of the same process and may not complete, causing silent event loss.

**Severity:** High — events would arrive and be acknowledged but never scored.

**Workaround:** Detected `VERCEL=1` environment variable (set automatically by Vercel) and switched to synchronous processing inside the webhook handler on Vercel. MOTIF scoring is fast enough (< 500ms) that Ring's 5-second deadline is still met. For production scale, a durable queue (SQS + Lambda) would be the correct solution.

**Suggestion for Vercel:** Document which background-task patterns are reliable in serverless functions; the failure is silent and difficult to debug.

---

## 5. AWS Bedrock — `anthropic.claude-3-sonnet-20240229-v1:0` model unavailable

**Task:** Generate human-readable pattern explanations using AWS Bedrock.

**Expected:** The model ID we had worked.

**Actual:** `anthropic.claude-3-sonnet-20240229-v1:0` is a legacy model. Newer Anthropic models on Bedrock use cross-region inference profiles with a `us.` prefix (e.g., `us.anthropic.claude-3-5-haiku-20241022-v1:0`). Passing the old base model ID returns HTTP 400. The Bedrock console model catalog and `list-foundation-models` CLI output are the authoritative source for available IDs, but the exact model ID format changed without a clear migration guide.

**Severity:** High — Bedrock integration would fail silently, producing "explanation unavailable" for all patterns.

**Workaround:** Updated model ID to `us.anthropic.claude-3-5-haiku-20241022-v1:0` (fast, low-cost, available in us-east-1). Made it configurable via `BEDROCK_MODEL_ID` env var. Migrated to the Converse API (cleaner interface, avoids raw JSON body construction).

**Suggestion for AWS:** Add a migration guide or a clear deprecation notice in the Bedrock console when a model ID format changes. The error message for an invalid model ID should suggest the correct format.

---

## 6. SQLite on Vercel — data vanishes on cold start

**Task:** Persist Ring events, learned baselines, and OAuth tokens across API requests in production.

**Expected:** Persistent storage between requests.

**Actual:** Vercel's `/tmp` filesystem is per-instance and ephemeral. A cold start (after ~15 minutes of inactivity) creates a fresh empty database. Demo patterns seeded via `/demo/seed` disappear between demo sessions. More critically, Ring OAuth tokens stored in SQLite are also lost, breaking the account link silently.

**Severity:** Critical for production use — demo and live data both disappear.

**Workaround:** SQLite works for local development and live demos (re-seed after cold start). Production requires a persistent Postgres instance. Added instructions in the README for connecting to Neon/Supabase free tier.

**Suggestion for Vercel:** Surface this limitation more clearly in the Python serverless function docs.

---

## 7. Ring Developer Portal account linking — single-account limitation

**Task:** Allow multiple users to link their Ring accounts to Vigilant.

**Expected:** A standard multi-user OAuth flow.

**Actual:** The account linking flow validates a nonce against a single configured `VIGILANT_ACCOUNT_EMAIL`. Scaling to multiple Vigilant users requires a full identity provider (auth0, Cognito, etc.) integrated with the nonce validation step. This is a one-tenant system by design at this stage.

**Severity:** Low for hackathon scope, High for production readiness.

**Workaround:** Documented the limitation explicitly in the README. Left a placeholder in the code for a future identity provider.

---

*Last updated: October 2026. Entries will be updated as the build progresses.*
