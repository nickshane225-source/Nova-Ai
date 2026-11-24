import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import server


class TestSettingsKeyValidation(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.orig_cfg_path = server.CONFIG_FILE
        server.CONFIG_FILE = Path(self.tmpdir.name) / "config.json"
        self.test_cfg = dict(server.DEFAULT_CONFIG)
        self.test_cfg["provider"] = "anthropic"
        self.test_cfg["api_key"] = ""
        server.save_config(self.test_cfg)

    def tearDown(self):
        server.CONFIG_FILE = self.orig_cfg_path
        self.tmpdir.cleanup()

    def test_mismatch_detection_rules(self):
        # Anthropic key on non-Anthropic provider
        self.assertIsNotNone(server.detect_api_key_provider_mismatch("gemini", "sk-ant-api03-1234567890"))
        self.assertIsNotNone(server.detect_api_key_provider_mismatch("openai", "sk-ant-api03-1234567890", "https://api.openai.com/v1"))
        self.assertIsNone(server.detect_api_key_provider_mismatch("anthropic", "sk-ant-api03-1234567890"))

        # Google keys (AIza and AQ.) on non-Gemini provider
        self.assertIsNotNone(server.detect_api_key_provider_mismatch("anthropic", "AIzaSyD-fake-google-key-123456"))
        self.assertIsNotNone(server.detect_api_key_provider_mismatch("anthropic", "AQ.Ab8RN6LfakeGoogleAuthKey123456789"))
        self.assertIsNotNone(server.detect_api_key_provider_mismatch("openai", "AQ.Ab8RN6LfakeGoogleAuthKey123456789", "https://api.openai.com/v1"))
        aq_note = server.detect_api_key_provider_mismatch("openai", "AQ.Ab8RN6LfakeGoogleAuthKey123456789", "https://generativelanguage.googleapis.com/v1beta/openai")
        self.assertIn("Vertex/Agent Platform express mode", aq_note)
        self.assertNotIn("invalid", aq_note.lower())
        self.assertIsNone(server.detect_api_key_provider_mismatch("gemini", "AIzaSyD-fake-google-key-123456"))

        # OpenAI key on Anthropic or Gemini
        self.assertIsNotNone(server.detect_api_key_provider_mismatch("anthropic", "sk-proj-1234567890abcdef"))
        self.assertIsNotNone(server.detect_api_key_provider_mismatch("gemini", "sk-proj-1234567890abcdef"))
        self.assertIsNone(server.detect_api_key_provider_mismatch("openai", "sk-proj-1234567890abcdef", "https://api.openai.com/v1"))

    def test_connection_outcomes_mocked_http(self):
        # 1. Success (verifies 1-token request)
        captured = {}
        def fake_post_ok(url, headers, body, timeout=15):
            captured["url"] = url
            captured["body"] = body
            return {"choices": [{"message": {"content": "ok"}}]}

        with mock.patch.object(server, "http_post", side_effect=fake_post_ok):
            res = server.test_llm_connection(
                provider="openai",
                api_key="AQ.Ab8RN6LfakeValidGeminiKey1234567890",
                model="gemini-3.5-flash-lite",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            )
        self.assertTrue(res["ok"])
        self.assertEqual(res["category"], "ok")
        self.assertEqual(captured["body"]["max_tokens"], 1)

        # 2. Wrong provider (401 + mismatch)
        with mock.patch.object(server, "http_post", side_effect=server.LLMError('API error 401: {"type":"authentication_error","message":"invalid x-api-key"}')):
            res = server.test_llm_connection(
                provider="anthropic",
                api_key="AQ.Ab8RN6LfakeGoogleKey12345678901234",
                model="claude-3-5-sonnet-latest",
            )
        self.assertFalse(res["ok"])
        self.assertEqual(res["category"], "wrong_provider")
        self.assertIn("Google Gemini", res["message"])
        self.assertNotIn("AQ.Ab8RN6LfakeGoogleKey12345678901234", res["message"])

        # 3. Invalid key (401 without mismatch)
        with mock.patch.object(server, "http_post", side_effect=server.LLMError("API error 401: invalid x-api-key")):
            res = server.test_llm_connection(
                provider="anthropic",
                api_key="sk-ant-api03-invalid-fake-key-123456",
                model="claude-3-5-sonnet-latest",
            )
        self.assertFalse(res["ok"])
        self.assertEqual(res["category"], "invalid_key")
        self.assertNotIn("sk-ant-api03-invalid-fake-key-123456", res["message"])

        # 4. Quota exceeded (429)
        with mock.patch.object(server, "http_post", side_effect=server.LLMError("API error 429: You exceeded your current quota")):
            res = server.test_llm_connection(
                provider="openai",
                api_key="AQ.Ab8RN6LfakeQuotaKey123456789012345",
                model="gemini-3.5-flash-lite",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            )
        self.assertFalse(res["ok"])
        self.assertEqual(res["category"], "quota")

        # 5. Network error
        with mock.patch.object(server, "http_post", side_effect=server.LLMError("Could not reach the AI provider: timed out")):
            res = server.test_llm_connection(
                provider="openai",
                api_key="sk-proj-fakekey1234567890",
                model="gpt-4o-mini",
                base_url="https://api.openai.com/v1",
            )
        self.assertFalse(res["ok"])
        self.assertEqual(res["category"], "network")

    def test_api_config_refuses_failed_key_unless_overridden(self):
        srv = server.SilentThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            headers = {
                "Content-Type": "application/json",
                "Cookie": f"nova_session={server.SESSION_TOKEN}",
                "X-Nova-Token": server.API_SESSION_TOKEN,
                "Origin": f"http://127.0.0.1:{port}",
            }

            # 1. /api/config/test returns 200 with structured failure on 401
            with mock.patch.object(server, "http_post", side_effect=server.LLMError("API error 401: invalid x-api-key")):
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/config/test",
                    data=json.dumps({
                        "provider": "anthropic",
                        "api_key": "AQ.Ab8RN6LwrongProviderKey1234567890",
                        "model": "claude-3-5-sonnet-latest",
                    }).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                self.assertFalse(data["ok"])
                self.assertEqual(data["category"], "wrong_provider")

            # 2. /api/config with verify_key=True refuses to save when test fails
            with mock.patch.object(server, "http_post", side_effect=server.LLMError("API error 401: invalid x-api-key")):
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/config",
                    data=json.dumps({
                        "provider": "anthropic",
                        "api_key": "AQ.Ab8RN6LwrongProviderKey1234567890",
                        "model": "claude-3-5-sonnet-latest",
                        "verify_key": True,
                    }).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(req, timeout=5)
                self.assertEqual(ctx.exception.code, 400)
                err_body = json.loads(ctx.exception.read().decode("utf-8"))
                self.assertTrue(err_body.get("test_failed"))
                self.assertEqual(err_body.get("category"), "wrong_provider")
                # Key must NOT have been saved
                self.assertEqual(server.get_config().get("api_key"), "")

            # 3. /api/config with force_save_key=True overrides and saves
            with mock.patch.object(server, "http_post", side_effect=server.LLMError("API error 401: invalid x-api-key")):
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/config",
                    data=json.dumps({
                        "provider": "anthropic",
                        "api_key": "AQ.Ab8RN6LwrongProviderKey1234567890",
                        "model": "claude-3-5-sonnet-latest",
                        "verify_key": True,
                        "force_save_key": True,
                    }).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    self.assertEqual(resp.status, 200)
                self.assertEqual(server.get_config().get("api_key"), "AQ.Ab8RN6LwrongProviderKey1234567890")
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
