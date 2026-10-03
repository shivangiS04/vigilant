import unittest
from datetime import datetime

from backend.bedrock_integration.explanation_generator import ExplanationGenerator


class ExplanationTests(unittest.TestCase):
    def test_prompt_handles_ring_events_without_confidence(self):
        generator = ExplanationGenerator.__new__(ExplanationGenerator)
        prompt = generator._build_prompt(
            {
                "pattern_type": "doorbell_sequence",
                "salience_score": 7,
                "confidence": None,
                "events": [
                    {
                        "timestamp": datetime(2026, 10, 2).isoformat(),
                        "camera": "Front Door",
                        "type": "doorbell",
                        "confidence": None,
                    }
                ],
            }
        )

        self.assertIn("Detection Confidence: Not provided", prompt)
        self.assertIn("Front Door - doorbell", prompt)
        self.assertNotIn("nan%", prompt)

    def test_cache_key_groups_same_type_and_salience_bucket(self):
        generator = ExplanationGenerator.__new__(ExplanationGenerator)
        left = generator._cache_key({"pattern_type": "motion", "salience_score": 7.1})
        right = generator._cache_key({"pattern_type": "motion", "salience_score": 7.4})
        self.assertEqual(left, right)


if __name__ == "__main__":
    unittest.main()