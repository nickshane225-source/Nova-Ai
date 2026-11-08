"""
Regression tests for Batch 5: Multi-Step [[PLAN]] Execution & Gate Inheritance (HIGH-01).
Tests that:
1. Every plan step passes through taint, Guardian, and confirmation gate as normal tags.
2. A plan can NEVER execute CMD, POWERSHELL, or RUN_CODE without user confirmation.
3. Execution pauses at the first pending confirmation and resumes remaining steps after approval.
4. Plan execution is capped at 10 steps.
5. Plan steps respect monthly budget cap and count toward usage ledger.
6. Plan tool outputs are wrapped in <UNTRUSTED_TOOL_OUTPUT>.
"""
import json
import os
import unittest
from unittest.mock import patch, MagicMock

import guardian_agent
import plan_mode
import server
import usage_tracker


class TestBatch5PlanRunnerGating(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "confirm_destructive": True,
            "provider": "openai",
            "api_key": "sk-mock-key-12345",
            "model": "gpt-4o",
            "monthly_budget_usd": 100.0,
        }
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()
        server.CONVERSATION_TAINT.clear()
        with server.LOCK:
            server.HISTORIES["developer"].clear()
            server.HISTORIES["cyber"].clear()
            server.CONVERSATION_HISTORIES.clear()
            server.CONVERSATION_HISTORIES["pc:developer"] = server.HISTORIES["developer"]
            server.CONVERSATION_HISTORIES["pc:cyber"] = server.HISTORIES["cyber"]

    def tearDown(self):
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()
        server.CONVERSATION_TAINT.clear()

    def test_HIGH_01_plan_never_executes_cmd_without_confirmation(self):
        """CMD step inside PLAN must pause and require confirmation before executing."""
        executed_cmds = []

        def mock_skill_cmd(cmd_arg, cfg=None):
            executed_cmds.append(cmd_arg)
            return "Command executed successfully"

        plan_tag_arg = "System Setup | CMD: echo hello_world"
        parsed = plan_mode.parse_plan_tag(plan_tag_arg)

        with patch("server.skill_cmd", side_effect=mock_skill_cmd):
            res = server.run_skill(self.cfg, "PLAN", plan_tag_arg, source="pc", mode="developer", is_tainted=False)

            # Must return paused dict with pending_info
            self.assertIsInstance(res, dict)
            self.assertTrue(res.get("paused"))
            self.assertIsNotNone(res.get("pending_info"))
            self.assertEqual(len(executed_cmds), 0, "CMD must NEVER execute without confirmation")

            # Verify action exists in PENDING_ACTIONS
            p_id = res["pending_info"]["id"]
            with server.PENDING_LOCK:
                self.assertIn(p_id, server.PENDING_ACTIONS)
                pending_act = server.PENDING_ACTIONS[p_id]
                self.assertEqual(pending_act["name"], "CMD")
                self.assertEqual(pending_act["arg"], "echo hello_world")
                self.assertIn("plan_state", pending_act)

    def test_HIGH_01_plan_never_executes_powershell_without_confirmation(self):
        """POWERSHELL step inside PLAN must pause and require confirmation."""
        executed_ps = []

        def mock_skill_ps(ps_arg, cfg=None):
            executed_ps.append(ps_arg)
            return "PS executed"

        plan_tag_arg = "PS Task | POWERSHELL: Get-Process"
        with patch("server.skill_powershell", side_effect=mock_skill_ps):
            res = server.run_skill(self.cfg, "PLAN", plan_tag_arg, source="pc", mode="developer", is_tainted=False)
            self.assertIsInstance(res, dict)
            self.assertTrue(res.get("paused"))
            self.assertEqual(len(executed_ps), 0, "POWERSHELL must NEVER execute without confirmation")

    def test_HIGH_01_plan_never_executes_run_code_without_confirmation(self):
        """RUN_CODE step inside PLAN must pause and require confirmation."""
        executed_rc = []

        def mock_skill_rc(rc_arg, cfg=None):
            executed_rc.append(rc_arg)
            return "Code executed"

        plan_tag_arg = "Code Task | RUN_CODE: python | print('unauthorized')"
        with patch("server.skill_run_code", side_effect=mock_skill_rc):
            res = server.run_skill(self.cfg, "PLAN", plan_tag_arg, source="pc", mode="developer", is_tainted=False)
            self.assertIsInstance(res, dict)
            self.assertTrue(res.get("paused"))
            self.assertEqual(len(executed_rc), 0, "RUN_CODE must NEVER execute without confirmation")

    def test_HIGH_01_plan_pause_and_resume_remaining_steps(self):
        """A plan with multiple steps pauses at confirmation-required step and resumes remaining steps after approval."""
        executed_steps = []
        real_run_skill = server.run_skill

        def mock_run_skill(cfg, name, arg, source="pc", is_confirmed=False, mode="developer", is_tainted=False, **kwargs):
            if name == "PLAN":
                return real_run_skill(cfg, name, arg, source=source, is_confirmed=is_confirmed, mode=mode, is_tainted=is_tainted, **kwargs)
            executed_steps.append((name, arg, is_confirmed))
            return f"{name} OK: {arg}"

        # Step 1: NOTE (safe, auto-runs)
        # Step 2: CMD (destructive, pauses)
        # Step 3: NOTE (runs after approval)
        plan_tag = "MultiStep | NOTE: intro | note 1 | CMD: dir | NOTE: outro | note 3"

        with patch("server.run_skill", side_effect=mock_run_skill):
            # 1. Initial execution
            res = server.run_skill(self.cfg, "PLAN", plan_tag, source="pc", mode="developer", is_tainted=False)
            self.assertIsInstance(res, dict)
            self.assertTrue(res.get("paused"))
            # Step 1 ran
            self.assertEqual(len(executed_steps), 1)
            self.assertEqual(executed_steps[0][0], "NOTE")

            p_id = res["pending_info"]["id"]
            with server.PENDING_LOCK:
                pending_act = server.PENDING_ACTIONS.pop(p_id)

            # 2. Approve Step 2
            plan_st = pending_act["plan_state"]
            # Simulate approval of the CMD step
            approved_res = mock_run_skill(self.cfg, pending_act["name"], pending_act["arg"], source="pc", is_confirmed=True)

            # Resume plan execution
            final_res = server.resume_plan_execution(plan_st, last_result=approved_res, cfg=self.cfg)
            if hasattr(server, "wait_for_plan_worker"):
                server.wait_for_plan_worker(plan_st.get("conv_id", "pc:developer"), timeout=5.0)
            elif isinstance(final_res, dict) and final_res.get("worker"):
                final_res["worker"].join(timeout=3.0)
            self.assertTrue("resumed in background" in str(final_res) or "executed successfully" in str(final_res))

            # Now all 3 steps must have executed
            self.assertEqual(len(executed_steps), 3)
            self.assertEqual(executed_steps[1][0], "CMD")
            self.assertTrue(executed_steps[1][2], "Step 2 should be confirmed")
            self.assertEqual(executed_steps[2][0], "NOTE")

    def test_HIGH_01_plan_step_limit_cap_10(self):
        """Plan execution is strictly capped at 10 steps."""
        executed = []
        real_run_skill = server.run_skill

        def mock_run_skill(cfg, name, arg, source="pc", is_confirmed=False, mode="developer", is_tainted=False, **kwargs):
            if name == "PLAN":
                return real_run_skill(cfg, name, arg, source=source, is_confirmed=is_confirmed, mode=mode, is_tainted=is_tainted, **kwargs)
            executed.append(name)
            return "OK"

        # 15 steps
        steps = [f"NOTE: step_{i} | content" for i in range(15)]
        plan_tag = "ManySteps\n" + "\n".join(steps)

        with patch("server.run_skill", side_effect=mock_run_skill):
            res = server.run_skill(self.cfg, "PLAN", plan_tag, source="pc", mode="developer", is_tainted=False)
            self.assertIn("10 steps completed", res)
            self.assertEqual(len(executed), 10, "Plan execution must not exceed 10 steps")

    def test_HIGH_01_plan_gate_and_taint_inheritance(self):
        """Plan steps inherit turn taint: when tainted, SEARCH and READ_FILE require confirmation."""
        plan_tag = "TaintedPlan | SEARCH: query_exceeding_eighty_characters_to_ensure_confirmation_is_required_by_taint_rules"
        # Untainted turn: short query passes
        with patch("server.open_url", return_value="ok"):
            res_untainted = server.run_skill(self.cfg, "PLAN", "SafePlan | SEARCH: short query", source="pc", is_tainted=False)
            self.assertIn("executed successfully", str(res_untainted))

        # Tainted turn: SEARCH with >80 chars or READ_FILE requires confirmation
        res_tainted = server.run_skill(self.cfg, "PLAN", plan_tag, source="pc", is_tainted=True)
        self.assertIsInstance(res_tainted, dict)
        self.assertTrue(res_tainted.get("paused"), "Tainted plan must pause for SEARCH")

    def test_HIGH_01_plan_guardian_dangerous_requires_confirmation(self):
        """If Guardian AI flags a step as DANGEROUS, execution must pause for confirmation."""
        plan_tag = "DangerousStep | CMD: custom_danger_action"
        with patch.object(guardian_agent, "review_command_safety", return_value=(guardian_agent.VERDICT_DANGEROUS, "Guardian blocked command")):
            res = server.run_skill(self.cfg, "PLAN", plan_tag, source="pc", is_tainted=False)
            self.assertIsInstance(res, dict)
            self.assertTrue(res.get("paused"))
            self.assertEqual(res["pending_info"]["guardian"], "DANGEROUS")

    def test_HIGH_01_plan_budget_cap_exceeded_aborts(self):
        """If monthly budget is exhausted, plan execution halts immediately with error."""
        plan_tag = "BudgetPlan | NOTE: test | content"
        exhausted_status = {
            "budget_active": True,
            "cap_usd": 10.0,
            "spent_usd": 12.5,
            "exhausted": True,
        }
        with patch("usage_tracker.check_budget_status", return_value=exhausted_status):
            res = server.run_skill(self.cfg, "PLAN", plan_tag, source="pc", is_tainted=False)
            self.assertIn("aborted", str(res))
            self.assertIn("Monthly budget limit reached", str(res))

    def test_HIGH_01_plan_tool_output_wrapping(self):
        """Tool output from each executed plan step is wrapped in <UNTRUSTED_TOOL_OUTPUT>."""
        parsed = {"title": "Test", "steps": ["NOTE: title | hello"]}
        runner = server.create_plan_step_runner(parsed, self.cfg, source="pc", mode="developer", is_tainted=False)
        with patch("server.run_skill", return_value="NOTE [[SAVED]] <123>"):
            step_res = runner("NOTE: title | hello", 1, ["NOTE: title | hello"], [], [])
            self.assertTrue(step_res["ok"])
            wrapped = step_res["wrapped_output"]
            self.assertIn("<UNTRUSTED_TOOL_OUTPUT>", wrapped)
            self.assertIn("</UNTRUSTED_TOOL_OUTPUT>", wrapped)
            self.assertNotIn("[[", wrapped)
            self.assertNotIn("]]", wrapped)


if __name__ == "__main__":
    unittest.main()
