"""
AlexaClient — invokes the vigilant-alexa-announcer Lambda
when VIGILANT detects a flagged pattern.

Requires:
  ALEXA_ENABLED=true
  ALEXA_LAMBDA_FUNCTION=vigilant-alexa-announcer  (default)
  AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION

Silently fails if Alexa is unavailable so it never breaks core detection.
"""

import json
import os
from typing import Dict


class AlexaClient:
    MIN_SALIENCE = 6.0

    def __init__(self):
        self.enabled = os.getenv("ALEXA_ENABLED", "false").lower() == "true"
        self.lambda_name = os.getenv("ALEXA_LAMBDA_FUNCTION", "vigilant-alexa-announcer")
        self._client = None

    def _get_lambda_client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client(
                "lambda",
                region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            )
        return self._client

    def send_alert(self, home_id: str, pattern: Dict) -> bool:
        """Fire-and-forget alert to Alexa Lambda. Returns True if invoked."""
        if not self.enabled:
            return False

        salience = float(pattern.get("salience_score", pattern.get("salience", 0)))
        if salience < self.MIN_SALIENCE:
            return False

        payload = {
            "home_id": home_id,
            "pattern": {
                "pattern_type": pattern.get("pattern_type"),
                "explanation": pattern.get("explanation", "Pattern detected."),
                "salience": salience,
            },
        }

        try:
            self._get_lambda_client().invoke(
                FunctionName=self.lambda_name,
                InvocationType="Event",  # async — don't block
                Payload=json.dumps(payload).encode(),
            )
            print(f"[Alexa] Sent alert → {self.lambda_name} (salience={salience:.1f})")
            return True
        except Exception as e:
            print(f"[Alexa] Silent fail: {e}")
            return False
