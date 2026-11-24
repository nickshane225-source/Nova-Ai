import unittest
import tempfile
import json
from pathlib import Path
import server

class TestItem3RequestSummary(unittest.TestCase):
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

        server.ROOT = self.tmp_path
        server.DATA = self.fake_data
        server.WORKSPACE = self.fake_ws
        server.CONFIG_FILE = self.fake_data / "config.json"
        server.MEMORY_FILE = self.fake_data / "memory.json"

        cfg = dict(server.DEFAULT_CONFIG)
        cfg["api_key"] = ""
        server.save_config(cfg)

    def tearDown(self):
        server.ROOT = self.orig_root
        server.DATA = self.orig_data
        server.WORKSPACE = self.orig_ws
        server.CONFIG_FILE = self.orig_config_file
        server.MEMORY_FILE = self.orig_memory_file
        self.tmp_dir.cleanup()

    def test_request_summary_metadata_and_zero_key_characters_leak(self):
        secret_key = "AQ.Ab8RN6LSecretPatternForSummaryCheck9876543210"
        res = server.get_request_summary(
            provider="gemini",
            api_key=secret_key,
            model="gemini-2.5-flash",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai"
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["provider"], "gemini")
        self.assertEqual(res["endpoint_host"], "generativelanguage.googleapis.com")
        self.assertEqual(res["auth_method"], "Bearer")
        self.assertEqual(res["key_length"], len(secret_key))
        self.assertEqual(res["key_format_label"], "AQ.")
        self.assertEqual(res["model"], "gemini-2.5-flash")

        # STRICT INTEGRITY: Verify that no key characters appear anywhere in the output
        dumped = json.dumps(res)
        self.assertNotIn(secret_key, dumped)
        self.assertNotIn("SecretPatternForSummaryCheck", dumped)
        self.assertNotIn(secret_key[3:], dumped)
        self.assertNotIn(secret_key[-12:], dumped)

    def test_request_summary_native_gemini_endpoint_and_x_goog_api_key(self):
        secret_key = "AIzaSyD-fakeNativeKeySecretValue123456789"
        res = server.get_request_summary(
            provider="gemini-native",
            api_key=secret_key,
            model="gemini-2.5-flash"
        )
        self.assertEqual(res["auth_method"], "x-goog-api-key")
        self.assertEqual(res["key_format_label"], "AIza")
        self.assertEqual(res["endpoint_host"], "generativelanguage.googleapis.com")
        self.assertEqual(res["key_length"], len(secret_key))

        dumped = json.dumps(res)
        self.assertNotIn(secret_key, dumped)
        self.assertNotIn("fakeNativeKeySecretValue", dumped)

    def test_request_summary_key_formats_classification(self):
        # 1. sk-ant-
        res_ant = server.get_request_summary("anthropic", "sk-ant-testSecretKey12345")
        self.assertEqual(res_ant["key_format_label"], "sk-ant-")
        self.assertEqual(res_ant["auth_method"], "Bearer or x-api-key")

        # 2. sk-
        res_openai = server.get_request_summary("openai", "sk-proj-testSecretKey12345")
        self.assertEqual(res_openai["key_format_label"], "sk-")
        self.assertEqual(res_openai["auth_method"], "Bearer")

        # 3. other
        res_other = server.get_request_summary("openai", "custom_raw_secret_key_12345")
        self.assertEqual(res_other["key_format_label"], "other")

        # 4. none / empty
        res_none = server.get_request_summary("openai", "")
        self.assertEqual(res_none["key_format_label"], "none")
        self.assertEqual(res_none["key_length"], 0)

if __name__ == "__main__":
    unittest.main()
