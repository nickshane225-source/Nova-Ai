"""
test_immediate_revocation.py - Verify live revocation without restart for:
1. telegram_allowed_chat_ids
2. telegram_allowed_user_ids
3. discord allowlists (discord_allowed_user_ids & discord_channel_ids)
4. remote device revocation
"""

import json
import tempfile
import threading
import unittest
import urllib.request
import secrets
from pathlib import Path
from unittest.mock import MagicMock, patch
import server
from telegram_gateway import TelegramGateway, ACTIVE_TELEGRAM_GATEWAYS
from discord_gateway import DiscordGateway, ACTIVE_DISCORD_GATEWAYS


class TestImmediateRevocation(unittest.TestCase):

    def setUp(self):
        ACTIVE_TELEGRAM_GATEWAYS.clear()
        ACTIVE_DISCORD_GATEWAYS.clear()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.orig_cfg_file = server.CONFIG_FILE
        server.CONFIG_FILE = Path(self.tmpdir.name) / "config.json"
        server.save_config(dict(server.DEFAULT_CONFIG))

    def tearDown(self):
        ACTIVE_TELEGRAM_GATEWAYS.clear()
        ACTIVE_DISCORD_GATEWAYS.clear()
        server.CONFIG_FILE = self.orig_cfg_file
        self.tmpdir.cleanup()

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

    def test_05_real_api_config_route_revokes_user_without_restart(self):
        """Changing allowlist via real POST /api/config immediately refuses next message from removed user."""
        cfg = server.get_config()
        cfg["telegram_allowed_chat_ids"] = ["chat_1"]
        cfg["telegram_allowed_user_ids"] = ["user_keep", "user_remove"]
        cfg["discord_allowed_user_ids"] = ["dc_keep", "dc_remove"]
        cfg["discord_channel_ids"] = ["chan_1"]
        server.save_config(cfg)

        tg_chat = MagicMock(return_value={"reply": "ok"})
        tg = TelegramGateway(cfg=server.get_config(), chat_callback=tg_chat)
        dc_chat = MagicMock(return_value={"reply": "ok"})
        dg = DiscordGateway(
            bot_token="fake_bot_token",
            channel_ids=["chan_1"],
            allowed_user_ids=["dc_keep", "dc_remove"],
            chat_handler=dc_chat,
        )

        self.assertTrue(tg.is_authorized(chat_id="chat_1", user_id="user_remove", chat_type="private"))
        self.assertTrue(dg.is_authorized(user_id="dc_remove", channel_id="chan_1"))

        srv = server.SilentThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            headers = {
                "Content-Type": "application/json",
                "Cookie": f"nova_session={server.SESSION_TOKEN}",
                "X-Nova-Token": server.API_SESSION_TOKEN,
                "Origin": f"http://127.0.0.1:{port}",
            }
            payload = {
                "telegram_allowed_user_ids": ["user_keep"],
                "discord_allowed_user_ids": ["dc_keep"],
            }
            # Step 1: /api/config requests confirmation token for sensitive allowlist change
            req1 = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/config",
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req1, timeout=5) as r1:
                d1 = json.loads(r1.read().decode("utf-8"))
            self.assertTrue(d1.get("need_confirm"))
            tok = d1["token"]

            # Step 2: Confirm via real /api/config
            req2 = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/config",
                data=json.dumps({**payload, "confirm_token": tok}).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req2, timeout=5) as r2:
                self.assertEqual(r2.status, 200)

            # Next message from removed users MUST be refused immediately without restart
            tg.process_update({
                "update_id": 1001,
                "message": {
                    "chat": {"id": "chat_1", "type": "private"},
                    "from": {"id": "user_remove"},
                    "text": "hello after revoke",
                },
            })
            tg_chat.assert_not_called()

            dg.process_raw_message({
                "id": "m1",
                "channel_id": "chan_1",
                "author": {"id": "dc_remove", "bot": False},
                "content": "hello after revoke",
            })
            dc_chat.assert_not_called()

            # Kept users still authorized
            self.assertTrue(tg.is_authorized(chat_id="chat_1", user_id="user_keep", chat_type="private"))
            self.assertTrue(dg.is_authorized(user_id="dc_keep", channel_id="chan_1"))
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
