import unittest
from unittest.mock import patch
import tempfile
import urllib.parse
from pathlib import Path
import server

class TestItem2NativeGeminiModelValidation(unittest.TestCase):
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

    def test_model_name_validation_rejections(self):
        invalid_models = [
            "../x",
            "a/b",
            "model:evil",
            "model with spaces",
            "model?query=1",
            "model#frag",
            "model@gemini",
            "a" * 81,  # exceeds 80 chars
            "",
        ]
        for bad_m in invalid_models:
            valid, encoded, err = server.validate_gemini_model_name(bad_m)
            self.assertFalse(valid, f"Expected '{bad_m}' to be rejected")
            self.assertIn("Invalid Gemini model name", err or "Invalid Gemini model name")

    def test_model_name_valid_and_url_encoded(self):
        valid_models = [
            ("gemini-2.5-flash", "gemini-2.5-flash"),
            ("gemini-1.5-pro_002", "gemini-1.5-pro_002"),
            ("gemini.flash.1", "gemini.flash.1"),
            ("custom-model-v1.0", "custom-model-v1.0"),
        ]
        for raw, expected_enc in valid_models:
            valid, encoded, err = server.validate_gemini_model_name(raw)
            self.assertTrue(valid, f"Expected '{raw}' to be accepted")
            self.assertEqual(encoded, expected_enc)
            self.assertEqual(err, "")

    def test_test_llm_connection_rejects_bad_models_with_400(self):
        for bad_m in ("../x", "a/b", "model:evil", "model space"):
            res = server.test_llm_connection(
                provider="gemini-native",
                api_key="AQ.mockValidKeyFormat1234567890",
                model=bad_m
            )
            self.assertFalse(res["ok"])
            self.assertEqual(res["status_code"], 400)
            self.assertEqual(res["category"], "invalid_model")
            self.assertIn("HTTP 400", res["message"])
            self.assertIn("Invalid Gemini model name", res["message"])
            self.assertIn("Key NOT saved", res["message"])

    def test_call_single_llm_native_gemini_constructs_clean_url(self):
        cfg = {
            "provider": "gemini-native",
            "model": "gemini-2.5-flash",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "api_key": "AQ.mockValidKeyFormat1234567890",
            "max_tokens": 1024,
        }
        with patch("server.http_post") as mock_post:
            mock_post.return_value = {
                "candidates": [{"content": {"parts": [{"text": "OK"}]}}]
            }
            res = server._call_single_llm(cfg, "sys", [{"role": "user", "content": "hi"}])
            self.assertEqual(res, "OK")
            called_url = mock_post.call_args[0][0]
            self.assertEqual(called_url, "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent")

        # Now test that bad model raises 400 LLMError
        cfg["model"] = "bad/model:evil"
        with self.assertRaises(server.LLMError) as ctx:
            server._call_single_llm(cfg, "sys", [{"role": "user", "content": "hi"}])
        self.assertIn("Invalid Gemini model name", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()
