import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server


class TestConfigSensitiveGating(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.orig_data = server.DATA
        self.orig_config_file = server.CONFIG_FILE
        server.DATA = Path(self.tmp_dir)
        server.CONFIG_FILE = server.DATA / "config.json"
        server._CONFIG_CACHE = None

        with open(server.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "provider": "anthropic",
                "base_url": "",
                "api_key": "sk-ant-testkey1234567890",
                "remote_bind_ip": "127.0.0.1",
                "fallback_providers": []
            }, f)

        server.CONFIG_CONFIRM_TOKENS.clear()

    def tearDown(self):
        server.CONFIG_CONFIRM_TOKENS.clear()
        server._CONFIG_CACHE = None
        server.DATA = self.orig_data
        server.CONFIG_FILE = self.orig_config_file
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _post(self, path, payload):
        sent = {}
        def mock_send(code, data):
            sent["code"] = code
            sent["data"] = data
            return None

        body_bytes = json.dumps(payload).encode("utf-8")
        with patch.object(server.Handler, "__init__", lambda self: None), \
             patch.object(server.Handler, "_send", side_effect=mock_send), \
             patch.object(server, "check_session_auth", return_value=True):
            h = server.Handler()
            h.path = path
            h.headers = {
                "Host": "127.0.0.1:8765",
                "Origin": "http://127.0.0.1:8765",
                "Content-Length": str(len(body_bytes)),
            }
            h.client_address = ("127.0.0.1", 54321)
            h.rfile = io.BytesIO(body_bytes)
            h.wfile = io.BytesIO()
            server.Handler.do_POST(h)

        return sent.get("code"), sent.get("data")

    def test_scheme_validation(self):
        # Local addresses
        self.assertTrue(server.validate_base_url_scheme("http://localhost:11434")[0])
        self.assertTrue(server.validate_base_url_scheme("http://127.0.0.1:11434")[0])
        self.assertTrue(server.validate_base_url_scheme("http://[::1]:11434")[0])
        self.assertTrue(server.validate_base_url_scheme("https://api.openai.com/v1")[0])
        self.assertTrue(server.validate_base_url_scheme("")[0])

        # Non-local http refused
        ok, err = server.validate_base_url_scheme("http://evil.example")
        self.assertFalse(ok)
        self.assertIn("must use https://", err)

        ok, err = server.validate_base_url_scheme("http://192.168.1.100:8000")
        self.assertFalse(ok)
        self.assertIn("must use https://", err)

    def test_changing_base_url_without_token_refused(self):
        # Simulate POST /api/config changing base_url without confirm_token
        code, data = self._post("/api/config", {"base_url": "http://localhost:11434"})
        self.assertEqual(code, 200)
        self.assertTrue(data.get("need_confirm"))
        self.assertIn("base_url", data.get("keys", []))
        token = data.get("token")
        self.assertTrue(token)

        # Invalid token rejected
        code, data = self._post("/api/config", {
            "base_url": "http://localhost:11434",
            "confirm_token": "wrong_token"
        })
        self.assertEqual(code, 403)

        # Valid token accepted
        code, data = self._post("/api/config", {
            "base_url": "http://localhost:11434",
            "confirm_token": token
        })
        self.assertEqual(code, 200)
        self.assertTrue(data.get("ok"))
        cfg = server.get_config()
        self.assertEqual(cfg.get("base_url"), "http://localhost:11434")

    def test_http_evil_example_refused(self):
        # In /api/config
        code, data = self._post("/api/config", {"base_url": "http://evil.example"})
        self.assertEqual(code, 400)
        self.assertIn("must use https://", data.get("error", ""))

        # In /api/config/test
        code, data = self._post("/api/config/test", {"base_url": "http://evil.example"})
        self.assertEqual(code, 400)
        self.assertEqual(data.get("category"), "invalid_url")

    def test_api_config_test_saved_key_mismatch_refused(self):
        # Trying to test saved key against arbitrary external URL without entering key
        code, data = self._post("/api/config/test", {
            "provider": "anthropic",
            "base_url": "https://attacker.com/v1"
        })
        self.assertEqual(code, 400)
        self.assertEqual(data.get("category"), "forbidden")

    def test_sensitive_keys_confirm_tier(self):
        # Test provider requires confirmation
        code, data = self._post("/api/config", {"provider": "openai"})
        self.assertEqual(code, 200)
        self.assertTrue(data.get("need_confirm"))
        self.assertIn("provider", data.get("keys", []))

        # Test remote_bind_ip requires confirmation
        code, data = self._post("/api/config", {"remote_bind_ip": "192.168.1.50"})
        self.assertEqual(code, 200)
        self.assertTrue(data.get("need_confirm"))
        self.assertIn("remote_bind_ip", data.get("keys", []))

        # Test fallback_providers requires confirmation
        code, data = self._post("/api/config", {"fallback_providers": ["gemini"]})
        self.assertEqual(code, 200)
        self.assertTrue(data.get("need_confirm"))
        self.assertIn("fallback_providers", data.get("keys", []))


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
