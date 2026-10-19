# VIGILANT — Product Feedback for Ring and AWS
**Submitted by:** Shivangi Singh, Archisha Srivastava
**Hackathon:** Amazon Developer Hackathon 2026 — Ring Track
**Date:** October 2026

This is honest feedback from building VIGILANT. All friction items are real issues we hit during development.

---

## Ring Partner API

### What worked well

**Webhook delivery model is exactly right.** POSTing signed payloads to a developer URL is clean and gives us full control over processing. The HMAC-SHA256 signing is the correct security model and it was easy to implement.

**The v1.1 payload structure is well-designed.** The `meta` / `data` / `attributes` separation is clear. `request_id` for deduplication is thoughtful. `timestamp_ms` as epoch milliseconds is unambiguous.

**OAuth 2.0 account linking flow is standard.** The authorization code flow works exactly like other OAuth 2.0 providers. Any developer familiar with OAuth can implement it without surprises.

---

### What was painful

**1. No webhook simulator. Severity: High.**

There is no official way to send a signed test webhook to a local URL. The Playground generates 30-minute OAuth tokens and tests device/account APIs — it explicitly does not deliver webhooks. The Test-page staging-user flow claims to support webhooks but community reports suggest it may not work reliably.

Stripe ships `stripe listen`. GitHub ships `gh webhook forward`. Both work in 30 seconds and are among the most loved features of their developer platforms. Ring needs an equivalent.

[OUR EXPERIENCE]: We spent two days building our own HMAC-signed simulator (`backend/ring_integration/webhook_simulator.py`) because we needed to test the full code path: signature verification, normalization, MOTIF scoring, Bedrock explanation. The simulator works and is now a core part of our local dev workflow. But two days of building infrastructure is two days not spent on product features.

**2. Payload schema is incomplete in documentation. Severity: Medium.**

The docs show a motion detection example. The `app_integration_removed` lifecycle event structure is not documented. We had to infer that it has empty `attributes` and handle it as a special case. We confirmed `sub_type` values (`human`, `vehicle`, `package_delivery`, `animal`) via third-party community projects, not official docs.

[OUR EXPERIENCE]: We had a failing test (`test_app_integration_removed_returns_none`) that took an hour to trace back to undocumented payload structure.

**3. "HMAC Signature Key is one-time" is ambiguous wording. Severity: Medium.**

The Portal displays it as a "one-time" value. Does this mean it is shown only once (like a secret), or that it rotates per OAuth flow? We assumed "shown once, stable," which is consistent with how webhook signing keys normally work, but we were not certain. If our assumption is wrong, nonce verification would break silently.

**4. Test-page staging users vs. Playground distinction is not surfaced in onboarding. Severity: Low.**

We spent time understanding when to use the Playground vs. the Test page. The distinction (Playground = device/account API testing, Test page = webhook delivery testing) should be front-and-center in the getting-started guide.

---

### Requests

See `feature_requests.md` for the prioritized request list.

---

## AWS Bedrock

### What worked well

**The Converse API is excellent.** Consistent interface across models, clean JSON request/response, no raw body construction. Much better than the legacy `invoke_model` API.

**Claude 3.5 Haiku is the right default for this use case.** Fast (< 1 second), accurate, and the cost per explanation is negligible. The inference profile format (`us.anthropic.claude-3-5-haiku-20241022-v1:0`) was unfamiliar at first but makes sense.

**IAM least-privilege is easy to express.** A single `bedrock:InvokeModel` action on the specific model ARN is clean.

---

### What was painful

**1. Model ID format changed without a clear migration guide. Severity: High.**

Older model IDs (`anthropic.claude-3-sonnet-20240229-v1:0`) return HTTP 400 without a clear error message. The new cross-region inference profile format (`us.anthropic.claude-3-5-haiku-20241022-v1:0`) is not discoverable unless you know to look for it. The `list-foundation-models` CLI output lists both formats and it is not obvious which one to use for `invoke_model` vs. `converse`.

[OUR EXPERIENCE]: We started with a legacy model ID, got silent failures that surfaced as "explanation unavailable" in the UI, spent 45 minutes tracing it back to the model ID, and then had to find the correct format through trial and error. The fix was one line; the debug time was not.

**2. `AccessDeniedException` and `ValidationException` error messages don't distinguish credential issues from model-not-enabled issues. Severity: Medium.**

Both errors surface as the same exception class with different message strings. When Bedrock is not enabled in a region, the message is close to a credential error message. Developers new to Bedrock cannot tell whether they need to enable the model in the console, request model access, or check their IAM policy.

[OUR EXPERIENCE]: We added specific error handling in `explanation_generator.py` to distinguish the two, but we had to learn the message string differences through documentation mining.

**3. No clear documentation of Converse API response structure for streaming vs. non-streaming. Severity: Low.**

The Converse API docs show the non-streaming response clearly. We found `response["output"]["message"]["content"][0]["text"]` through the SDK source code and community examples, not through the official documentation.

---

### Requests

See `feature_requests.md` for the prioritized request list.

---

*Submitted as part of the Amazon Developer Hackathon 2026 Ring track.*
