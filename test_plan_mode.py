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

    def test_plan_step_taint_propagation_and_next_turn_confirmation(self):
        import server
        from unittest.mock import patch

        cfg = {"workspace_dir": "D:\\Developer Mode on\\nova-ai"}
        conv_id = "test_plan_taint_propagation_conv"
        server.CONVERSATION_TAINT[conv_id] = False

        # Plan with BROWSER_READ step
        plan_text = "Web Investigation | BROWSER_READ: https://news.example.com/item"
        with patch("nova_browser.read_page_content", return_value={"title": "News", "url": "https://news.example.com/item", "content": "Untrusted text"}):
            res = server.run_skill(
                cfg, "PLAN", plan_text, source="pc", mode="developer", is_tainted=False, conv_id=conv_id
            )

        # 1. Assert conversation taint store was updated immediately
        self.assertTrue(server.CONVERSATION_TAINT.get(conv_id, False))

        # 2. Next turn: READ_FILE and SEARCH must require confirmation because conversation is tainted
        next_turn_taint = server.CONVERSATION_TAINT.get(conv_id, False)

        # READ_FILE
        needs_confirm_read, reason_read = server.check_tool_confirmation_required(
            cfg, "READ_FILE", "passwords.txt", is_tainted=next_turn_taint, source="pc", conv_id=conv_id
        )
        self.assertTrue(needs_confirm_read)
        self.assertIn("tainted", reason_read.lower())

        # 3. Resume path: If a paused plan is resumed with a tainted step, taint propagates immediately
        conv_id_resume = "test_resume_plan_taint_conv"
        server.CONVERSATION_TAINT[conv_id_resume] = False
        paused_plan_state = {
            "title": "Resume Taint Plan",
            "all_steps": ["CMD: echo 1", "BROWSER_READ: https://example.com/data"],
            "completed": ["CMD: echo 1"],
            "remaining_steps": ["BROWSER_READ: https://example.com/data"],
            "paused_step_idx": 1,
            "paused_step": "CMD: echo 1",
            "source": "pc",
            "mode": "developer",
            "is_tainted": False,
            "conv_id": conv_id_resume,
        }
        with patch("nova_browser.read_page_content", return_value={"title": "Data", "url": "https://example.com/data", "content": "Untrusted"}):
            res_res = server.resume_plan_execution(paused_plan_state, last_result="1", cfg=cfg)
            if isinstance(res_res, dict) and res_res.get("worker"):
                res_res["worker"].join(2.0)

        self.assertTrue(server.CONVERSATION_TAINT.get(conv_id_resume, False), "Resume path must propagate taint to conversation taint store")

    def test_paused_plan_approval_prompt_resume_deny_and_expiry(self):
        import server
        from unittest.mock import patch
        import time

        # Reset history and state
        with server.LOCK:
            server.HISTORIES["developer"].clear()
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()

        # Mock LLM returning a PLAN tag whose step 2 is a CMD
        mock_plan_llm_reply = (
            "Here is the execution plan:\n"
            "[[PLAN: Deploy Pipeline | STEP: Prep environment | CMD: echo deploying_service_running | STEP: Verify service health]]"
        )

        with patch("server.call_llm", return_value=mock_plan_llm_reply):
            res_chat = server.chat("deploy the pipeline", source="pc", mode="developer")

        # 1. Verify approval prompt appears in chat
        self.assertIn("[Action Requires Confirmation:", res_chat["reply"])
        self.assertIn("pending", res_chat)
        action_id = res_chat["pending"]["id"]
        self.assertEqual(res_chat["pending"]["name"], "CMD")
        with server.PENDING_LOCK:
            self.assertIn(action_id, server.PENDING_ACTIONS)
            pending_entry = server.PENDING_ACTIONS[action_id]
            self.assertEqual(pending_entry["plan_state"]["title"], "Deploy Pipeline")
            self.assertEqual(pending_entry["plan_state"]["paused_step_idx"], 2)

        # 2. Approving resumes remaining steps non-blocking with resumed message
        res_approve = server.chat("yes", source="pc", mode="developer")
        self.assertIn("resumed in background", res_approve["reply"])
        with server.PENDING_LOCK:
            self.assertNotIn(action_id, server.PENDING_ACTIONS)

        # 3. Denying aborts the plan
        with server.LOCK:
            server.HISTORIES["developer"].clear()
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()

        mock_plan_deny_reply = (
            "Here is the execution plan:\n"
            "[[PLAN: Abort Pipeline | STEP: Prep | CMD: echo abort_me_cmd | STEP: Post-step]]"
        )
        with patch("server.call_llm", return_value=mock_plan_deny_reply):
            res_chat_deny = server.chat("run abort pipeline", source="pc", mode="developer")

        self.assertIn("pending", res_chat_deny)
        deny_action_id = res_chat_deny["pending"]["id"]

        res_deny = server.chat("no", source="pc", mode="developer")
        self.assertIn("cancelled", res_deny["reply"])
        self.assertIn("Plan 'Abort Pipeline' aborted", res_deny["reply"])
        with server.PENDING_LOCK:
            self.assertNotIn(deny_action_id, server.PENDING_ACTIONS)

        # 4. Expiry cleans up
        with server.LOCK:
            server.HISTORIES["developer"].clear()
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()

        with patch("server.call_llm", return_value=mock_plan_deny_reply):
            res_chat_exp = server.chat("run expire pipeline", source="pc", mode="developer")

        exp_action_id = res_chat_exp["pending"]["id"]
        with server.PENDING_LOCK:
            # Force expiration
            server.PENDING_ACTIONS[exp_action_id]["expires_at"] = time.time() - 10

        # Attempting chat turn after expiry purges it
        with patch("server.call_llm", return_value="All systems nominal."):
            server.chat("status update", source="pc", mode="developer")
        with server.PENDING_LOCK:
            self.assertNotIn(exp_action_id, server.PENDING_ACTIONS)

    def test_plan_step_nested_plan_refused(self):
        import server
        # Direct batch execution check
        plan_data = {
            "title": "Outer Plan",
            "steps": ["STEP: step 1", "PLAN: Inner | a | b"]
        }
        res_batch = plan_mode.execute_plan_batch(plan_data, {})
        self.assertFalse(res_batch["ok"])
        self.assertIn("Nested plans are not allowed", res_batch["error"])

        # run_skill check
        res_skill = server.run_skill({}, "PLAN", "Outer Plan | STEP: step 1 | PLAN: Nested | step a")
        self.assertIn("Nested plans are not allowed", res_skill)

        # Embedded [[PLAN: ...]] tag check
        res_embedded = server.run_skill({}, "PLAN", "Outer Plan | STEP: step 1 | [[PLAN: Nested | step a]]")
        self.assertIn("Nested plans are not allowed", res_embedded)

    def test_total_tool_executions_cap_at_25_per_turn(self):
        import server

        # 1. Direct execute_model_tags cap check
        tags_30 = [("NOTE", f"note {i}", 0, 10) for i in range(30)]
        turn_counter = [0]
        res_exec = server.execute_model_tags(tags_30, {}, turn_tool_executions=turn_counter)
        self.assertEqual(turn_counter[0], 25)
        # 25 executed actions + 1 halted action
        self.assertEqual(len(res_exec["actions"]), 26)
        self.assertIn("Maximum of 25 tool executions reached", res_exec["actions"][-1]["result"])

        # 2. Plan step execution cap check
        plan_steps = [f"NOTE: note {i}" for i in range(10)]
        counter_plan = [20]  # Already used 20
        runner = server.create_plan_step_runner({"title": "Cap Plan"}, {}, turn_tool_executions=counter_plan)
        res_plan = plan_mode.execute_plan_batch({"title": "Cap Plan", "steps": plan_steps}, {}, runner=runner)
        self.assertFalse(res_plan["ok"])
        self.assertEqual(counter_plan[0], 25)
        self.assertIn("Maximum of 25 tool executions reached", res_plan["error"])

    def test_honest_usage_accounting_zero_tokens_and_budget_exhaustion(self):
        import server
        from unittest.mock import patch
        import usage_tracker

        cfg = {"monthly_budget_usd": 10.0}

        # 1. Plan tool steps log 0 tokens and 0 cost
        with patch("usage_tracker.record_usage") as mock_record:
            res = server.run_skill(cfg, "PLAN", "Usage Accounting Plan | NOTE: step a | NOTE: step b")
            self.assertIn("executed successfully", res)
            self.assertGreaterEqual(mock_record.call_count, 1)
            for call in mock_record.call_args_list:
                kw = call.kwargs
                self.assertEqual(kw.get("input_tokens"), 0)
                self.assertEqual(kw.get("output_tokens"), 0)

        # 2. Budget exhaustion stops plan immediately
        with patch("usage_tracker.check_budget_status", return_value={"exhausted": True, "spent_usd": 15.75}):
            res_exhausted = server.run_skill(cfg, "PLAN", "Exhausted Plan | NOTE: step 1 | NOTE: step 2")
            self.assertIn("aborted", res_exhausted)
            self.assertIn("Monthly budget limit reached ($15.75 spent)", res_exhausted)

    def test_search_hardening_token_shingles_and_bounded_counts(self):
        import server

        # 7c. has_base64_hex_token checks
        self.assertFalse(server.has_base64_hex_token("get_user_authentication_token"))
        self.assertFalse(server.has_base64_hex_token("internationalization-and-localization"))
        self.assertTrue(server.has_base64_hex_token("ZXhhbXBsZXNlY3JldGtleTEyMzQ="))
        self.assertTrue(server.has_base64_hex_token("4a5b6c7d8e9f0123456789abcdef0123"))

        # 7b. Hashed 15-character shingles check
        tainted_sample = "Confidential super secret project database key credentials"
        server.extract_tainted_shingles(tainted_sample)

        # 15+ char matching substring
        self.assertTrue(server.is_text_from_tainted_file("find super secret proj"))
        self.assertFalse(server.is_text_from_tainted_file("completely unrelated text query"))

        # 7a. Bounded CONVERSATION_SEARCH_COUNTS and reset
        server.reset_search_counts()
        for i in range(550):
            server.record_unconfirmed_search(f"conv_{i}")

        self.assertLessEqual(len(server.CONVERSATION_SEARCH_COUNTS), 500)
        self.assertIn("conv_549", server.CONVERSATION_SEARCH_COUNTS)
        self.assertNotIn("conv_0", server.CONVERSATION_SEARCH_COUNTS)

        # Reset specific conv
        server.reset_search_counts(["conv_549"])
        self.assertNotIn("conv_549", server.CONVERSATION_SEARCH_COUNTS)

        # Full reset
        server.reset_search_counts()
        self.assertEqual(len(server.CONVERSATION_SEARCH_COUNTS), 0)

    def test_resume_plan_execution_nonblocking_events_and_timeout(self):
        import time
        import server
        import plan_mode

        # 1. Non-blocking resume execution & immediate return
        plan_state = {
            "title": "Nonblocking Test Plan",
            "all_steps": ["NOTE: step1", "NOTE: step2"],
            "completed": ["NOTE: step1"],
            "remaining_steps": ["NOTE: step2"],
            "started_at": time.time(),
            "source": "pc",
            "mode": "developer",
        }
        res_resume = server.resume_plan_execution(plan_state, last_result="step1 ok", cfg={})
        self.assertIsInstance(res_resume, dict)
        self.assertTrue(res_resume.get("ok"))
        self.assertTrue(res_resume.get("resumed"))
        self.assertIn("resumed in background", res_resume.get("message", ""))
        self.assertIn("worker", res_resume)
        # Wait for worker thread to finish
        res_resume["worker"].join(timeout=3.0)

        # 2. Verify events exposed on status channel (/api/events)
        with server.LOCK:
            event_types = [e.get("type") for e in server.EVENTS]
        self.assertIn("plan_resumed_async", event_types)
        self.assertIn("plan_completed", event_types)

        # 3. 5-minute total plan runtime timeout enforcement
        expired_plan = {
            "title": "Expired Test Plan",
            "steps": ["NOTE: stepA", "NOTE: stepB"],
            "started_at": time.time() - 310,  # 310 seconds ago (> 300s)
        }
        batch_res = plan_mode.execute_plan_batch(expired_plan, cfg={}, runner=lambda s: "ok")
        self.assertFalse(batch_res["ok"])
        self.assertTrue(batch_res.get("timed_out"))
        self.assertIn("Plan execution timed out", batch_res["error"])
        self.assertIn("maximum allowed: 300s", batch_res["error"])

        # 4. Immediate timeout parameter support
        quick_timeout_plan = {
            "title": "Quick Timeout Plan",
            "steps": ["NOTE: step1", "NOTE: step2"],
            "started_at": time.time() - 5,
        }
        res_quick = plan_mode.execute_plan_batch(quick_timeout_plan, cfg={}, runner=lambda s: "ok", timeout=1.0)
        self.assertFalse(res_quick["ok"])
        self.assertTrue(res_quick.get("timed_out"))
        self.assertIn("maximum allowed: 1s", res_quick["error"])


if __name__ == "__main__":
    unittest.main()
