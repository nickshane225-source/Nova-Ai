#!/usr/bin/env python3
"""
Unit tests for Nova AI Discord Remote Gateway (discord_gateway.py)
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import discord_gateway


class TestDiscordGateway(unittest.TestCase):
    def setUp(self):
        self.mock_chat = MagicMock(return_value={"reply": "Mocked AI Response"})
        self.mock_confirm = MagicMock(return_value={"ok": True, "message": "Action approved"})
        self.gateway = discord_gateway.DiscordGateway(
            bot_token="test_bot_token",
            channel_ids=["channel_123"],
            allowed_user_ids=["user_admin"],
            chat_handler=self.mock_chat,
            confirm_handler=self.mock_confirm,
            poll_interval=1.0,
        )
        self.gateway.bot_id = "bot_999"

    def test_ignore_own_or_bot_messages(self):
        # Bot's own message
        with patch.object(self.gateway, "_api_request") as mock_req:
            mock_req.return_value = [
                {
                    "id": "1001",
                    "content": "Hello",
                    "author": {"id": "bot_999", "bot": True},
                }
            ]
            self.gateway.poll_channel("channel_123")
            self.mock_chat.assert_not_called()

    def test_unauthorized_user_ignored(self):
        with patch.object(self.gateway, "_api_request") as mock_req:
            mock_req.return_value = [
                {
                    "id": "1002",
                    "content": "Delete database",
                    "author": {"id": "user_intruder", "bot": False},
                }
            ]
            self.gateway.poll_channel("channel_123")
            self.mock_chat.assert_not_called()

    def test_authorized_user_chat_execution(self):
        with patch.object(self.gateway, "_api_request") as mock_req:
            mock_req.return_value = [
                {
                    "id": "1003",
                    "content": "What is the weather today?",
                    "author": {"id": "user_admin", "bot": False},
                }
            ]
            with patch.object(self.gateway, "send_message") as mock_send:
                self.gateway.poll_channel("channel_123")
                self.mock_chat.assert_called_once_with("What is the weather today?", "discord")
                mock_send.assert_called_once_with("channel_123", "Mocked AI Response")

    def test_approval_commands(self):
        self.mock_confirm.return_value = {"ok": True, "action": "CMD", "command": "echo test_discord_cmd", "result": "Success"}
        with patch.object(self.gateway, "send_message") as mock_send:
            self.gateway.handle_message("channel_123", "user_admin", "/allow token_xyz")
            self.mock_confirm.assert_called_once_with("token_xyz", True)
            sent = mock_send.call_args[0][1]
            self.assertIn("Action allowed: CMD", sent)
            self.assertIn("echo test_discord_cmd", sent)
            self.assertIn("Success", sent)

    def test_pending_action_includes_command_in_approval_prompt(self):
        self.mock_chat.return_value = {
            "reply": "Need approval",
            "pending": {
                "id": "act_dc_99",
                "prompt": "Run shell script?",
                "command": "dir /s /b",
            }
        }
        with patch.object(self.gateway, "send_message") as mock_send:
            self.gateway.handle_message("channel_123", "user_admin", "List files")
            sent = mock_send.call_args[0][1]
            self.assertIn("Action Requires Approval", sent)
            self.assertIn("dir /s /b", sent)
            self.assertIn("Command:", sent)

    def test_approval_command_failure_reporting(self):
        self.mock_confirm.return_value = {"ok": False, "error": "Token expired"}
        with patch.object(self.gateway, "send_message") as mock_send:
            self.gateway.handle_message("channel_123", "user_admin", "/allow bad_token")
            mock_send.assert_called_once_with("channel_123", "❌ Failed to allow: Token expired")

    def test_approval_missing_argument(self):
        with patch.object(self.gateway, "send_message") as mock_send:
            self.gateway.handle_message("channel_123", "user_admin", "/allow")
            mock_send.assert_called_once_with("channel_123", "Usage: /allow <action_id>")

    def test_message_chunking_on_send(self):
        long_text = "A" * 3000
        with patch.object(self.gateway, "_api_request") as mock_req:
            mock_req.return_value = {"id": "new_msg"}
            res = self.gateway.send_message("channel_123", long_text)
            self.assertTrue(res)
            # Should have called _api_request twice because length > 1950
            self.assertEqual(mock_req.call_count, 2)


if __name__ == "__main__":
    unittest.main()
