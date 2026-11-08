"""
Regression tests for Batch 5c Item 3:
- One active plan per conversation enforced via ACTIVE_PLANS map
- Rejection of concurrent second plan on the same conversation
- Rejection of chat messages while the plan worker thread is actively running
- Independent plan execution across different conversation IDs
- Active plan cleared on completion or denial.
"""
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import server


class TestBatch5cActivePlans(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "confirm_destructive": True,
            "provider": "openai",
            "api_key": "sk-mock-12345",
            "model": "gpt-4o",
            "monthly_budget_usd": 100.0,
        }
        with server.ACTIVE_PLANS_LOCK:
            server.ACTIVE_PLANS.clear()
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()
        with server.LOCK:
            server.HISTORIES["developer"].clear()
            server.HISTORIES["cyber"].clear()

    def tearDown(self):
        with server.ACTIVE_PLANS_LOCK:
            server.ACTIVE_PLANS.clear()
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()
        with server.LOCK:
            server.HISTORIES["developer"].clear()
            server.HISTORIES["cyber"].clear()

    def test_rejection_of_concurrent_second_plan(self):
        """A conversation with an active running plan refuses to start another plan."""
        conv_id = "pc:developer"
        mock_worker = MagicMock()
        mock_worker.is_alive.return_value = True

        with server.ACTIVE_PLANS_LOCK:
            server.ACTIVE_PLANS[conv_id] = {
                "title": "PrimaryPlan",
                "status": "running",
                "worker": mock_worker,
            }

        res = server.run_skill(
            self.cfg,
            "PLAN",
            "SecondaryPlan\nNOTE: step1 | content",
            source="pc",
            mode="developer",
            conv_id=conv_id,
        )
        self.assertIn("Refused", str(res))
        self.assertIn("PrimaryPlan", str(res))
        self.assertIn("currently running in the background", str(res))

    def test_rejection_of_chat_message_while_worker_runs(self):
        """User chat messages are rejected with clear status while the plan worker is running."""
        conv_id = "pc:developer"
        mock_worker = MagicMock()
        mock_worker.is_alive.return_value = True

        with server.ACTIVE_PLANS_LOCK:
            server.ACTIVE_PLANS[conv_id] = {
                "title": "BuildPipeline",
                "status": "running",
                "worker": mock_worker,
            }

        chat_res = server.chat("What is the system uptime?", source="pc", mode="developer")
        reply = chat_res.get("reply", "") if isinstance(chat_res, dict) else str(chat_res)
        self.assertIn("Plan 'BuildPipeline' is currently running in the background", reply)
        self.assertIn("Please wait for it to complete or pause", reply)

    def test_different_conversations_can_run_independently(self):
        """A running plan on pc:developer does not block chat or plans on another conversation."""
        conv_dev = "pc:developer"
        conv_cyber = "pc:cyber"
        mock_worker = MagicMock()
        mock_worker.is_alive.return_value = True

        with server.ACTIVE_PLANS_LOCK:
            server.ACTIVE_PLANS[conv_dev] = {
                "title": "DevPlan",
                "status": "running",
                "worker": mock_worker,
            }

        with patch("server.call_llm", return_value="Cyber response OK"):
            res_cyber = server.chat("Run security scan", source="pc", mode="cyber")
            reply = res_cyber.get("reply", "") if isinstance(res_cyber, dict) else str(res_cyber)
            self.assertIn("Cyber response OK", reply)

    def test_active_plan_cleaned_up_on_completion_and_cancellation(self):
        """ACTIVE_PLANS map is cleaned up after a plan completes or is cancelled."""
        conv_id = "pc:developer"
        # 1. Successful execution cleans up
        plan_tag = "QuickPlan\nNOTE: Step1 | Done"
        server.run_skill(self.cfg, "PLAN", plan_tag, source="pc", mode="developer", conv_id=conv_id)
        with server.ACTIVE_PLANS_LOCK:
            self.assertNotIn(conv_id, server.ACTIVE_PLANS)

        # 2. Paused plan updates status to paused
        gated_plan_tag = "PausedPlan\nCMD: echo gated\nNOTE: Step2 | Done"
        res_pause = server.run_skill(self.cfg, "PLAN", gated_plan_tag, source="pc", mode="developer", conv_id=conv_id)
        with server.ACTIVE_PLANS_LOCK:
            self.assertIn(conv_id, server.ACTIVE_PLANS)
            self.assertEqual(server.ACTIVE_PLANS[conv_id]["status"], "paused")

        # 3. User denial cleans up
        with server.PENDING_LOCK:
            p_id = list(server.PENDING_ACTIONS.keys())[0]
            pending_item = server.PENDING_ACTIONS[p_id]

        with server.LOCK:
            server.HISTORIES["developer"].append({
                "role": "assistant",
                "content": f"[Action Requires Confirmation: {pending_item.get('prompt')}]"
            })

        server.chat("no", source="pc", mode="developer")
        with server.ACTIVE_PLANS_LOCK:
            self.assertNotIn(conv_id, server.ACTIVE_PLANS)


if __name__ == "__main__":
    unittest.main()
