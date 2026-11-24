import unittest
from unittest.mock import patch
import tempfile
import json
from pathlib import Path
import server
import audit_logger

class TestItem5SecurityAndMaskingVerification(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.fake_data = self.tmp_path / "data"
        self.fake_data.mkdir(parents=True, exist_ok=True)
        self.fake_ws = self.tmp_path / "workspace"
        self.fake_ws.mkdir(parents=True, exist_ok=True)

        self.orig_root = server.ROOT
        self.orig_data = server.DATA
        self.orig_ws = server.WORKSPACE
        self.orig_config_file = server.CONFIG_FILE
        self.orig_memory_file = server.MEMORY_FILE
        self.orig_audit_file = audit_logger._AUDIT_FILE

        server.ROOT = self.tmp_path
        server.DATA = self.fake_data
        server.WORKSPACE = self.fake_ws
        server.CONFIG_FILE = self.fake_data / "config.json"
        server.MEMORY_FILE = self.fake_data / "memory.json"
        audit_logger._AUDIT_FILE = self.fake_data / "audit.jsonl"

        cfg = dict(server.DEFAULT_CONFIG)
        cfg["api_key"] = ""
        cfg["encrypt_keys"] = False
        server.save_config(cfg)

    def tearDown(self):
        server.ROOT = self.orig_root
        server.DATA = self.orig_data
        server.WORKSPACE = self.orig_ws
        server.CONFIG_FILE = self.orig_config_file
        server.MEMORY_FILE = self.orig_memory_file
        audit_logger._AUDIT_FILE = self.orig_audit_file
        self.tmp_dir.cleanup()

    def test_whitespace_padded_key_is_trimmed(self):
        # 1. Padded with whitespace, newlines, and single quotes
        padded_key = "  \n\t 'sk-sampleCleanKey1234567890' \r\n  "
        valid, cleaned, err = server.sanitize_and_validate_api_key(padded_key)
        self.assertTrue(valid)
        self.assertEqual(cleaned, "sk-sampleCleanKey1234567890")

        # 2. Padded with double quotes
        quoted_key = ' \n "AQ.sampleCleanKey9876543210" \t '
        valid_q, cleaned_q, _ = server.sanitize_and_validate_api_key(quoted_key)
        self.assertTrue(valid_q)
        self.assertEqual(cleaned_q, "AQ.sampleCleanKey9876543210")

        # 3. Keys containing internal spaces are rejected
        spaced_key = "sk-invalid key with inner spaces"
        valid_s, cleaned_s, err_s = server.sanitize_and_validate_api_key(spaced_key)
        self.assertFalse(valid_s)
        self.assertIn("cannot contain spaces", err_s)

    def test_mocked_401_shows_status_and_not_saved(self):
        err = server.LLMError("API error 401: Unauthorized request")
        err.status_code = 401
        with patch("server.http_post", side_effect=err):
            res = server.test_llm_connection(
                provider="anthropic",
                api_key="sk-ant-testKeyMock401987654321",
                model="claude-3-5-sonnet-latest"
            )
            self.assertFalse(res["ok"])
            self.assertEqual(res["status_code"], 401)
            self.assertIn("401", res["message"])
            self.assertIn("Key NOT saved", res["message"])

            # Verify that config was NOT modified
            saved_cfg = server.get_config()
            self.assertEqual(saved_cfg.get("api_key", ""), "")

    def test_no_key_fragment_appears_in_response_or_log(self):
        secret_key = "AQ." + "MockFakeMaskingKey" + "1234567890"
        err = server.LLMError(f"API error 401: Invalid token {secret_key}")
        err.status_code = 401

        with patch("server.http_post", side_effect=err):
            # Test connection call
            res = server.test_llm_connection(
                provider="gemini",
                api_key=secret_key,
                model="gemini-2.5-flash"
            )
            resp_str = json.dumps(res)
            self.assertNotIn(secret_key, resp_str)
            self.assertNotIn("MockFakeMaskingKey", resp_str)

            # Chat call
            cfg = server.get_config()
            cfg["api_key"] = secret_key
            cfg["provider"] = "gemini"
            server.save_config(cfg)

            chat_res = server.chat("Test prompt for key leak", mode="developer", source="pc")
            chat_reply = chat_res.get("reply", "")
            self.assertNotIn(secret_key, chat_reply)
            self.assertNotIn("SecretPatternKey", chat_reply)

            # Audit log check
            audit_path = self.fake_data / "audit.jsonl"
            audit_logger.log_audit_event(
                channel="pc",
                tool="LLM_TEST",
                preview=f"Testing authorization with token {secret_key}",
                guardian_verdict="SAFE",
                status="EXECUTED",
                cfg=cfg,
            )
            if audit_path.exists():
                audit_content = audit_path.read_text(encoding="utf-8")
                self.assertNotIn(secret_key, audit_content)
                self.assertNotIn("SecretPatternKey", audit_content)

if __name__ == "__main__":
    unittest.main()
