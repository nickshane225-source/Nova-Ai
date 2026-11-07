"""
Unit tests for Task 5: Telegram Remote Gateway (telegram_gateway.py).
Zero third-party pip dependencies - Python standard library only.
"""
import json
import unittest
from unittest.mock import MagicMock, patch

import telegram_gateway


class TestTelegramGateway(unittest.TestCase):
    def test_unauthorized_chat_id_rejected(self):
        cfg = {
            "telegram_bot_token": "fake_token",
            "telegram_allowed_chat_ids": ["12345678"]
        }
        gw = telegram_gateway.TelegramGateway(cfg, chat_callback=MagicMock())

        # An incoming update from an attacker/unauthorized chat ID "999999"
        update = {
            "update_id": 1,
            "message": {
                "message_id": 101,
                "chat": {"id": 999999},
                "text": "rm -rf /",
            }
        }
        handled = gw.process_update(update)
        self.assertFalse(handled)
        gw.chat_callback.assert_not_called()

    def test_authorized_chat_id_invokes_callback(self):
        cfg = {
            "telegram_bot_token": "fake_token",
            "telegram_allowed_chat_ids": ["12345678"]
        }
        mock_callback = MagicMock(return_value="Nova says hello back!")
        gw = telegram_gateway.TelegramGateway(cfg, chat_callback=mock_callback)

        update = {
            "update_id": 2,
            "message": {
                "message_id": 102,
                "chat": {"id": 12345678},
                "text": "What is the weather?",
            }
        }
        with patch.object(gw, "send_message") as mock_send:
            handled = gw.process_update(update)
            self.assertTrue(handled)
            mock_callback.assert_called_once_with("What is the weather?", source="telegram")
            mock_send.assert_called_once()
            self.assertEqual(mock_send.call_args[0][0], 12345678)
            self.assertIn("Nova says hello back!", mock_send.call_args[0][1])

    def test_remote_allow_confirmation_command(self):
        cfg = {
            "telegram_bot_token": "fake_token",
            "telegram_allowed_chat_ids": ["12345678"]
        }
        gw = telegram_gateway.TelegramGateway(cfg)

        update = {
            "update_id": 3,
            "message": {
                "message_id": 103,
                "chat": {"id": 12345678},
                "text": "/allow abcdef12",
            }
        }
        with patch("telegram_gateway.handle_remote_confirm", return_value={"ok": True, "result": "Done"}) as mock_confirm:
            with patch.object(gw, "send_message") as mock_send:
                handled = gw.process_update(update)
                self.assertTrue(handled)
                mock_confirm.assert_called_once_with("abcdef12", approve=True)
                mock_send.assert_called_once()
                self.assertIn("Approved", mock_send.call_args[0][1])

    def test_remote_deny_confirmation_command(self):
        cfg = {
            "telegram_bot_token": "fake_token",
            "telegram_allowed_chat_ids": ["12345678"]
        }
        gw = telegram_gateway.TelegramGateway(cfg)

        update = {
            "update_id": 4,
            "message": {
                "message_id": 104,
                "chat": {"id": 12345678},
                "text": "/deny abcdef12",
            }
        }
        with patch("telegram_gateway.handle_remote_confirm", return_value={"ok": True, "action": "CMD"}) as mock_confirm:
            with patch.object(gw, "send_message") as mock_send:
                handled = gw.process_update(update)
                self.assertTrue(handled)
                mock_confirm.assert_called_once_with("abcdef12", approve=False)
                mock_send.assert_called_once()
                self.assertIn("Denied", mock_send.call_args[0][1])


if __name__ == "__main__":
    unittest.main()
