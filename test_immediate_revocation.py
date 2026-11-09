"""
test_immediate_revocation.py - Verify live revocation without restart for:
1. telegram_allowed_chat_ids
2. telegram_allowed_user_ids
3. discord allowlists (discord_allowed_user_ids & discord_channel_ids)
4. remote device revocation
"""

import unittest
import secrets
from unittest.mock import MagicMock, patch
import server
from telegram_gateway import TelegramGateway, ACTIVE_TELEGRAM_GATEWAYS
from discord_gateway import DiscordGateway, ACTIVE_DISCORD_GATEWAYS


class TestImmediateRevocation(unittest.TestCase):

    def setUp(self):
        ACTIVE_TELEGRAM_GATEWAYS.clear()
        ACTIVE_DISCORD_GATEWAYS.clear()
        self.orig_config = server.get_config()

    def tearDown(self):
        ACTIVE_TELEGRAM_GATEWAYS.clear()
        ACTIVE_DISCORD_GATEWAYS.clear()
        server.save_config(self.orig_config)

    def test_01_telegram_allowed_chat_ids_revocation(self):
        """Changes to telegram_allowed_chat_ids take effect immediately on config save without restart."""
        server.save_config({
            "telegram_allowed_chat_ids": ["111222"],
            "telegram_allowed_user_ids": [],
            "telegram_allow_groups": False,
        })
        tg = TelegramGateway(cfg=server.get_config())

        # Initially authorized in private chat
        self.assertTrue(tg.is_authorized(chat_id="111222", chat_type="private"))

        # Revoke chat_id 111222 by saving updated config
        server.save_config({
            "telegram_allowed_chat_ids": ["999888"],
            "telegram_allowed_user_ids": [],
            "telegram_allow_groups": False,
        })
        self.assertFalse(tg.is_authorized(chat_id="111222", chat_type="private"))
        self.assertTrue(tg.is_authorized(chat_id="999888", chat_type="private"))

        # Completely empty the allowlist -> all denied
        server.save_config({
            "telegram_allowed_chat_ids": [],
            "telegram_allowed_user_ids": [],
            "telegram_allow_groups": False,
        })
        self.assertFalse(tg.is_authorized(chat_id="999888", chat_type="private"))

    def test_02_telegram_allowed_user_ids_revocation(self):
        """Changes to telegram_allowed_user_ids take effect immediately on config save without restart."""
        server.save_config({
            "telegram_allowed_chat_ids": ["100"],
            "telegram_allowed_user_ids": ["555"],
            "telegram_allow_groups": False,
        })
        tg = TelegramGateway(cfg=server.get_config())

        # Initially authorized
        self.assertTrue(tg.is_authorized(chat_id="100", user_id="555", chat_type="private"))

        # Revoke user 555 by saving updated config
        server.save_config({
            "telegram_allowed_chat_ids": ["100"],
            "telegram_allowed_user_ids": ["666"],
            "telegram_allow_groups": False,
        })
        self.assertFalse(tg.is_authorized(chat_id="100", user_id="555", chat_type="private"))
        self.assertTrue(tg.is_authorized(chat_id="100", user_id="666", chat_type="private"))

        # Remove all allowed users -> denied
        server.save_config({
            "telegram_allowed_chat_ids": ["100"],
            "telegram_allowed_user_ids": [],
            "telegram_allow_groups": False,
        })
        self.assertFalse(tg.is_authorized(chat_id="100", user_id="666", chat_type="private"))

    def test_03_discord_allowlists_revocation(self):
        """Changes to discord_allowed_user_ids and discord_channel_ids take effect immediately on config save without restart."""
        server.save_config({
            "discord_allowed_user_ids": ["12345"],
            "discord_channel_ids": ["chan_1"],
        })
        dg = DiscordGateway(bot_token="fake", channel_ids=["chan_1"], allowed_user_ids=["12345"])

        # Initially authorized
        self.assertTrue(dg.is_authorized(user_id="12345", channel_id="chan_1"))

        # Revoke user 12345 by saving updated config
        server.save_config({
            "discord_allowed_user_ids": ["54321"],
            "discord_channel_ids": ["chan_1"],
        })
        self.assertFalse(dg.is_authorized(user_id="12345", channel_id="chan_1"))
        self.assertTrue(dg.is_authorized(user_id="54321", channel_id="chan_1"))

        # Channel changed in live config
        server.save_config({
            "discord_allowed_user_ids": ["54321"],
            "discord_channel_ids": ["chan_2"],
        })
        self.assertFalse(dg.is_authorized(user_id="54321", channel_id="chan_1"))
        self.assertTrue(dg.is_authorized(user_id="54321", channel_id="chan_2"))

        # Revoke all users -> denied
        server.save_config({
            "discord_allowed_user_ids": [],
            "discord_channel_ids": ["chan_2"],
        })
        self.assertFalse(dg.is_authorized(user_id="54321", channel_id="chan_2"))

    def test_04_remote_device_revocation(self):
        """Remote device revocation immediately revokes access without restart."""
        device_id = "phone-abc-123"
        device_token = secrets.token_hex(32)

        server.save_config({"remote_enabled": True})
        with server.PAIRED_DEVICES_LOCK:
            server.PAIRED_DEVICES[device_id] = {
                "id": device_id,
                "name": "Test Phone",
                "token": device_token,
                "paired_at": 1000.0,
                "last_seen": 1000.0,
            }

        # Mock RemoteHandler instance to test _auth
        handler = server.RemoteHandler.__new__(server.RemoteHandler)
        handler.client_address = ("192.168.1.50", 12345)
        handler.headers = {"Authorization": f"Bearer {device_token}"}
        handler._send = MagicMock()

        # Initially authenticated
        self.assertTrue(handler._auth())

        # Revoke device via PAIRED_DEVICES.pop (as done by /api/remote/devices/revoke)
        with server.PAIRED_DEVICES_LOCK:
            server.PAIRED_DEVICES.pop(device_id, None)

        # Immediate re-auth attempt MUST fail with 401
        self.assertFalse(handler._auth())
        handler._send.assert_called_with(401, {"error": "Not paired. Scan the QR code on your PC again."})


if __name__ == "__main__":
    unittest.main()
