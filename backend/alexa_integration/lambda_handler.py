"""
AWS Lambda handler for VIGILANT → Alexa announcements.

Deploy this to a Lambda function named `vigilant-alexa-announcer`.
VIGILANT backend invokes it asynchronously when a pattern is flagged.

Test event:
{
  "pattern": {
    "pattern_type": "rapid_return",
    "explanation": "Someone returned home unusually quickly and entered via side door",
    "salience": 7.8
  },
  "home_id": "home_001"
}
"""

import json
from datetime import datetime, timezone


def lambda_handler(event, context):
    print(f"[Alexa] Received event: {json.dumps(event)}")

    try:
        pattern = event.get("pattern", {})
        home_id = event.get("home_id", "unknown")
        salience = float(pattern.get("salience", 0))
        explanation = pattern.get("explanation", "Security pattern detected.")
        pattern_type = pattern.get("pattern_type", "unknown")

        if salience > 8:
            urgency = "URGENT alert"
        elif salience > 6:
            urgency = "Security alert"
        else:
            urgency = "Home notification"

        voice_message = f"{urgency}: {explanation}"
        print(f"[Alexa] Voice message: {voice_message}")

        # --- Production hook: call Alexa Proactive Events API here ---
        # This requires an Alexa skill with the Proactive Events permission.
        # See: https://developer.amazon.com/en-US/docs/alexa/smapi/proactive-events-api.html
        # For hackathon purposes, the Lambda logs the message and returns success.

        return {
            "statusCode": 200,
            "body": json.dumps({
                "voice_message": voice_message,
                "home_id": home_id,
                "pattern_type": pattern_type,
                "salience": salience,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }),
        }

    except Exception as e:
        print(f"[Alexa] Error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }
