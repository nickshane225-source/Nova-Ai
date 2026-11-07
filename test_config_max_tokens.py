"""
Unit tests for max_tokens configuration and fallback handling.
"""
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server

class TestConfigMaxTokens(unittest.TestCase):

    def test_default_config_fallback(self):
        # Real get_config() fallback and real POST /api/config validation
        with patch("server.load_json", return_value={}):
            cfg = server.get_config()
            self.assertEqual(cfg.get("max_tokens"), 2048)

        class MockConfigHandler(server.Handler):
            def __init__(self, body):
                self.path = "/api/config"
                self.headers = {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"}
                self.command = "POST"
                self.requestline = "POST /api/config HTTP/1.1"
                self._test_body = body
                self.status = None
                self.data = None
            def _body(self):
                return self._test_body
            def _send(self, status, data, ctype="application/json"):
                self.status = status
                self.data = data

        # Out-of-bounds rejected by real server handler
        h_bad = MockConfigHandler({"max_tokens": 100})
        h_bad.do_POST()
        self.assertEqual(h_bad.status, 400)

        # Valid setting accepted by real server handler
        with patch("server.save_config"):
            h_good = MockConfigHandler({"max_tokens": 4096})
            h_good.do_POST()
            self.assertEqual(h_good.status, 200)

    def test_call_llm_uses_configured_max_tokens(self):
        # Test OpenAI compatible path
        captured_body = {}
        def mock_http_post(url, headers, body, timeout=60):
            nonlocal captured_body
            captured_body = body
            return {"choices": [{"message": {"content": "ok"}}]}

        custom_cfg = {
            "provider": "openai",
            "model": "gpt-4o",
            "base_url": "http://127.0.0.1:11434/v1",
            "api_key": "test",
            "max_tokens": 4096
        }

        with patch("server.http_post", side_effect=mock_http_post):
            server.call_llm(custom_cfg, "system", [{"role": "user", "content": "hi"}])
            self.assertEqual(captured_body.get("max_tokens"), 4096)

        # Test fallback when max_tokens is omitted
        custom_cfg_no_tokens = {
            "provider": "openai",
            "model": "gpt-4o",
            "base_url": "http://127.0.0.1:11434/v1",
            "api_key": "test",
        }
        with patch("server.http_post", side_effect=mock_http_post):
            server.call_llm(custom_cfg_no_tokens, "system", [{"role": "user", "content": "hi"}])
            self.assertEqual(captured_body.get("max_tokens"), 2048)

    def test_anthropic_uses_configured_max_tokens(self):
        captured_payload = {}
        def mock_http_post(url, headers, body, timeout=60):
            nonlocal captured_payload
            captured_payload = body
            return {"content": [{"text": "anthropic ok"}]}

        anthropic_cfg = {
            "provider": "anthropic",
            "model": "claude-3-5-sonnet-latest",
            "api_key": "sk-ant-test",
            "max_tokens": 3000
        }
        with patch("server.http_post", side_effect=mock_http_post):
            server.call_llm(anthropic_cfg, "system", [{"role": "user", "content": "hi"}])
            self.assertEqual(captured_payload.get("max_tokens"), 3000)

        # Anthropic fallback to 2048
        anthropic_cfg_fallback = {
            "provider": "anthropic",
            "model": "claude-3-5-sonnet-latest",
            "api_key": "sk-ant-test",
        }
        with patch("server.http_post", side_effect=mock_http_post):
            server.call_llm(anthropic_cfg_fallback, "system", [{"role": "user", "content": "hi"}])
            self.assertEqual(captured_payload.get("max_tokens"), 2048)

    def test_api_config_endpoint_max_tokens(self):
        """Real endpoint test for /api/config via Handler.do_POST."""
        class MockConfigReq:
            def __init__(self, body):
                self.headers = {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"}
                self.command = "POST"
                self.path = "/api/config"
                self._test_body = body
                self.status = None
                self.data = None
            _local_only = server.Handler._local_only
            do_POST = server.Handler.do_POST
            def _body(self):
                return self._test_body
            def _send(self, status, data, ctype="application/json"):
                self.status = status
                self.data = data

        # Test valid max_tokens
        req_valid = MockConfigReq({"max_tokens": 4096})
        with patch("server.save_json") as mock_save:
            req_valid.do_POST()
            self.assertEqual(req_valid.status, 200)
            self.assertTrue(req_valid.data["ok"])
            saved_cfg = mock_save.call_args[0][1]
            self.assertEqual(saved_cfg["max_tokens"], 4096)

        # Test minimum boundary (256)
        req_min = MockConfigReq({"max_tokens": 256})
        with patch("server.save_json") as mock_save:
            req_min.do_POST()
            self.assertEqual(req_min.status, 200)
            saved_cfg = mock_save.call_args[0][1]
            self.assertEqual(saved_cfg["max_tokens"], 256)

        # Test maximum boundary (8192)
        req_max = MockConfigReq({"max_tokens": 8192})
        with patch("server.save_json") as mock_save:
            req_max.do_POST()
            self.assertEqual(req_max.status, 200)
            saved_cfg = mock_save.call_args[0][1]
            self.assertEqual(saved_cfg["max_tokens"], 8192)

        # Test out of range rejected (100)
        req_low = MockConfigReq({"max_tokens": 100})
        req_low.do_POST()
        self.assertEqual(req_low.status, 400)
        self.assertFalse(req_low.data["ok"])

        # Test out of range rejected (99999)
        req_high = MockConfigReq({"max_tokens": 99999})
        req_high.do_POST()
        self.assertEqual(req_high.status, 400)
        self.assertFalse(req_high.data["ok"])

        # Test invalid string rejected
        req_invalid = MockConfigReq({"max_tokens": "invalid"})
        req_invalid.do_POST()
        self.assertEqual(req_invalid.status, 400)
        self.assertFalse(req_invalid.data["ok"])

if __name__ == "__main__":
    unittest.main()
