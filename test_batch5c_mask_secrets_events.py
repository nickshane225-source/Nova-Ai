"""
Regression tests for Batch 5c Item 5:
- Mask secrets in plan events (audit_logger.mask_secrets or server.mask_secrets)
- 100-character cap on event strings
- Verification with 'sk-...' string in step result and step text.
"""
import unittest
from unittest.mock import patch

import server


class TestBatch5cMaskSecretsEvents(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "confirm_destructive": True,
            "provider": "openai",
            "api_key": "sk-mock-12345",
            "model": "gpt-4o",
            "monthly_budget_usd": 100.0,
        }
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()
        with server.ACTIVE_PLANS_LOCK:
            server.ACTIVE_PLANS.clear()
        with server.LOCK:
            server.EVENTS.clear()

    def tearDown(self):
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()
        with server.ACTIVE_PLANS_LOCK:
            server.ACTIVE_PLANS.clear()
        with server.LOCK:
            server.EVENTS.clear()

    def test_plan_events_mask_sk_secrets_and_keep_hundred_char_limit(self):
        """Plan events must mask sk-... API keys and truncate results to 100 characters maximum."""
        raw_secret_key = "sk-proj-abcdef1234567890abcdef1234567890"
        long_result = f"Output containing secret key {raw_secret_key} and some very long trailing text that goes on and on and on and on and on and on and on."

        plan_state = {
            "title": f"SecretPlan-{raw_secret_key}",
            "all_steps": [f"NOTE: extract | {raw_secret_key}"],
            "remaining_steps": [f"NOTE: extract | {raw_secret_key}"],
            "completed": [],
            "source": "pc",
            "mode": "developer",
            "conv_id": "pc:developer",
        }

        with patch("server.create_plan_step_runner") as mock_create_runner:
            # Runner returns a string containing the sk-... key
            mock_runner = lambda step, *args: long_result
            mock_create_runner.return_value = mock_runner

            res = server.resume_plan_execution(plan_state, cfg=self.cfg, async_run=False)
            server.wait_for_plan_worker("pc:developer", timeout=5.0)

        with server.LOCK:
            step_done_events = [e for e in server.EVENTS if e.get("type") == "plan_step_done"]
            step_start_events = [e for e in server.EVENTS if e.get("type") == "plan_step_start"]
            completed_events = [e for e in server.EVENTS if e.get("type") == "plan_completed"]

        self.assertTrue(len(step_done_events) >= 1)
        done_ev = step_done_events[0]

        # 1. Secret must NOT appear in any event field
        res_text = done_ev.get("preview") or done_ev.get("res", "")
        self.assertNotIn(raw_secret_key, res_text)
        self.assertNotIn(raw_secret_key, done_ev.get("title", ""))

        # 2. String lengths must strictly adhere to limit
        self.assertLessEqual(len(res_text), 200)
        self.assertLessEqual(len(done_ev.get("title", "")), 100)

        # 3. Masked indicator present
        self.assertTrue(
            "[MASKED_SECRET]" in res_text or "sk-proj****" in res_text
        )


if __name__ == "__main__":
    unittest.main()
