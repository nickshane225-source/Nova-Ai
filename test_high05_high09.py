import unittest
from unittest.mock import MagicMock
import pathlib

import telegram_gateway
import discord_gateway

class TestHigh05AndHigh09(unittest.TestCase):
    def test_high05_no_duplicate_warning_in_gateways(self):
        tg = telegram_gateway.TelegramGateway(cfg={"telegram_bot_token": "fake", "telegram_allowed_user_ids": ["123"]})
        tg.send_message = MagicMock()

        pending = {
            "id": "pend123",
            "prompt": "Run this command",
            "command": "calc.exe \u200B", # Zero-width space
        }

        tg.send_approval_announcement(12345, pending)
        tg.send_message.assert_called_once()
        msg = tg.send_message.call_args[0][1]

        # Ensure warning banner is present, and warning count is not duplicated
        self.assertIn("SECURITY WARNING", msg)
        self.assertNotIn("Warning: Command contains hidden or invisible characters.", msg)

        # Now test DiscordGateway
        dg = discord_gateway.DiscordGateway(bot_token="fake", channel_ids=["chan1"])
        dg.send_message = MagicMock()
        dg.send_approval_announcement("chan1", pending)
        dg.send_message.assert_called_once()
        d_msg = dg.send_message.call_args[0][1]
        self.assertIn("SECURITY WARNING", d_msg)
        self.assertNotIn("Warning: Command contains hidden or invisible characters.", d_msg)

    def test_high09_second_brain_taint_badge_in_app_js(self):
        app_js = pathlib.Path("web/app.js").read_text(encoding="utf-8")
        # Ensure n.tainted badge appears in stored notes rendering
        self.assertIn("${n.tainted ? ' <span style=\"color:#ff6b6b;font-size:10px;margin-left:6px;\">[untrusted source]</span>' : ''}", app_js)
        # Count occurrences: once in stored notes list, once in search notes list
        badge_count = app_js.count("[untrusted source]")
        # 1 in memory panel, 2 in brain panel
        self.assertGreaterEqual(badge_count, 3)

if __name__ == "__main__":
    unittest.main()
