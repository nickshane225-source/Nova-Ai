import unittest
import time
from unittest.mock import patch

import server
import audit_logger


class TestSecretMaskingAndLockout(unittest.TestCase):
    def setUp(self):
        server.FAILS.clear()

    def tearDown(self):
        server.FAILS.clear()

    def test_mask_secrets_skips_shorter_than_8_chars(self):
        cfg = {
            "api_key": "short",         # 5 chars -> should NOT mask by value
            "telegram_bot_token": "1234567",  # 7 chars -> should NOT mask by value
            "discord_bot_token": "secretDiscordToken123456",  # >= 8 chars -> MUST mask
        }

        sample_text = "The word short and number 1234567 and secretDiscordToken123456 were found."
        masked_server = server.mask_secrets(sample_text, cfg=cfg)

        self.assertIn("short", masked_server)
        self.assertIn("1234567", masked_server)
        self.assertNotIn("secretDiscordToken123456", masked_server)
        self.assertIn("secr****", masked_server)

        # Audit logger mask_secrets
        masked_audit = audit_logger.mask_secrets(sample_text, cfg=cfg)
        self.assertIn("short", masked_audit)
        self.assertIn("1234567", masked_audit)
        self.assertNotIn("secretDiscordToken123456", masked_audit)
        self.assertIn("[MASKED_SECRET]", masked_audit)

    def test_pattern_masking_still_active_for_pattern_keys(self):
        sample_text = "Here is an Anthropic key: sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890"
        masked = server.mask_secrets(sample_text, cfg={})
        self.assertNotIn("sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890", masked)
        self.assertIn("sk-ant-****", masked)

    def test_remote_lockout_8_failures_9th_locked_out(self):
        class MockRemoteRequest(server.RemoteHandler):
            def __init__(self, ip="192.168.1.100", headers=None):
                self.client_address = (ip, 12345)
                self.headers = headers or {"X-Nova-Token": "wrong-token-value"}
                self.path = "/api/remote/info"
                self.status = None
                self.data = None

            def _send(self, status, data, ctype="application/json"):
                self.status = status
                self.data = data

        with patch("server.get_config", return_value={"remote_enabled": True, "remote_token": "valid_real_remote_token_32_chars"}):
            req = MockRemoteRequest()

            # First 8 attempts should return 401
            for i in range(8):
                ok = req._auth()
                self.assertFalse(ok)
                self.assertEqual(req.status, 401, f"Attempt {i+1} should be 401")

            # 9th attempt should be locked out with 429
            ok = req._auth()
            self.assertFalse(ok)
            self.assertEqual(req.status, 429)
            self.assertIn("15 minutes", req.data.get("error", ""))


if __name__ == "__main__":
    unittest.main()
