import unittest
from unittest.mock import patch, MagicMock
import tempfile
from pathlib import Path
import server

class TestItem2GeminiNativeAndKeySanitization(unittest.TestCase):
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

    def test_key_trimming_whitespace_quotes_newlines(self):
        # Trims whitespace, single/double quotes, and newlines
        padded = "  \n\t 'sk-validSecretSampleKey12345' \r\n  "
        valid, cleaned, err = server.sanitize_and_validate_api_key(padded)
        self.assertTrue(valid)
        self.assertEqual(cleaned, "sk-validSecretSampleKey12345")
        self.assertEqual(err, "")

        double_quoted = '  "AQ.validGoogleSampleKey987654" \n'
        valid2, cleaned2, err2 = server.sanitize_and_validate_api_key(double_quoted)
        self.assertTrue(valid2)
        self.assertEqual(cleaned2, "AQ.validGoogleSampleKey987654")

    def test_reject_keys_containing_spaces(self):
        spaced_key = "sk-invalid key with spaces"
        valid, cleaned, err = server.sanitize_and_validate_api_key(spaced_key)
        self.assertFalse(valid)
        self.assertIn("spaces", err)

        # In test_llm_connection
        res = server.test_llm_connection(
            provider="anthropic",
            api_key=spaced_key,
            model="claude-3-5-sonnet-latest"
        )
        self.assertFalse(res["ok"])
        self.assertIn("cannot contain spaces", res["message"])
        self.assertIn("Key NOT saved", res["message"])

    def test_gemini_openai_compatible_sends_bearer_token(self):
        cfg = {
            "provider": "openai",
            "model": "gemini-2.5-flash",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "api_key": "AQ.mockedTestBearerKey12345",
            "max_tokens": 1024,
        }
        with patch("server.http_post") as mock_post:
            mock_post.return_value = {
                "choices": [{"message": {"content": "OpenAI-compatible Gemini response"}}]
            }
            reply = server._call_single_llm(cfg, "System instructions", [{"role": "user", "content": "Hello"}])
            self.assertEqual(reply, "OpenAI-compatible Gemini response")
            mock_post.assert_called_once()
            called_url, called_headers, called_body = mock_post.call_args[0][:3]
            self.assertTrue(called_url.endswith("/chat/completions"))
            self.assertEqual(called_headers.get("authorization"), "Bearer AQ.mockedTestBearerKey12345")

    def test_gemini_native_endpoint_sends_x_goog_api_key(self):
        cfg = {
            "provider": "gemini-native",
            "model": "gemini-2.5-flash",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "api_key": "AQ.mockedTestNativeKey12345",
            "max_tokens": 1024,
        }
        with patch("server.http_post") as mock_post:
            mock_post.return_value = {
                "candidates": [{
                    "content": {
                        "parts": [{"text": "Native Gemini response"}]
                    }
                }]
            }
            reply = server._call_single_llm(cfg, "System instructions", [{"role": "user", "content": "Hello native"}])
            self.assertEqual(reply, "Native Gemini response")
            mock_post.assert_called_once()
            called_url, called_headers, called_body = mock_post.call_args[0][:3]
            self.assertIn("/models/gemini-2.5-flash:generateContent", called_url)
            self.assertEqual(called_headers.get("x-goog-api-key"), "AQ.mockedTestNativeKey12345")
            self.assertNotIn("authorization", called_headers)

if __name__ == "__main__":
    unittest.main()
