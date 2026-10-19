import boto3
import json
import hashlib
import os
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta


# Default: claude-3-5-haiku — fast, cheap, available in us-east-1.
# Override with BEDROCK_MODEL_ID env var (verify your model is enabled in the
# Bedrock console before changing; run:
#   aws bedrock list-foundation-models --region us-east-1 --by-provider anthropic
# Cross-region inference profiles use the "us." prefix; regional IDs do not.
_DEFAULT_MODEL_ID = "us.anthropic.claude-3-5-haiku-20241022-v1:0"


class ExplanationGenerator:
    """
    Calls AWS Bedrock (Converse API) to turn MOTIF scores into human-readable
    explanations. Falls back gracefully when Bedrock is unconfigured or
    unavailable — the UI shows "Explanation unavailable" rather than an error.
    Caches by (pattern_type, salience_bucket) for 6 hours to reduce latency.
    """

    @property
    def MODEL_ID(self) -> str:
        return os.getenv("BEDROCK_MODEL_ID", _DEFAULT_MODEL_ID)

    MAX_TOKENS = 150
    TEMPERATURE = 0.3

    def __init__(self, region: str = "us-east-1", cache_ttl_hours: int = 6):
        self._region = region
        self._client: Optional[object] = None
        self._cache: Dict[str, tuple] = {}
        self._cache_ttl = timedelta(hours=cache_ttl_hours)

    def _bedrock(self):
        if self._client is None:
            self._client = boto3.client(
                "bedrock-runtime",
                region_name=os.getenv("AWS_DEFAULT_REGION", self._region),
            )
        return self._client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_explanation(self, pattern_data: Dict) -> str:
        cache_key = self._cache_key(pattern_data)
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        prompt = self._build_prompt(pattern_data)
        explanation = self._call_bedrock(prompt)
        if not explanation.startswith("Explanation unavailable"):
            self._set_cache(cache_key, explanation)
        return explanation

    def generate_daily_summary(self, patterns: List[Dict], date: str, location: str) -> str:
        prompt = self._build_batch_prompt(patterns, date, location)
        return self._call_bedrock(prompt)

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _build_prompt(self, p: Dict) -> str:
        event_lines = []
        for i, event in enumerate(p.get("events", [])):
            confidence = event.get("confidence")
            confidence_text = f" ({confidence * 100:.0f}%)" if confidence is not None else ""
            event_lines.append(
                f"  {i + 1}. {event.get('timestamp', '')}: {event.get('camera', '')} - "
                f"{event.get('type', '')}{confidence_text}"
            )
        events_text = "\n".join(event_lines) or "  (no events)"

        salience = p.get("salience_score", 5)
        if salience > 7:
            tone = "Alert but not alarmist — use phrases like 'worth checking into'"
        elif salience >= 4:
            tone = "Informative — use phrases like 'this is different from usual'"
        else:
            tone = "Low-key FYI — use phrases like 'just flagged as slightly unusual'"

        confidence = p.get("confidence")
        confidence_text = f"{confidence * 100:.0f}%" if confidence is not None else "Not provided"

        return f"""You are explaining a behavioral pattern detected at a residential smart home to the homeowner. The system learns what is "normal" and surfaces meaningful deviations.

Pattern type: {p.get('pattern_type', 'unknown')}
Detection confidence: {confidence_text}
Novelty score: {p.get('novelty_score', 5):.1f}/10
Salience score: {salience:.1f}/10

Event sequence:
{events_text}

Instructions: Explain in 1–2 sentences why this pattern is unusual (reference the baseline). If salience > 6, include one actionable insight. Use natural, conversational language. Tone: {tone}"""

    def _build_batch_prompt(self, patterns: List[Dict], date: str, location: str) -> str:
        pattern_blocks = ""
        for i, p in enumerate(patterns[:5], 1):
            pattern_blocks += (
                f"\nPattern #{i}: {p.get('pattern_type', 'unknown')}\n"
                f"- Time: {p.get('time', 'unknown')}\n"
                f"- Salience: {p.get('salience_score', 0):.1f}/10\n"
                f"- Summary: {p.get('summary', '')}\n"
            )
        return (
            f"Summarise multiple behavioral patterns detected in one day at a home. "
            f"Avoid alert fatigue — only call out the most significant ones.\n\n"
            f"Home: {location}\nDate: {date}\n\nPatterns:\n{pattern_blocks}\n\n"
            f"Instructions: Rank by importance (ignore salience < 4). "
            f"1 sentence per significant pattern. Max 4 sentences total."
        )

    # ------------------------------------------------------------------
    # Bedrock Converse call
    # ------------------------------------------------------------------

    def _call_bedrock(self, prompt: str) -> str:
        try:
            response = self._bedrock().converse(
                modelId=self.MODEL_ID,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={
                    "maxTokens": self.MAX_TOKENS,
                    "temperature": self.TEMPERATURE,
                },
            )
            return response["output"]["message"]["content"][0]["text"].strip()
        except self._bedrock().exceptions.AccessDeniedException:
            return "Explanation unavailable — Bedrock model access not enabled for this account."
        except self._bedrock().exceptions.ValidationException as exc:
            return f"Explanation unavailable — model ID may be invalid: {exc}"
        except Exception:
            return "Explanation unavailable."

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_key(self, pattern_data: Dict) -> str:
        key = f"{pattern_data.get('pattern_type')}:{round(pattern_data.get('salience_score', 0))}"
        return hashlib.md5(key.encode()).hexdigest()

    def _get_cached(self, key: str) -> Optional[str]:
        if key in self._cache:
            explanation, expires_at = self._cache[key]
            if datetime.now(timezone.utc) < expires_at:
                return explanation
            del self._cache[key]
        return None

    def _set_cache(self, key: str, explanation: str) -> None:
        self._cache[key] = (explanation, datetime.now(timezone.utc) + self._cache_ttl)


# ------------------------------------------------------------------
# Smoke test (no Bedrock creds needed — shows prompt only)
# ------------------------------------------------------------------
if __name__ == "__main__":
    gen = ExplanationGenerator()
    test_pattern = {
        "pattern_type": "rapid_return",
        "confidence": 0.95,
        "novelty_score": 8.5,
        "salience_score": 7.2,
        "events": [
            {"timestamp": "14:30", "camera": "front_door", "type": "person_detected", "confidence": 0.95},
            {"timestamp": "14:31", "camera": "front_door", "type": "motion_detected", "confidence": 0.92},
            {"timestamp": "14:35", "camera": "side_door", "type": "person_detected", "confidence": 0.89},
        ],
    }
    print("=== BUILT PROMPT ===")
    print(gen._build_prompt(test_pattern))
    print(f"\nModel ID: {gen.MODEL_ID}")
    print("(Add AWS credentials to .env to test a live Bedrock call)")
