import json
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import audit_logger
import discord_gateway
import plan_mode
import server
import telegram_gateway


class TestPlanLifecycleAndCancellation(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "confirm_destructive": True,
            "provider": "openai",
            "api_key": "sk-mock-test-key-12345",
            "model": "gpt-4o",
            "monthly_budget_usd": 100.0,
            "telegram_enabled": True,
            "telegram_bot_token": "mock_tg_token",
            "telegram_allowed_user_ids": ["12345"],
            "discord_enabled": True,
            "discord_bot_token": "mock_discord_token",
            "discord_channel_ids": ["ch1"],
            "discord_allowed_user_ids": ["user_alice"],
        }
        with server.ACTIVE_PLANS_LOCK:
            server.ACTIVE_PLANS.clear()
        server.CONVERSATION_TAINT.clear()
        server.RUN_CODE_TRUST_STATE.reset()
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()
        with server.LOCK:
            server.HISTORIES["developer"].clear()
            server.HISTORIES["cyber"].clear()

    def tearDown(self):
        with server.ACTIVE_PLANS_LOCK:
            server.ACTIVE_PLANS.clear()
        server.CONVERSATION_TAINT.clear()
        server.RUN_CODE_TRUST_STATE.reset()
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()

    def test_item2_active_plans_keyed_by_random_plan_id_not_title(self):
        """ACTIVE_PLANS must be keyed by a random plan_id (not title or conv_id)."""
        conv_id = "pc:developer"
        gated_plan = "DeploySite\nCMD: npm run build\nNOTE: Step2 | Done"

        res = server.run_skill(self.cfg, "PLAN", gated_plan, source="pc", mode="developer", conv_id=conv_id)
        self.assertTrue(isinstance(res, dict) and res.get("paused"))

        with server.ACTIVE_PLANS_LOCK:
            self.assertEqual(len(server.ACTIVE_PLANS), 1)
            raw_key = list(server.ACTIVE_PLANS.keys())[0]
            plan_obj = list(server.ACTIVE_PLANS.values())[0]

        # Key must not be the title or the conv_id
        self.assertNotEqual(raw_key, "DeploySite")
        self.assertNotEqual(raw_key, conv_id)
        # Key is random hex plan_id matching plan_obj["plan_id"]
        self.assertEqual(raw_key, plan_obj["plan_id"])
        self.assertEqual(plan_obj["title"], "DeploySite")
        self.assertEqual(plan_obj["status"], "paused")

    def test_item2_two_plans_with_same_title_cannot_run_concurrently(self):
        """Two plans with the same title must not run concurrently across any conversations."""
        conv_dev = "pc:developer"
        conv_tg = "telegram:12345"
        gated_plan = "SharedPipeline\nCMD: echo gated\nNOTE: step2 | done"

        # Start plan in developer mode
        res1 = server.run_skill(self.cfg, "PLAN", gated_plan, source="pc", mode="developer", conv_id=conv_dev)
        self.assertTrue(isinstance(res1, dict) and res1.get("paused"))

        # Attempt to start a plan with the same title in another conversation
        res2 = server.run_skill(self.cfg, "PLAN", gated_plan, source="telegram", mode="developer", conv_id=conv_tg)
        self.assertIn("Refused", str(res2))
        self.assertIn("SharedPipeline", str(res2))
        self.assertIn("Two plans with the same title cannot run concurrently", str(res2))

    def test_item2_active_plans_cleanup_when_worker_ends(self):
        """ACTIVE_PLANS entry is cleaned up when plan completes successfully."""
        conv_id = "pc:developer"
        simple_plan = "AutoTask\nNOTE: Step1 | Done\nNOTE: Step2 | Done"

        res = server.run_skill(self.cfg, "PLAN", simple_plan, source="pc", mode="developer", conv_id=conv_id)
        self.assertIn("executed successfully", str(res))
        with server.ACTIVE_PLANS_LOCK:
            self.assertEqual(len(server.ACTIVE_PLANS), 0)

    def test_item2_active_plans_cleanup_when_pending_action_expires(self):
        """ACTIVE_PLANS entry is cleaned up when its paused pending action expires."""
        conv_id = "pc:developer"
        gated_plan = "ExpirePlan\nCMD: echo expire\nNOTE: Step2 | Done"

        server.run_skill(self.cfg, "PLAN", gated_plan, source="pc", mode="developer", conv_id=conv_id)
        with server.ACTIVE_PLANS_LOCK:
            self.assertEqual(len(server.ACTIVE_PLANS), 1)

        # Force expiry in PENDING_ACTIONS
        with server.PENDING_LOCK:
            p_id = list(server.PENDING_ACTIONS.keys())[0]
            server.PENDING_ACTIONS[p_id]["expires_at"] = time.time() - 10.0

        # Trigger chat turn which runs expiry sweep
        with patch("server.call_llm", return_value="Hello human"):
            server.chat("Hello Nova", source="pc", mode="developer")

        # ACTIVE_PLANS must be cleaned up
        with server.ACTIVE_PLANS_LOCK:
            self.assertEqual(len(server.ACTIVE_PLANS), 0)

    def test_item2_active_plans_cleanup_when_pending_action_is_denied(self):
        """ACTIVE_PLANS entry is cleaned up when the user denies the pending step."""
        conv_id = "pc:developer"
        gated_plan = "DeniedPlan\nCMD: echo denied\nNOTE: Step2 | Done"

        server.run_skill(self.cfg, "PLAN", gated_plan, source="pc", mode="developer", conv_id=conv_id)
        with server.ACTIVE_PLANS_LOCK:
            self.assertEqual(len(server.ACTIVE_PLANS), 1)

        with server.PENDING_LOCK:
            p_id = list(server.PENDING_ACTIONS.keys())[0]
            pending_item = server.PENDING_ACTIONS[p_id]

        with server.LOCK:
            server.HISTORIES["developer"].append({
                "role": "assistant",
                "content": f"[Action Requires Confirmation: {pending_item.get('prompt')}]"
            })

        # Say no
        reply = server.chat("no", source="pc", mode="developer")
        self.assertIn("cancelled", str(reply))

        with server.ACTIVE_PLANS_LOCK:
            self.assertEqual(len(server.ACTIVE_PLANS), 0)

    def test_item3_cancel_plan_endpoint_and_audit_logging(self):
        """POST /api/plan/cancel cancels active plans, clears pending actions, and logs 'plan cancelled'."""
        conv_id = "pc:developer"
        gated_plan = "CancelMe\nCMD: echo cancel\nNOTE: Step2 | Done"

        server.run_skill(self.cfg, "PLAN", gated_plan, source="pc", mode="developer", conv_id=conv_id)
        with server.ACTIVE_PLANS_LOCK:
            self.assertEqual(len(server.ACTIVE_PLANS), 1)
        with server.PENDING_LOCK:
            self.assertEqual(len(server.PENDING_ACTIONS), 1)

        with patch("audit_logger.log_audit_event") as mock_audit:
            res = server.cancel_plan(conv_id=conv_id, source="pc")
            self.assertTrue(res.get("ok"))
            self.assertIn("plan cancelled", res.get("message"))

            # Pending action must be cleared
            with server.PENDING_LOCK:
                self.assertEqual(len(server.PENDING_ACTIONS), 0)

            # Audit event must be recorded
            mock_audit.assert_called()
            call_kw = mock_audit.call_args[1]
            self.assertEqual(call_kw.get("tool"), "PLAN")
            self.assertEqual(call_kw.get("status"), "CANCELLED")
            self.assertIn("plan cancelled", call_kw.get("preview"))

    def test_item3_cancel_flag_checked_between_steps(self):
        """A cancel flag set between steps aborts subsequent steps without executing them."""
        plan_data = {
            "title": "MultiStepPlan",
            "steps": ["NOTE: Step 1 | Run", "NOTE: Step 2 | Run", "NOTE: Step 3 | Run"],
            "cancelled": False,
        }
        executed = []

        def runner(step, *args):
            executed.append(step)
            if "Step 1" in step:
                # Cancel plan after step 1
                plan_data["cancelled"] = True
            return "OK"

        res = plan_mode.execute_plan_batch(plan_data, cfg=self.cfg, runner=runner)
        self.assertFalse(res.get("ok"))
        self.assertTrue(res.get("cancelled"))
        self.assertEqual(len(executed), 1)
        self.assertIn("Step 1", executed[0])
        self.assertEqual(len(res.get("completed")), 1)

    def test_item3_telegram_stopplan_allowlist_and_execution(self):
        """Telegram /stopplan enforces user allowlist and cancels active plan."""
        conv_id = "telegram:12345"
        gw = telegram_gateway.TelegramGateway(self.cfg)
        gw.send_message = MagicMock()

        # Seed an active plan
        with server.ACTIVE_PLANS_LOCK:
            server.ACTIVE_PLANS["p_tg_1"] = {
                "plan_id": "p_tg_1",
                "title": "TgPlan",
                "conv_id": conv_id,
                "status": "running",
                "cancelled": False,
            }

        # 1. Unauthorized user 99999 is rejected
        gw.process_update({
            "update_id": 101,
            "message": {
                "message_id": 1,
                "date": int(time.time()),
                "chat": {"id": 12345, "type": "private"},
                "from": {"id": 99999, "is_bot": False},
                "text": "/stopplan",
            }
        })
        with server.ACTIVE_PLANS_LOCK:
            self.assertFalse(server.ACTIVE_PLANS["p_tg_1"]["cancelled"])

        # 2. Authorized user 12345 cancels the plan
        gw.process_update({
            "update_id": 102,
            "message": {
                "message_id": 2,
                "date": int(time.time()),
                "chat": {"id": 12345, "type": "private"},
                "from": {"id": 12345, "is_bot": False},
                "text": "/stopplan",
            }
        })
        with server.ACTIVE_PLANS_LOCK:
            self.assertTrue(server.ACTIVE_PLANS["p_tg_1"]["cancelled"])

    def test_item3_discord_stopplan_allowlist_and_execution(self):
        """Discord /stopplan enforces user/channel allowlist and cancels active plan."""
        gw = discord_gateway.DiscordGateway(
            bot_token=self.cfg["discord_bot_token"],
            channel_ids=self.cfg["discord_channel_ids"],
            allowed_user_ids=self.cfg["discord_allowed_user_ids"],
        )
        gw.send_message = MagicMock()
        gw.bot_id = "bot_999"

        with server.ACTIVE_PLANS_LOCK:
            server.ACTIVE_PLANS["p_dc_1"] = {
                "plan_id": "p_dc_1",
                "title": "DiscordPlan",
                "conv_id": "discord:ch1",
                "status": "running",
                "cancelled": False,
            }

        # 1. Unauthorized user Eve is ignored
        gw.handle_message(channel_id="ch1", user_id="user_eve", text="/stopplan")
        with server.ACTIVE_PLANS_LOCK:
            self.assertFalse(server.ACTIVE_PLANS["p_dc_1"]["cancelled"])

        # 2. Authorized user Alice cancels plan
        gw.handle_message(channel_id="ch1", user_id="user_alice", text="/stopplan")
        with server.ACTIVE_PLANS_LOCK:
            self.assertTrue(server.ACTIVE_PLANS["p_dc_1"]["cancelled"])


if __name__ == "__main__":
    unittest.main()
