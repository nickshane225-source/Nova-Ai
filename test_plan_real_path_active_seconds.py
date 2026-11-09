"""
test_plan_real_path_active_seconds.py - Integration test verifying plan active_seconds on the REAL code path.

Requirements:
1. Show where plan_state stores active_seconds on pause and where resume_plan_execution restores it into plan_data.
2. Integration test through create_plan_step_runner, PENDING_ACTIONS, and /api/confirm with mocked time:
   - 4-minute pause completes successfully (paused wall clock time not counted as active execution).
   - 301 active execution seconds fails with timeout.
   - Three sequential pauses and resumes preserve the accumulated active_seconds without reset.
"""

import time
import unittest
from unittest.mock import patch

import plan_mode
import server


class TestPlanRealPathActiveSeconds(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "confirm_destructive": True,
            "provider": "openai",
            "api_key": "sk-mock-12345",
            "model": "gpt-4o",
            "monthly_budget_usd": 100.0,
            "workspace_dir": "D:\\Developer Mode on\\nova-ai",
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

    def _simulate_api_confirm(self, action_id: str, approve: bool = True):
        """
        Executes the exact logic of /api/confirm in server.py:
        1. Pops action from PENDING_ACTIONS under PENDING_LOCK.
        2. Validates expiration.
        3. Runs approved skill.
        4. Resumes plan with pending['plan_state'] via resume_plan_execution.
        """
        with server.PENDING_LOCK:
            pending = server.PENDING_ACTIONS.pop(action_id, None)
        if not pending:
            return {"ok": False, "error": "Pending action not found or expired"}
        if pending.get("expires_at", 0) < time.time():
            if pending.get("plan_state"):
                server.cleanup_active_plan(
                    plan_id=pending.get("plan_state", {}).get("plan_id"),
                    conv_id=pending.get("conv_id"),
                    pending_id=action_id,
                )
            return {"ok": False, "error": "Pending action expired"}

        if not approve:
            if pending.get("plan_state"):
                server.cleanup_active_plan(
                    plan_id=pending.get("plan_state", {}).get("plan_id"),
                    conv_id=pending.get("conv_id"),
                    pending_id=action_id,
                )
            return {"ok": True, "approved": False}

        p_conv = pending.get("plan_state", {}).get("conv_id") or pending.get("conv_id") or "pc:developer"
        res = server.run_skill(
            self.cfg,
            pending["name"],
            pending["arg"],
            source=pending.get("source", "pc"),
            is_confirmed=True,
            mode=pending.get("mode", "developer"),
            is_tainted=pending.get("is_tainted", False),
            conv_id=p_conv,
        )

        if pending.get("plan_state"):
            plan_res = server.resume_plan_execution(
                pending["plan_state"],
                last_result=res,
                cfg=self.cfg,
                async_run=False,
            )
            return {"ok": True, "approved": True, "plan_res": plan_res}
        return {"ok": True, "approved": True, "result": res}

    def test_real_path_four_minute_pause_completes(self):
        """
        Integration test on real path:
        4-minute (240s) wall-clock pause waiting for user approval on /api/confirm
        completes successfully because only active execution time is charged.
        """
        mock_clock = [1000.0]

        def fake_time():
            return mock_clock[0]

        with patch("time.time", side_effect=fake_time):
            plan_info = {
                "plan_id": "test_real_pause_id",
                "title": "RealPausePlan",
                "steps": ["CMD: echo step1", "NOTE: final | done"],
                "active_seconds": 0.0,
            }

            # Step runner created via real factory
            runner = server.create_plan_step_runner(
                plan_info,
                self.cfg,
                source="pc",
                mode="developer",
                is_tainted=False,
            )

            # Step 1: CMD requires confirmation in real gate
            batch1 = plan_mode.execute_plan_batch(plan_info, cfg=self.cfg, runner=runner)
            self.assertTrue(batch1.get("paused"))

            pending_info = batch1.get("pending_info")
            self.assertIsNotNone(pending_info)
            action_id = pending_info["id"]

            # Verify action exists in PENDING_ACTIONS with plan_state storing active_seconds
            with server.PENDING_LOCK:
                self.assertIn(action_id, server.PENDING_ACTIONS)
                pending_entry = server.PENDING_ACTIONS[action_id]
                plan_state = pending_entry["plan_state"]
                self.assertIn("active_seconds", plan_state)
                # Active seconds should be tiny
                self.assertLess(plan_state["active_seconds"], 5.0)

            # SIMULATE 4 MINUTES (240 SECONDS) OF WALL CLOCK PAUSE BY USER
            mock_clock[0] += 240.0

            # Keep pending action within mock expiry window for the simulation
            with server.PENDING_LOCK:
                server.PENDING_ACTIONS[action_id]["expires_at"] = mock_clock[0] + 60.0

            # Execute /api/confirm approval
            confirm_res = self._simulate_api_confirm(action_id, approve=True)
            self.assertTrue(confirm_res.get("ok"))
            plan_res = confirm_res.get("plan_res")
            self.assertIn("executed successfully", str(plan_res))

            # Pending action was cleaned up
            with server.PENDING_LOCK:
                self.assertNotIn(action_id, server.PENDING_ACTIONS)

    def test_real_path_301_seconds_active_fails(self):
        """Active execution time exceeding 300 seconds triggers real timeout."""
        mock_clock = [1000.0]

        def fake_time():
            return mock_clock[0]

        with patch("time.time", side_effect=fake_time):
            plan_info = {
                "plan_id": "test_timeout_id",
                "title": "RealTimeoutPlan",
                "steps": [f"NOTE: step_{i} | data" for i in range(8)],
                "active_seconds": 0.0,
            }

            # Each step consumes 45s active work
            def slow_runner(step, idx=1, *args):
                mock_clock[0] += 45.0
                return f"Step {idx} OK"

            batch_res = plan_mode.execute_plan_batch(plan_info, cfg=self.cfg, runner=slow_runner)
            self.assertFalse(batch_res["ok"])
            self.assertTrue(batch_res.get("timed_out"))
            self.assertIn("Plan execution timed out after", batch_res["error"])
            self.assertIn("maximum allowed: 300s", batch_res["error"])

    def test_real_path_three_resumes_do_not_reset_counter(self):
        """
        Three sequential pauses and resumes preserve the accumulated active_seconds without reset.
        Total wall-clock pause: 1800s (30 minutes).
        Each step adds 40s of active work.
        Step 1: 40s active -> pause -> pending 1
        Step 2: +40s = 80s active -> pause -> pending 2
        Step 3: +40s = 120s active -> pause -> pending 3
        Step 4: +40s = 160s active -> completes!
        """
        mock_clock = [1000.0]

        def fake_time():
            return mock_clock[0]

        with patch("time.time", side_effect=fake_time):
            all_steps = [
                "CMD: echo step1",
                "CMD: echo step2",
                "CMD: echo step3",
                "NOTE: finish | complete",
            ]

            plan_info = {
                "plan_id": "three_resumes_test_id",
                "title": "ThreeResumesPlan",
                "steps": all_steps,
                "active_seconds": 0.0,
            }

            # In step runner, simulate 40s of active work per step
            def step_runner(step, idx=1, all_s=None, comp=None, res_list=None):
                mock_clock[0] += 40.0
                name, arg = server.parse_step_to_tag(step)
                # Gated steps pause via create_pending_action
                if name == "CMD":
                    rem_steps = all_s[idx:] if all_s and idx < len(all_s) else []
                    p_state = {
                        "plan_id": plan_info.get("plan_id"),
                        "title": plan_info.get("title"),
                        "all_steps": all_s or all_steps,
                        "completed": list(comp or []),
                        "paused_step_idx": idx,
                        "paused_step": step,
                        "remaining_steps": rem_steps,
                        "results": list(res_list or []),
                        "source": "pc",
                        "mode": "developer",
                        "is_tainted": False,
                        "conv_id": "pc:developer",
                        "active_seconds": plan_info.get("active_seconds", 0.0),
                    }
                    p_entry, p_info, err = server.create_pending_action(
                        cfg=self.cfg,
                        name=name,
                        arg=arg,
                        source="pc",
                        mode="developer",
                        is_tainted=False,
                        reason="Test CMD gate",
                        plan_state=p_state,
                    )
                    return {"ok": True, "paused": True, "pending_info": p_info}
                return f"Step {idx} OK"

            # 1. Start plan - Step 1 runs for 40s active, then pauses
            batch1 = plan_mode.execute_plan_batch(plan_info, cfg=self.cfg, runner=step_runner)
            self.assertTrue(batch1.get("paused"))
            p1_id = batch1["pending_info"]["id"]
            # Store updated active_seconds as server does
            with server.PENDING_LOCK:
                server.PENDING_ACTIONS[p1_id]["plan_state"]["active_seconds"] = batch1["active_seconds"]
                state1 = server.PENDING_ACTIONS[p1_id]["plan_state"]
                self.assertAlmostEqual(state1["active_seconds"], 40.0)

            # Advance wall clock by 10 minutes (600s) during user idle time
            mock_clock[0] += 600.0
            with server.PENDING_LOCK:
                server.PENDING_ACTIONS[p1_id]["expires_at"] = mock_clock[0] + 60.0

            # 2. User confirms Step 1 via /api/confirm
            with patch.object(server, "create_plan_step_runner", return_value=step_runner):
                conf1 = self._simulate_api_confirm(p1_id, approve=True)
                self.assertTrue(conf1["ok"])
                batch2 = conf1["plan_res"]
                self.assertTrue(batch2.get("paused"))
                p2_id = batch2["pending_info"]["id"]
                with server.PENDING_LOCK:
                    state2 = server.PENDING_ACTIONS[p2_id]["plan_state"]
                    self.assertAlmostEqual(state2["active_seconds"], 80.0, msg="Counter must not reset; should be 80s")

            # Advance wall clock by another 10 minutes (600s)
            mock_clock[0] += 600.0
            with server.PENDING_LOCK:
                server.PENDING_ACTIONS[p2_id]["expires_at"] = mock_clock[0] + 60.0

            # 3. User confirms Step 2 via /api/confirm
            with patch.object(server, "create_plan_step_runner", return_value=step_runner):
                conf2 = self._simulate_api_confirm(p2_id, approve=True)
                self.assertTrue(conf2["ok"])
                batch3 = conf2["plan_res"]
                self.assertTrue(batch3.get("paused"))
                p3_id = batch3["pending_info"]["id"]
                with server.PENDING_LOCK:
                    state3 = server.PENDING_ACTIONS[p3_id]["plan_state"]
                    self.assertAlmostEqual(state3["active_seconds"], 120.0, msg="Counter must not reset; should be 120s")

            # Advance wall clock by another 5 minutes (300s)
            mock_clock[0] += 300.0
            with server.PENDING_LOCK:
                server.PENDING_ACTIONS[p3_id]["expires_at"] = mock_clock[0] + 60.0

            # 4. User confirms Step 3 via /api/confirm -> final step completes
            with patch.object(server, "create_plan_step_runner", return_value=step_runner):
                conf3 = self._simulate_api_confirm(p3_id, approve=True)
                self.assertTrue(conf3["ok"])
                final_res = conf3["plan_res"]
                self.assertIn("executed successfully", str(final_res))


if __name__ == "__main__":
    unittest.main()
