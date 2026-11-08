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


if __name__ == "__main__":
    unittest.main()
