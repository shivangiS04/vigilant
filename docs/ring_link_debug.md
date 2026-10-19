# Ring Account-Linking Debug Report
**Branch:** ring-live-integration
**Date:** 2026-10-20
**Status:** 0 linked accounts despite Ring Portal showing account as authorized

---

## Summary: Most Likely Root Cause

**Ring's servers and the user's browser never reached our Account Link URL or Token Exchange URL.**

Evidence: Searching 100 recent Vercel function invocation logs shows zero requests to `/ring/link`, `/ring/token`, or any Ring callback path. The health endpoint shows the database is Postgres and the linking vars are all set, but `linked_accounts: 0`. If any step of the two-part link flow had been attempted, at least one request log would exist.

The two most likely reasons:

1. **Wrong URLs in Ring Developer Portal** — The Account Link URL and/or Token Exchange URL may be pointing to an old preview deployment URL (e.g., `vigilant-backend-dhm410tk9-...vercel.app`) instead of the stable alias `vigilant-backend-omega.vercel.app`. Or the paths are slightly off (trailing slash, wrong prefix). Any mismatch means Ring redirects/POSTs to a URL that isn't ours.

2. **Linking was done when SQLite was active** — The account was linked against the old `/tmp/vigilant.db` (SQLite on Vercel). That database is ephemeral and reset. Neon Postgres was connected after the Ring authorization happened, so the tokens were written to the old DB and are now gone.

---

## Findings Per Investigation Area

### 1. Integration Mode (simulator vs official)

**Finding:** `RING_INTEGRATION_MODE=simulator` is currently deployed in production. However, simulator mode does NOT disable or short-circuit the OAuth callback, `/ring/link`, `/ring/token`, or any linking route. All linking routes are fully live in simulator mode. Mode affects only: whether the webhook simulator co-process starts (not applicable on Vercel serverless), whether `/ring/simulator/seed-account` is accessible (POST — no auth), and whether `/demo/seed` requires a token (skips the token check in simulator mode).

**Impact:** Medium. Running in simulator mode is wrong for production but is not why 0 linked accounts exist. The webhook simulator does NOT run on Vercel (it's an async subprocess that dies with the serverless function). The real impact is that the Ring Docs team will see `mode: simulator` and question whether real Ring data is being processed.

**Required action (user):** Set `RING_INTEGRATION_MODE=official` in Vercel → Production and redeploy.

---

### 2. Env Vars — All Four Linking Vars Are Now Set

**Finding (from `vercel env ls`):**
- `RING_TOKEN_ENCRYPTION_KEY` — set 1h ago ✅
- `RING_SESSION_SECRET` — set 1h ago ✅
- `VIGILANT_ACCOUNT_EMAIL` — set 1h ago ✅
- `VIGILANT_ACCOUNT_PASSWORD_HASH` — set 43 min ago ✅

Health endpoint confirms: `ring_account_linking: {enabled: true}`.

Missing from Vercel (not in env ls output):
- `HOME_ID` — no row in Vercel. The code uses `os.getenv("HOME_ID", "home_001")` fallback. Present but defaulting.
- `DEMO_SEED_TOKEN` — not set. In official mode, `/demo/seed` requires this token. If not set, the endpoint returns 404 in official mode (even with a token), because `not expected` is truthy when the env var is empty.
- `HOME_TIMEZONE` — not set. May affect pattern detection around midnight.
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` — not set. Bedrock is disabled.

**RING_CLIENT_SECRET and RING_HMAC_SIGNING_KEY were set 11 days ago.** If Ring rotated these values in the Portal since then, the token exchange and nonce verification will silently fail. No code path logs the original Ring response body on exchange failure.

---

### 3. Did Ring Ever Call Us?

**Finding:** Zero Vercel log entries for `/ring/link`, `/ring/token`, or any Ring callback path across the last 100 invocations. This is the strongest evidence for the root cause above.

**What would have appeared if the flow worked:**
- At least one `λ GET /ring/link` or `λ POST /ring/token` log entry
- For a successful link: `λ POST /ring/link/claim` as well

**Conclusion:** Ring never reached our app for the link flow. Either the Portal URLs are wrong, or the link was completed against the old SQLite database.

---

### 4. The Linking Flow — Code vs Ring Docs

Ring's Partner API account-linking (private app flow) has two independent parts:

**Part A — OAuth authorization code (Token Exchange URL):**
- Ring's server POSTs to our Token Exchange URL with `client_id` and `code` (authorization code)
- Our `/ring/token` accepts form or JSON body, checks `client_id == RING_CLIENT_ID`, calls `exchange_authorization_code(code)` → stores encrypted tokens
- **Field name accepted:** `code` OR `authorization_code` (routes.py:361) — two aliases handled ✅
- **Content-Type:** form-urlencoded or JSON ✅
- No known mismatch; the acceptance of both field names is defensive

**Part B — Nonce/account-link (Account Link URL):**
- Ring redirects user's browser to Account Link URL with query params `time` (ms timestamp) and `nonce` (HMAC-SHA256 base64url)
- Our `/ring/link` stores them in a cookie-backed session, shows VIGILANT sign-in form
- User signs in: `/ring/login` (POST, form or JSON, fields: `email`, `password`, `csrf_token`)
- User confirms: `/ring/link/claim` (POST, form or JSON, field: `csrf_token`)
- `/ring/link/claim` calls `claim_ring_account()` → validates nonce against `RING_HMAC_SIGNING_KEY` → marks account linked

**Potential mismatch:** Ring's docs say the Account Link URL receives `time` and `nonce`. Our code expects them as query parameters on a GET. If Ring sends them differently (e.g., POST body), the params would be None and `_partner_signin_ready()` would 503 before they're stored.

**Nonce window:** 600 seconds (10 minutes). If the user authorizes in Ring but doesn't complete the VIGILANT sign-in + confirm within 10 minutes, the nonce expires and `claim_ring_account()` will find no matching unclaimed account.

---

### 5. Database State

**Finding:** Neon Postgres has a `ring_accounts` table (created by `init_db()`). It currently has 0 rows. The `/demo/seed` seed ran successfully, so the DB is writable. The health endpoint queries `RingAccount` rows with `status == "completed"` and returns 0.

Any previous links were written to the ephemeral SQLite `/tmp/vigilant.db` on Vercel and are now gone.

---

### 6. Silent Failures in the Linking Path

**Critical gaps (no logging at all):**

- `routes.py:528-530` — `ring_status()` has a bare `except Exception: pass` that covers the entire DB query for linked accounts, last webhook, and devices. Any DB error silently returns zeros.
- `webhook_simulator.py:182-183` — `_ensure_simulator_account()` has `except Exception: pass` with no log.
- `routes.py:430-433` — webhook event processing logs only the exception *class*, not the message or traceback.

**Token exchange — no response body logging:**  
`official_client.py` (the `exchange_authorization_code` method) — the Ring token endpoint response is only checked for status code. If Ring returns a 4xx with an error body (e.g., expired code, wrong client_secret), the error body is not logged. The only visible symptom would be an unhandled exception propagating up, caught by a generic FastAPI 500 handler, with no detail in Vercel logs.

---

### 7. VIGILANT Sign-In Step

**Finding:** `VIGILANT_ACCOUNT_PASSWORD_HASH` is now set (43 min ago). `_partner_signin_ready()` returns True. The VIGILANT sign-in form at `/ring/link` will render correctly.

However: the sign-in flow is a **browser-driven 3-step flow** requiring a human to:
1. Follow the Ring redirect to `https://vigilant-backend-omega.vercel.app/ring/link?time=X&nonce=Y`
2. Sign in to VIGILANT with email + password in that browser tab
3. Click "Connect Ring Account" → POST `/ring/link/claim`

This flow was never completed — confirmed by the zero log entries.

---

### 8. frontend/.env.production

**Finding:** The file exists at `frontend/.env.production` and contains only `VITE_API_URL=https://vigilant-backend-omega.vercel.app`. No secrets. However, the file is **not gitignored** — `*.env.production` is not in `.gitignore`. It is tracked in git.

Since `VITE_API_URL` is a public URL (compiled into the JS bundle anyway), having it in git is not a secret leak. However, the file should be gitignored by convention to prevent accidentally committing real frontend secrets in future.

---

## Step 3: User Action Checklist

These require direct Portal/console access and cannot be done by code changes:

### A. Vercel — Environment Variables

In the Vercel dashboard → `vigilant-backend` project → Settings → Environment Variables:

| Variable | Value | Action |
|---|---|---|
| `RING_INTEGRATION_MODE` | `official` | **Change from `simulator`** |
| `RING_CLIENT_ID` | *(from Ring Portal)* | Verify matches Portal |
| `RING_CLIENT_SECRET` | *(from Ring Portal)* | Verify matches Portal — was set 11d ago, may be stale |
| `RING_HMAC_SIGNING_KEY` | *(from Ring Portal)* | Verify matches Portal — was set 11d ago, may be stale |
| `DEMO_SEED_TOKEN` | any random string | Add — needed for `/demo/seed` in official mode |
| `HOME_ID` | `home_001` | Add explicitly |
| `AWS_ACCESS_KEY_ID` | *(from AWS IAM)* | Add for Bedrock |
| `AWS_SECRET_ACCESS_KEY` | *(from AWS IAM)* | Add for Bedrock |
| `AWS_DEFAULT_REGION` | `us-east-1` | Add for Bedrock |

After ALL changes → click **Redeploy** (or push any commit).

### B. Ring Developer Portal — Verify URLs

Log in to the Ring Developer Portal and confirm these URLs for the app **exactly** match (no trailing slashes, no old preview domain):

| Field | Required value |
|---|---|
| Account Link URL | `https://vigilant-backend-omega.vercel.app/ring/link` |
| Token Exchange URL | `https://vigilant-backend-omega.vercel.app/ring/token` |
| Webhook URL | `https://vigilant-backend-omega.vercel.app/ring/webhook` |
| App Homepage URL | `https://vigilant-backend-omega.vercel.app/ring` |

If any of these point to `localhost`, a preview URL (`...dhm410tk9...`), or have the wrong path, Ring's callbacks will fail silently.

### C. Re-link (full flow)

1. In the Ring app or Portal, **disconnect/remove** the existing VIGILANT authorization (it stored tokens to the old SQLite DB which is now gone)
2. Re-authorize: open the Ring app → Link Partner App → VIGILANT
3. Ring will redirect your browser to `https://vigilant-backend-omega.vercel.app/ring/link?time=X&nonce=Y`
4. On that page: sign in with `archishaava@gmail.com` and the VIGILANT password (the one hashed in `VIGILANT_ACCOUNT_PASSWORD_HASH`)
5. Click "Connect Ring Account"
6. Within 30 seconds: check `/health` for `linked_accounts: 1`

**Time window:** The nonce is valid for 10 minutes after Ring generates it. Complete steps 3–5 within that window.

### D. Verify

After re-linking:
- `GET /health` → `ring_account_linking.linked_accounts: 1`, `ring_integration_mode: official`, `bedrock_explanations.enabled: true`
- `GET /ring/status` → shows linked account + devices
- Walk past a Ring device → a webhook arrives at `/ring/webhook` with a real `request_id` and signature; a pattern appears on the dashboard within 30s
