"""
test_plan_fast_approve.py - Verify that active_seconds is passed atomically
into plan_state at the moment create_pending_action is called (no post-hoc patch under a second lock),
and verify fast approval right after pause.
"""

import unittest
import time
from unittest.mock import patch, MagicMock

import server
import plan_mode


class TestPlanFastApprove(unittest.TestCase):

    def setUp(self):
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()
        with server.ACTIVE_PLANS_LOCK:
            server.ACTIVE_PLANS.clear()

    def tearDown(self):
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()
        with server.ACTIVE_PLANS_LOCK:
            server.ACTIVE_PLANS.clear()

    def test_01_active_seconds_passed_atomically_to_plan_state(self):
        """active_seconds must be present in plan_state inside PENDING_ACTIONS immediately at pause."""
        cfg = server.get_config()
        plan_id = "test_plan_fast_1"
        plan_data = {
            "plan_id": plan_id,
            "title": "Fast Approve Test Plan",
            "steps": ["[[NOTE: note_1|content_1]]", "[[CMD: calc]]"],
            "completed": [],
            "results": [],
            "active_seconds": 12.5,
            "started_at": time.time() - 30.0,
        }

        # Create step runner
        runner = server.create_plan_step_runner(
            plan_data,
            cfg=cfg,
            source="pc",
            mode="developer",
            is_tainted=False,
            conv_id="pc:developer",
        )

        # Execute batch
        res = plan_mode.execute_plan_batch(plan_data, cfg=cfg, runner=runner)
        self.assertTrue(res.get("paused"), "Batch must pause at step 2 requiring confirmation")

        # Step 1 was executed, step 2 paused
        pending_info = res.get("pending_info")
        self.assertIsNotNone(pending_info)
        p_id = pending_info["id"]

        # Immediately inspect PENDING_ACTIONS without waiting for any post-hoc patch
        with server.PENDING_LOCK:
            self.assertIn(p_id, server.PENDING_ACTIONS)
            pending_entry = server.PENDING_ACTIONS[p_id]
            self.assertIn("plan_state", pending_entry)
            p_state = pending_entry["plan_state"]

            # active_seconds MUST be >= 12.5 (original 12.5s + time taken for Step 1)
            self.assertGreaterEqual(p_state["active_seconds"], 12.5)

    def test_02_fast_approve_right_after_pause(self):
        """Fast approve immediately following pause resumes with active_seconds preserved."""
        cfg = server.get_config()
        plan_id = "test_plan_fast_2"
        plan_data = {
            "plan_id": plan_id,
            "title": "Fast Approve Resume Plan",
            "steps": ["[[NOTE: initial|note]]", "[[CMD: echo hello]]"],
            "completed": [],
            "results": [],
            "active_seconds": 5.0,
            "started_at": time.time() - 10.0,
        }

        runner = server.create_plan_step_runner(
            plan_data,
            cfg=cfg,
            source="pc",
            mode="developer",
            is_tainted=False,
            conv_id="pc:developer",
        )

        res = plan_mode.execute_plan_batch(plan_data, cfg=cfg, runner=runner)
        self.assertTrue(res.get("paused"))
        pending_id = res["pending_info"]["id"]

        # Immediately simulate fast approve via mock Remote/API handler
        with server.PENDING_LOCK:
            pending = server.PENDING_ACTIONS.pop(pending_id)

        # Verify active_seconds is in plan_state
        initial_active = pending["plan_state"]["active_seconds"]
        self.assertGreaterEqual(initial_active, 5.0)

        # Resume plan with approve
        with patch("server.run_skill", return_value="hello"):
            resume_res = server.resume_plan_execution(pending["plan_state"], last_result="Approved CMD", cfg=cfg)

        # Plan execution completed
        self.assertTrue(isinstance(resume_res, str) or resume_res.get("ok"))


if __name__ == "__main__":
    unittest.main()
