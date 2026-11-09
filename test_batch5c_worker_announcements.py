"""
Regression tests for Batch 5c Items 1 & 2:
- Worker progress announcements via notify callback and plan_paused event
- Plans with 2 gated steps executed and resumed across Telegram, Discord, /api/confirm, and conversational 'yes'
- All resume_plan_execution return values are strictly JSON-serializable (no Thread objects).
"""
import json
import os
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import discord_gateway
import guardian_agent
import plan_mode
import server
import telegram_gateway


class TestBatch5cWorkerAnnouncements(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "confirm_destructive": True,
            "provider": "openai",
            "api_key": "sk-mock-12345",
            "model": "gpt-4o",
            "monthly_budget_usd": 100.0,
            "telegram_bot_token": "mock-tg-token",
            "telegram_allowed_chat_ids": ["12345"],
            "telegram_allowed_user_ids": ["12345"],
            "discord_bot_token": "mock-disc-token",
            "discord_enabled": True,
            "discord_allowed_user_ids": ["u123"],
            "discord_channel_ids": ["c123"],
        }
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()
        with server.ACTIVE_PLANS_LOCK:
            server.ACTIVE_PLANS.clear()
        with server.LOCK:
            server.EVENTS.clear()
            server.HISTORIES["developer"].clear()
        server.CONVERSATION_TAINT.clear()

    def tearDown(self):
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()
        with server.ACTIVE_PLANS_LOCK:
            server.ACTIVE_PLANS.clear()
        with server.LOCK:
            server.EVENTS.clear()
            server.HISTORIES["developer"].clear()
        server.CONVERSATION_TAINT.clear()

    def test_item2_return_values_json_serializable_and_no_thread_object(self):
        """All return values from resume_plan_execution must be JSON-serializable without Thread objects."""
        # 1. Async resumption return dict
        plan_state_async = {
            "title": "Async Test",
            "all_steps": ["NOTE: a | 1", "NOTE: b | 2"],
            "completed": ["NOTE: a | 1"],
            "remaining_steps": ["NOTE: b | 2"],
            "started_at": time.time(),
            "source": "pc",
            "mode": "developer",
            "conv_id": "test:async_json",
        }
        res_async = server.resume_plan_execution(plan_state_async, cfg=self.cfg, async_run=True)
        self.assertNotIn("worker", res_async)
        serialized = json.dumps(res_async)
        loaded = json.loads(serialized)
        self.assertTrue(loaded.get("ok"))
        self.assertTrue(loaded.get("resumed"))
        server.wait_for_plan_worker("test:async_json", timeout=5.0)

        # 2. No remaining steps return
        empty_plan = {"title": "Empty", "all_steps": [], "remaining_steps": []}
        res_empty = server.resume_plan_execution(empty_plan, cfg=self.cfg, async_run=False)
        self.assertNotIn("worker", res_empty if isinstance(res_empty, dict) else {})
        self.assertTrue(json.loads(json.dumps(res_empty)))

    def test_plan_two_gated_steps_telegram(self):
        """A plan with 2 gated steps pauses twice, notifies Telegram at each pause, and completes."""
        tg = telegram_gateway.TelegramGateway(self.cfg)
        tg.send_message = MagicMock(return_value=True)
        tg.send_approval_announcement = MagicMock(return_value=True)

        plan_tag = "DeployTwoSteps\nCMD: echo step1\nCMD: echo step2\nNOTE: Done | all finished"
        res1 = server.run_skill(self.cfg, "PLAN", plan_tag, source="telegram", mode="developer", conv_id="telegram:12345")
        self.assertIsInstance(res1, dict)
        self.assertTrue(res1.get("paused"))
        p1_id = res1["pending_info"]["id"]

        # User approves step 1 via Telegram /allow
        msg1 = {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "chat": {"id": 12345, "type": "private"},
                "from": {"id": 12345, "is_bot": False},
                "text": f"/allow {p1_id}",
            },
        }
        with patch("server.run_skill", return_value="Step 1 Output") as mock_run:
            tg.process_update(msg1)
            server.wait_for_plan_worker("telegram:12345", timeout=5.0)

        # Telegram should have received approval announcement for Step 2!
        self.assertTrue(tg.send_approval_announcement.called)
        # Find the pending action for step 2
        with server.PENDING_LOCK:
            pending_ids = list(server.PENDING_ACTIONS.keys())
        self.assertEqual(len(pending_ids), 1)
        p2_id = pending_ids[0]

        # User approves step 2 via Telegram /allow
        msg2 = {
            "update_id": 2,
            "message": {
                "message_id": 11,
                "chat": {"id": 12345, "type": "private"},
                "from": {"id": 12345, "is_bot": False},
                "text": f"/allow {p2_id}",
            },
        }
        with patch("server.run_skill", return_value="Step 2 Output"):
            tg.process_update(msg2)
            server.wait_for_plan_worker("telegram:12345", timeout=5.0)

        # Telegram should have received completion message
        messages_sent = [call[0][1] for call in tg.send_message.call_args_list]
        self.assertTrue(any("executed successfully" in m or "Action Approved" in m for m in messages_sent))

    def test_plan_two_gated_steps_discord(self):
        """A plan with 2 gated steps pauses twice, notifies Discord at each pause, and completes."""
        disc = discord_gateway.DiscordGateway(
            bot_token="mock-disc-token",
            channel_ids=["c123"],
            allowed_user_ids=["u123"],
            confirm_handler=discord_gateway.handle_remote_confirm,
        )
        disc.send_message = MagicMock(return_value=True)
        disc.send_approval_announcement = MagicMock(return_value=True)

        plan_tag = "DiscordTwoSteps\nCMD: echo disc1\nCMD: echo disc2\nNOTE: Finished | done"
        res1 = server.run_skill(self.cfg, "PLAN", plan_tag, source="discord", mode="developer", conv_id="discord:c123")
        self.assertIsInstance(res1, dict)
        self.assertTrue(res1.get("paused"))
        p1_id = res1["pending_info"]["id"]

        with patch("server.run_skill", return_value="Disc 1 Output"):
            disc.handle_message(
                channel_id="c123",
                user_id="u123",
                text=f"/allow {p1_id}",
                is_bot=False,
                is_dm=False,
            )
            server.wait_for_plan_worker("discord:c123", timeout=5.0)

        self.assertTrue(disc.send_approval_announcement.called)
        with server.PENDING_LOCK:
            pending_ids = list(server.PENDING_ACTIONS.keys())
        self.assertEqual(len(pending_ids), 1)
        p2_id = pending_ids[0]

        with patch("server.run_skill", return_value="Disc 2 Output"):
            disc.handle_message(
                channel_id="c123",
                user_id="u123",
                text=f"/allow {p2_id}",
                is_bot=False,
                is_dm=False,
            )
            server.wait_for_plan_worker("discord:c123", timeout=5.0)

        messages_sent = [call[0][1] for call in disc.send_message.call_args_list]
        self.assertTrue(any("executed successfully" in m or "Action allowed" in m for m in messages_sent))

    def test_plan_two_gated_steps_conversational_yes(self):
        """Conversational 'yes' approves step 1, plan pauses at step 2, second 'yes' finishes plan."""
        plan_tag = "[[PLAN: ConvTwoSteps | CMD: echo conv1 | CMD: echo conv2 | NOTE: ConvDone | ok]]"
        with patch("server.call_llm", return_value=plan_tag):
            r1 = server.chat("run conv steps", source="pc", mode="developer")
            self.assertIsNotNone(r1.get("pending"))
            self.assertEqual(r1.get("pending", {}).get("action"), "CMD")

        with server.PENDING_LOCK:
            p1_id = list(server.PENDING_ACTIONS.keys())[0]

        # Say 'yes' to approve step 1
        with patch("server.run_skill", return_value="Conv1 OK"):
            r2 = server.chat("yes", source="pc", mode="developer")
            server.wait_for_plan_worker("pc:developer", timeout=5.0)

        # Plan paused again at step 2
        with server.PENDING_LOCK:
            self.assertEqual(len(server.PENDING_ACTIONS), 1)
            p2_id = list(server.PENDING_ACTIONS.keys())[0]
            self.assertNotEqual(p1_id, p2_id)

        # Say 'yes' to approve step 2
        with patch("server.run_skill", return_value="Conv2 OK"):
            r3 = server.chat("yes", source="pc", mode="developer")
            server.wait_for_plan_worker("pc:developer", timeout=5.0)

        with server.PENDING_LOCK:
            self.assertEqual(len(server.PENDING_ACTIONS), 0)

        with server.LOCK:
            types = [e.get("type") for e in server.EVENTS]
        self.assertIn("plan_completed", types)


    def test_plan_two_gated_steps_api_confirm(self):
        """A plan with 2 gated steps pauses twice and completes via /api/confirm resolution."""
        plan_tag = "ApiConfirmTwoSteps\nCMD: echo api1\nCMD: echo api2\nNOTE: Finished | ok"
        res1 = server.run_skill(self.cfg, "PLAN", plan_tag, source="pc", mode="developer", conv_id="pc:developer")
        self.assertIsInstance(res1, dict)
        self.assertTrue(res1.get("paused"))
        p1_id = res1["pending_info"]["id"]

        # Approve step 1 via confirm resolution
        with server.PENDING_LOCK:
            pending1 = server.PENDING_ACTIONS.pop(p1_id)
        with patch("server.run_skill", return_value="API1 Output"):
            res_resume1 = server.resume_plan_execution(pending1["plan_state"], last_result="API1 Output", cfg=self.cfg)
            server.wait_for_plan_worker("pc:developer", timeout=5.0)

        # Plan should now have paused at step 2
        with server.PENDING_LOCK:
            self.assertEqual(len(server.PENDING_ACTIONS), 1)
            p2_id = list(server.PENDING_ACTIONS.keys())[0]
            self.assertNotEqual(p1_id, p2_id)
            pending2 = server.PENDING_ACTIONS.pop(p2_id)

        # Check plan_paused event
        with server.LOCK:
            pause_events = [e for e in server.EVENTS if e.get("type") == "plan_paused"]
        self.assertTrue(len(pause_events) >= 1)
        self.assertEqual(pause_events[-1].get("pending_id"), p2_id)

        # Approve step 2 via confirm resolution
        with patch("server.run_skill", return_value="API2 Output"):
            res_resume2 = server.resume_plan_execution(pending2["plan_state"], last_result="API2 Output", cfg=self.cfg)
            server.wait_for_plan_worker("pc:developer", timeout=5.0)

        with server.LOCK:
            completed_events = [e for e in server.EVENTS if e.get("type") == "plan_completed"]
        self.assertTrue(len(completed_events) >= 1)
        self.assertEqual(completed_events[-1].get("title"), "ApiConfirmTwoSteps")


if __name__ == "__main__":
    unittest.main()
