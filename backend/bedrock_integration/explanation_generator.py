import boto3
import json
import hashlib
from typing import Dict, List, Optional
from datetime import datetime, timedelta


class ExplanationGenerator:
    """
    Calls AWS Bedrock (Claude 3 Sonnet) to turn MOTIF scores into
    human-readable explanations. Caches by pattern type to reduce
    latency (same pattern type → same explanation returned instantly).
    """

    MODEL_ID = "anthropic.claude-3-sonnet-20240229-v1:0"
    MAX_TOKENS = 150
    TEMPERATURE = 0.3

    def __init__(self, region: str = "us-east-1", cache_ttl_hours: int = 6):
        self.client = boto3.client("bedrock-runtime", region_name=region)
        self._cache: Dict[str, tuple] = {}  # key → (explanation, expires_at)
        self._cache_ttl = timedelta(hours=cache_ttl_hours)

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
        self._set_cache(cache_key, explanation)
        return explanation

    def generate_daily_summary(self, patterns: List[Dict], date: str, location: str) -> str:
        """Summarise multiple patterns for one day (avoids alert fatigue)."""
        prompt = self._build_batch_prompt(patterns, date, location)
        return self._call_bedrock(prompt)

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _build_prompt(self, p: Dict) -> str:
        events_text = "\n".join(
            f"  {i+1}. {e['timestamp']}: {e['camera']} - {e['type']} ({e['confidence']*100:.0f}%)"
            for i, e in enumerate(p.get("events", []))
        )

        salience = p.get("salience_score", 5)
        if salience > 7:
            tone = "Alert but not alarmist — use phrases like 'worth checking into'"
        elif salience >= 4:
            tone = "Informative — use phrases like 'this is different from usual'"
        else:
            tone = "Low-key FYI — use phrases like 'just flagged as slightly unusual'"

        return f"""CONTEXT:
You are explaining a behavioral pattern detected at a residential smart home to the homeowner.
The system (VIGILANT) learns what is "normal" for this specific home and detects meaningful deviations.

HOME BASELINE:
- Location: {p.get('location', 'Residential property')}
- Typical daily patterns: {p.get('baseline_patterns', 'Not yet fully established')}
- Normal activity hours: {p.get('normal_hours', '7 AM - 11 PM')}
- Known residents: {p.get('resident_count', 'Unknown')}

DETECTED PATTERN:
- Pattern Type: {p.get('pattern_type', 'unknown')}
- Detection Confidence: {p.get('confidence', 0) * 100:.0f}%
- Novelty Score: {p.get('novelty_score', 5):.1f}/10 (how unusual is this?)
- Salience Score: {salience:.1f}/10 (how important is this?)

EVENT SEQUENCE:
{events_text}

PATTERN HISTORY:
- How often seen before: {p.get('frequency', 'First time')}
- Last similar pattern: {p.get('last_occurrence', 'Never')}

YOUR TASK:
1. Explain WHY this pattern is unusual (reference the baseline)
2. Be concise — 1-2 sentences max
3. Focus on the sequence, not individual events
4. Include ONE actionable insight if salience > 6
5. Use natural, conversational language

TONE: {tone}

Provide the explanation now:"""

    def _build_batch_prompt(self, patterns: List[Dict], date: str, location: str) -> str:
        pattern_blocks = ""
        for i, p in enumerate(patterns[:5], 1):  # cap at 5
            pattern_blocks += f"""
Pattern #{i}: {p.get('pattern_type', 'unknown')}
- Time: {p.get('time', 'unknown')}
- Salience: {p.get('salience_score', 0):.1f}/10
- Summary: {p.get('summary', '')}
"""

        return f"""CONTEXT:
You're summarising multiple behavioral patterns detected in one day at a home.
Avoid alert fatigue — only call out the most significant patterns.

HOME: {location}
DATE: {date}

PATTERNS DETECTED:
{pattern_blocks}

YOUR TASK:
1. Rank patterns by importance (ignore salience < 4)
2. Provide 1 sentence per significant pattern
3. Group related patterns if any
4. Suggest if homeowner should investigate
5. Total explanation: max 4 sentences

Now provide the summary:"""

    # ------------------------------------------------------------------
    # Bedrock call
    # ------------------------------------------------------------------

    def _call_bedrock(self, prompt: str) -> str:
        try:
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": self.MAX_TOKENS,
                "temperature": self.TEMPERATURE,
            })
            response = self.client.invoke_model(modelId=self.MODEL_ID, body=body)
            result = json.loads(response["body"].read())
            return result["content"][0]["text"].strip()
        except Exception as e:
            # graceful degradation — never crash the dashboard
            return f"Pattern detected (explanation unavailable: {type(e).__name__})"

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_key(self, pattern_data: Dict) -> str:
        key_parts = f"{pattern_data.get('pattern_type')}:{round(pattern_data.get('salience_score', 0))}"
        return hashlib.md5(key_parts.encode()).hexdigest()

    def _get_cached(self, key: str) -> Optional[str]:
        if key in self._cache:
            explanation, expires_at = self._cache[key]
            if datetime.utcnow() < expires_at:
                return explanation
            del self._cache[key]
        return None

    def _set_cache(self, key: str, explanation: str):
        self._cache[key] = (explanation, datetime.utcnow() + self._cache_ttl)


# ------------------------------------------------------------------
# Smoke test (no Bedrock creds needed — shows prompt output)
# ------------------------------------------------------------------
if __name__ == "__main__":
    gen = ExplanationGenerator()

    test_pattern = {
        "pattern_type": "rapid_return",
        "confidence": 0.95,
        "novelty_score": 8.5,
        "salience_score": 7.2,
        "location": "123 Main Street",
        "baseline_patterns": "Person typically out 4+ hours, returns between 5-7 PM",
        "normal_hours": "7 AM - 11 PM",
        "resident_count": 2,
        "events": [
            {"timestamp": "2:30 PM", "camera": "front_door", "type": "person_detected", "confidence": 0.95},
            {"timestamp": "2:31 PM", "camera": "front_door", "type": "motion_detected", "confidence": 0.92},
            {"timestamp": "2:35 PM", "camera": "side_door", "type": "person_detected", "confidence": 0.89},
        ],
        "frequency": "First time this week",
        "last_occurrence": "Similar pattern 2 weeks ago",
    }

    prompt = gen._build_prompt(test_pattern)
    print("=== BUILT PROMPT ===")
    print(prompt)
    print("\n(Skipping actual Bedrock call — add AWS creds to test live)")
