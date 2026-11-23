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
        self.assertIn("[REDACTED:key]", masked_server)

        # Audit logger mask_secrets
        masked_audit = audit_logger.mask_secrets(sample_text, cfg=cfg)
        self.assertIn("short", masked_audit)
        self.assertIn("1234567", masked_audit)
        self.assertNotIn("secretDiscordToken123456", masked_audit)
        self.assertIn("[REDACTED:key]", masked_audit)

    def test_pattern_masking_still_active_for_pattern_keys(self):
        sample_text = "Here is an Anthropic key: sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890"
        masked = server.mask_secrets(sample_text, cfg={})
        self.assertNotIn("sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890", masked)
        self.assertIn("[REDACTED:key]", masked)

    def test_mask_secrets_8_12_40_char_secrets_no_partial_leakage(self):
        """
        Item 3 Requirement:
        - Test with 8-, 12- and 40-character secrets.
        - No value may ever be partially shown (no prefix or suffix characters).
        - Test across both server.mask_secrets and audit_logger.mask_secrets.
        """
        sec_8 = "Ab1!cDe2"                             # 8 chars
        sec_12 = "K9#mP2$xY7&q"                         # 12 chars
        sec_40 = "1234567890abcdef1234567890abcdef12345678"  # 40 chars

        cfg = {
            "api_key": sec_8,
            "telegram_bot_token": sec_12,
            "discord_bot_token": sec_40,
        }

        raw_text = f"API={sec_8} and Bot={sec_12} and Discord={sec_40}"

        for name, mask_fn in [("server", server.mask_secrets), ("audit_logger", audit_logger.mask_secrets)]:
            masked = mask_fn(raw_text, cfg=cfg)

            # None of the secrets may appear in the output
            self.assertNotIn(sec_8, masked, f"Failed for {name} with 8-char secret")
            self.assertNotIn(sec_12, masked, f"Failed for {name} with 12-char secret")
            self.assertNotIn(sec_40, masked, f"Failed for {name} with 40-char secret")

            # Check that no prefix fragments (first 2, 4 chars) appear anywhere in connection to the redaction
            self.assertNotIn("Ab1!", masked)
            self.assertNotIn("K9#m", masked)
            self.assertNotIn("12345678", masked)

            # Fixed redaction token must be present
            self.assertIn("[REDACTED:key]", masked)
            self.assertEqual(masked.count("[REDACTED:key]"), 3)

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

    def test_valid_device_on_different_ip_not_locked_out_by_other_ip_failures(self):
        """
        Item 6: Lockout Scoping
        - Attacker IP (192.168.1.99) sends 8 failures and is locked out on the 9th attempt.
        - Legitimate device on distinct IP (192.168.1.50) with valid token is NOT locked out (returns 200).
        """
        valid_token = "valid_real_remote_token_32_chars"

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

        with patch("server.get_config", return_value={"remote_enabled": True, "remote_token": valid_token}):
            # Attacker on IP 192.168.1.99 fails 8 times
            attacker_req = MockRemoteRequest(ip="192.168.1.99", headers={"X-Nova-Token": "bad-pass"})
            for i in range(8):
                ok = attacker_req._auth()
                self.assertFalse(ok)
                self.assertEqual(attacker_req.status, 401)

            # 9th attempt from attacker is locked out (429)
            ok = attacker_req._auth()
            self.assertFalse(ok)
            self.assertEqual(attacker_req.status, 429)

            # Legitimate device on IP 192.168.1.50 with valid token
            valid_req = MockRemoteRequest(ip="192.168.1.50", headers={"X-Nova-Token": valid_token})
            ok_valid = valid_req._auth()
            self.assertTrue(ok_valid, "Valid device on distinct IP must NOT be locked out by attacker IP failures")


if __name__ == "__main__":
    unittest.main()
