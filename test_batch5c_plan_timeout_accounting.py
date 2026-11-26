"""
Regression tests for Batch 5c Item 4:
- Plan timeout accounting tracks active_seconds accumulated across active execution segments
- Pauses/waiting time (e.g. 4 minutes) excluded from timeout accounting and succeeds
- 301 seconds of active execution fails with timeout
- Active execution cap does NOT reset on resume
- Single step exceeding 60s fails with per-step timeout.
"""
import time
import unittest
from unittest.mock import patch, MagicMock

import plan_mode
import server


class TestBatch5cPlanTimeoutAccounting(unittest.TestCase):
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

    def tearDown(self):
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()
        with server.ACTIVE_PLANS_LOCK:
            server.ACTIVE_PLANS.clear()

    def test_four_minute_pause_succeeds(self):
        """A plan that pauses for 4 minutes (240s wall-clock time) executes successfully because active_seconds is low."""
        mock_current_time = [1000.0]

        def fake_time():
            return mock_current_time[0]

        with patch("time.time", side_effect=fake_time):
            # Step 1: Pauses for confirmation
            plan_data = {
                "title": "PauseTest",
                "steps": ["CMD: echo step1", "NOTE: step2 | finish"],
            }

            def paused_runner(step, *args):
                mock_current_time[0] += 2.0  # 2s active work
                return {
                    "ok": True,
                    "paused": True,
                    "pending_info": {
                        "id": "p_pause_1",
                        "prompt": "Approve step1",
                        "plan_state": {"title": "PauseTest"},
                    },
                }

            batch1 = plan_mode.execute_plan_batch(plan_data, cfg=self.cfg, runner=paused_runner)
            self.assertTrue(batch1.get("paused"))
            self.assertAlmostEqual(batch1.get("active_seconds"), 2.0)

            # SIMULATE 4 MINUTES (240 SECONDS) OF WALL-CLOCK PAUSE WAITING FOR USER APPROVAL
            mock_current_time[0] += 240.0

            # Step 2: Resume remaining steps
            resumed_plan_state = {
                "title": "PauseTest",
                "all_steps": ["CMD: echo step1", "NOTE: step2 | finish"],
                "completed": ["CMD: echo step1"],
                "remaining_steps": ["NOTE: step2 | finish"],
                "active_seconds": batch1.get("active_seconds"),
            }

            def finish_runner(step, *args):
                mock_current_time[0] += 3.0  # 3s active work
                return "Step 2 Done"

            batch2 = plan_mode.execute_plan_batch(resumed_plan_state, cfg=self.cfg, runner=finish_runner)
            self.assertTrue(batch2.get("ok"), "Plan should succeed after 4-min pause since active execution is only 5s")
            self.assertAlmostEqual(batch2.get("active_seconds"), 5.0)

    def test_three_hundred_one_seconds_active_fails(self):
        """Accumulated active execution time exceeding 300 seconds triggers timeout."""
        mock_current_time = [1000.0]

        def fake_time():
            return mock_current_time[0]

        with patch("time.time", side_effect=fake_time):
            plan_data = {
                "title": "LongActivePlan",
                "steps": [f"NOTE: step_{i}" for i in range(8)],
                "active_seconds": 0.0,
            }

            def long_runner(step, *args):
                mock_current_time[0] += 45.0  # Each step takes 45s active (within 60s per-step cap)
                return "OK"

            # 7 steps * 45s = 315s active > 300s
            batch_res = plan_mode.execute_plan_batch(plan_data, cfg=self.cfg, runner=long_runner)
            self.assertFalse(batch_res["ok"])
            self.assertTrue(batch_res.get("timed_out"))
            self.assertIn("Plan execution timed out after", batch_res["error"])
            self.assertIn("maximum allowed: 300s", batch_res["error"])

    def test_cap_does_not_reset_on_resume(self):
        """Active seconds accumulated before a pause carry over and are not reset on resume."""
        mock_current_time = [1000.0]

        def fake_time():
            return mock_current_time[0]

        with patch("time.time", side_effect=fake_time):
            # Phase 1: Executes with 220 seconds of active execution, then pauses
            plan_data = {
                "title": "CarryoverPlan",
                "steps": ["NOTE: step1", "CMD: echo pause", "NOTE: step3"],
                "active_seconds": 0.0,
            }

            def runner_phase1(step, idx, *args):
                if "CMD:" in step:
                    return {
                        "ok": True,
                        "paused": True,
                        "pending_info": {
                            "id": "p_carryover",
                            "plan_state": {"title": "CarryoverPlan"},
                        },
                    }
                mock_current_time[0] += 55.0  # step1 takes 55s active
                return "OK"

            batch1 = plan_mode.execute_plan_batch(plan_data, cfg=self.cfg, runner=runner_phase1)
            self.assertTrue(batch1.get("paused"))
            self.assertAlmostEqual(batch1.get("active_seconds"), 55.0)

            # Phase 2: Resume with active_seconds set to 260s (e.g. from prior runs)
            resumed_state = {
                "title": "CarryoverPlan",
                "steps": ["NOTE: step1", "CMD: echo pause", "NOTE: step3"],
                "completed": ["NOTE: step1", "CMD: echo pause"],
                "remaining_steps": ["NOTE: step3"],
                "active_seconds": 260.0,  # 260s already spent
            }

            def runner_phase2(step, *args):
                mock_current_time[0] += 50.0  # 260s + 50s = 310s > 300s
                return "OK"

            batch2 = plan_mode.execute_plan_batch(resumed_state, cfg=self.cfg, runner=runner_phase2)
            self.assertFalse(batch2["ok"])
            self.assertTrue(batch2.get("timed_out"), "Cap must carry over across resume and abort when reaching 310s")

    def test_per_step_timeout_sixty_seconds(self):
        """A single step running longer than 60 seconds aborts with a per-step timeout error."""
        mock_current_time = [1000.0]

        def fake_time():
            return mock_current_time[0]

        with patch("time.time", side_effect=fake_time):
            plan_data = {
                "title": "PerStepTimeoutPlan",
                "steps": ["NOTE: slow_step", "NOTE: next_step"],
            }

            def slow_runner(step, *args):
                mock_current_time[0] += 65.0  # 65s > 60s per-step cap
                return "OK"

            batch_res = plan_mode.execute_plan_batch(plan_data, cfg=self.cfg, runner=slow_runner)
            self.assertFalse(batch_res["ok"])
            self.assertTrue(batch_res.get("timed_out"))
            self.assertIn("Plan step timed out", batch_res["error"])
            self.assertIn("exceeded per-step timeout of 60s", batch_res["error"])


if __name__ == "__main__":
    unittest.main()
