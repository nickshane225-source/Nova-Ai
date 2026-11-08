"""
Unit tests for Task 4: Plan Mode Coordinator (plan_mode.py).
Zero third-party pip dependencies - Python standard library only.
"""
import unittest

import plan_mode


class TestPlanMode(unittest.TestCase):
    def test_parse_plan_tag_multiple_steps(self):
        raw_tag = "Refactor auth engine | 1. Backup old config | 2. Implement DPAPI cipher | 3. Run regression tests"
        plan = plan_mode.parse_plan_tag(raw_tag)
        self.assertEqual(plan["title"], "Refactor auth engine")
        self.assertEqual(len(plan["steps"]), 3)
        self.assertEqual(plan["steps"][0], "1. Backup old config")
        self.assertEqual(plan["steps"][1], "2. Implement DPAPI cipher")
        self.assertEqual(plan["steps"][2], "3. Run regression tests")

    def test_parse_plan_tag_newline_delimited_steps(self):
        raw_tag = "Setup Web App\n- Step 1: Create index.html\n- Step 2: Add styles\n- Step 3: Launch dev server"
        plan = plan_mode.parse_plan_tag(raw_tag)
        self.assertEqual(plan["title"], "Setup Web App")
        self.assertEqual(len(plan["steps"]), 3)
        self.assertIn("Create index.html", plan["steps"][0])

    def test_execute_plan_batch_success(self):
        plan = {
            "title": "Test Plan",
            "steps": ["step A", "step B", "step C"]
        }
        executed = []
        def mock_runner(step_text):
            executed.append(step_text)
            return f"Done: {step_text}"

        res = plan_mode.execute_plan_batch(plan, {}, runner=mock_runner)
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["completed"]), 3)
        self.assertEqual(executed, ["step A", "step B", "step C"])

    def test_execute_plan_batch_aborts_on_step_failure(self):
        plan = {
            "title": "Failing Plan",
            "steps": ["step 1", "step 2", "step 3"]
        }
        def mock_runner(step_text):
            if step_text == "step 2":
                raise RuntimeError("Step 2 failed!")
            return f"Done: {step_text}"

        res = plan_mode.execute_plan_batch(plan, {}, runner=mock_runner)
        self.assertFalse(res["ok"])
        self.assertEqual(res["failed_step"], "step 2")
        self.assertEqual(len(res["completed"]), 1)

    def test_run_skill_plan_integration(self):
        import server
        res = server.run_skill({}, "PLAN", "Deploy Update | Check git status | Compile assets")
        self.assertIn("Deploy Update", res)
        self.assertIn("executed successfully", res)

    def test_execute_plan_batch_no_double_execution_on_type_error(self):
        plan = {
            "title": "Side Effect Plan",
            "steps": ["step 1", "step 2"]
        }
        side_effects = []
        def buggy_runner(step_text, idx, all_steps, completed, step_results):
            side_effects.append(step_text)
            # Perform side effect and then raise TypeError
            raise TypeError("simulated inner type error in runner")

        res = plan_mode.execute_plan_batch(plan, {}, runner=buggy_runner)
        self.assertFalse(res["ok"])
        self.assertEqual(res["failed_step"], "step 1")
        self.assertEqual(len(side_effects), 1, "Side effect must only execute once without fallback re-execution")
        self.assertIn("simulated inner type error in runner", res["error"])

    def test_shared_confirmation_gate_identical_pending_entry(self):
        import server
        cfg = {"confirm_destructive": True, "workspace_dir": "D:\\Developer Mode on\\nova-ai"}
        source = "pc"
        mode = "developer"
        conv_id = "pc:developer"
        cmd_text = "echo test_shared_gate_comparison"

        # 1. Path 1: execute_model_tags
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()
        res_tags_1 = server.execute_model_tags(
            [("CMD", cmd_text, 0, 10)],
            cfg,
            jid="jid_gate_test_1",
            mode=mode,
            source=source,
            is_tainted=False,
            conv_id=conv_id,
        )
        pending_1 = res_tags_1.get("pending_info")
        self.assertIsNotNone(pending_1)
        id_1 = pending_1["id"]
        with server.PENDING_LOCK:
            entry_1 = dict(server.PENDING_ACTIONS[id_1])

        # 2. Path 2: plan step runner
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()
        runner = server.create_plan_step_runner(
            {"title": "Unified Gate Test Plan"},
            cfg,
            source=source,
            mode=mode,
            is_tainted=False,
            conv_id=conv_id,
        )
        res_runner = runner(f"CMD: {cmd_text}", 1, [f"CMD: {cmd_text}"], [], [])
        self.assertTrue(res_runner.get("paused"))
        pending_2 = res_runner.get("pending_info")
        self.assertIsNotNone(pending_2)
        id_2 = pending_2["id"]
        with server.PENDING_LOCK:
            entry_2 = dict(server.PENDING_ACTIONS[id_2])

        # Compare entry_1 and entry_2
        self.assertIn("plan_state", entry_2)
        self.assertEqual(entry_2["plan_state"]["title"], "Unified Gate Test Plan")
        self.assertNotIn("plan_state", entry_1)

        # Apart from id, timestamps (created_at, expires_at), and plan_state: entries must be IDENTICAL
        e1_norm = {k: v for k, v in entry_1.items() if k not in ("id", "created_at", "expires_at", "plan_state")}
        e2_norm = {k: v for k, v in entry_2.items() if k not in ("id", "created_at", "expires_at", "plan_state")}
        self.assertEqual(e1_norm, e2_norm)

        # Check required fields
        self.assertEqual(e1_norm["name"], "CMD")
        self.assertEqual(e1_norm["arg"], cmd_text)
        self.assertEqual(e1_norm["command"], cmd_text)
        self.assertEqual(e1_norm["source"], "pc")
        self.assertEqual(e1_norm["mode"], "developer")
        self.assertFalse(e1_norm["is_tainted"])

        # 2000-char rejection check in both paths
        huge_cmd = "dir " + ("a" * 2005)
        # execute_model_tags
        res_huge = server.execute_model_tags(
            [("CMD", huge_cmd, 0, 10)],
            cfg,
            jid="jid_gate_test_huge",
            mode=mode,
            source=source,
            is_tainted=False,
            conv_id=conv_id,
        )
        self.assertIn("exceeds maximum allowed length of 2,000 characters", res_huge["actions"][0]["result"])

        # plan runner
        res_runner_huge = runner(f"CMD: {huge_cmd}", 1, [f"CMD: {huge_cmd}"], [], [])
        self.assertFalse(res_runner_huge.get("ok"))
        self.assertIn("exceeds maximum allowed length of 2,000 characters", res_runner_huge.get("error"))


if __name__ == "__main__":
    unittest.main()
