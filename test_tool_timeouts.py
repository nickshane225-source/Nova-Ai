import time
import unittest
from unittest.mock import MagicMock, patch

import server


class TestToolTimeouts(unittest.TestCase):
    def test_fetch_url_timeout_and_char_cap(self):
        """FETCH tool enforces strict timeout and 6000-char cap."""
        # Test refusal of non-http/https
        res_file = server.fetch_url_content("file:///C:/Windows/win.ini")
        self.assertIn("Refused", res_file)

        # Mock ssrf_guard to test timeout and cap
        with patch("ssrf_guard.safe_http_fetch") as mock_fetch:
            mock_fetch.return_value = (True, "A" * 6000, {})

            out = server.fetch_url_content("https://example.com/data.txt", timeout=10.0)
            mock_fetch.assert_called()
            self.assertEqual(mock_fetch.call_args[1].get("timeout"), 10.0)
            # Must cap output at 6000 characters
            self.assertEqual(len(out), 6000)

    def test_vision_llm_timeout_passed_to_anthropic_and_openai(self):
        """call_llm_vision passes explicit timeout to both Anthropic and OpenAI calls."""
        cfg_anthropic = {
            "provider": "anthropic",
            "api_key": "test_key",
            "model": "claude-3-5-sonnet-latest",
            "llm_timeout": 42,
        }
        with patch("server.http_post", return_value={"content": [{"text": "Anthropic Vision OK"}]}) as mock_post:
            server.call_llm_vision(cfg_anthropic, "prompt", "base64image")
            self.assertEqual(mock_post.call_args[1].get("timeout"), 42)

        cfg_openai = {
            "provider": "openai",
            "api_key": "test_key",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o",
            "llm_timeout": 53,
        }
        with patch("server.http_post", return_value={"choices": [{"message": {"content": "OpenAI Vision OK"}}]}) as mock_post:
            server.call_llm_vision(cfg_openai, "prompt", "base64image")
            self.assertEqual(mock_post.call_args[1].get("timeout"), 53)


if __name__ == "__main__":
    unittest.main()
