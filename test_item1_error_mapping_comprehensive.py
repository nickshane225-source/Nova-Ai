import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path
import server

class TestItem1ErrorMappingComprehensive(unittest.TestCase):
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
        cfg["api_key"] = "sk-" + "validConfigKeyForTestsOnly12345"
        server.save_config(cfg)

    def tearDown(self):
        server.ROOT = self.orig_root
        server.DATA = self.orig_data
        server.WORKSPACE = self.orig_ws
        server.CONFIG_FILE = self.orig_config_file
        server.MEMORY_FILE = self.orig_memory_file
        self.tmp_dir.cleanup()

    def test_error_mapping_400_bad_request(self):
        err = server.LLMError("API error 400: Bad request parameters")
        err.status_code = 400
        with patch("server.http_post", side_effect=err):
            res = server.test_llm_connection(provider="openai", api_key="sk-test400Key12345", model="gpt-4o")
            self.assertFalse(res["ok"])
            self.assertEqual(res["status_code"], 400)
            self.assertIn("HTTP 400", res["message"])
            self.assertIn("Bad request", res["message"])
            self.assertIn("Key NOT saved", res["message"])

            chat_res = server.chat("test prompt", mode="developer", source="pc")
            self.assertIn("HTTP 400", chat_res["reply"])
            self.assertIn("Bad request", chat_res["reply"])

    def test_error_mapping_401_key_rejected(self):
        err = server.LLMError("API error 401: Unauthorized invalid api key")
        err.status_code = 401
        with patch("server.http_post", side_effect=err):
            res = server.test_llm_connection(provider="openai", api_key="sk-test401Key12345", model="gpt-4o")
            self.assertFalse(res["ok"])
            self.assertEqual(res["status_code"], 401)
            self.assertIn("HTTP 401", res["message"])
            self.assertIn("API key rejected", res["message"])
            self.assertIn("Key NOT saved", res["message"])

            chat_res = server.chat("test prompt", mode="developer", source="pc")
            self.assertIn("HTTP 401", chat_res["reply"])
            self.assertIn("API key rejected", chat_res["reply"])

    def test_error_mapping_403_permission_forbidden(self):
        err = server.LLMError("API error 403: Forbidden - API not enabled or region restricted")
        err.status_code = 403
        with patch("server.http_post", side_effect=err):
            res = server.test_llm_connection(provider="openai", api_key="sk-test403Key12345", model="gpt-4o")
            self.assertFalse(res["ok"])
            self.assertEqual(res["status_code"], 403)
            self.assertIn("HTTP 403", res["message"])
            self.assertIn("Access forbidden", res["message"])
            self.assertIn("Key NOT saved", res["message"])

            chat_res = server.chat("test prompt", mode="developer", source="pc")
            self.assertIn("HTTP 403", chat_res["reply"])
            self.assertIn("Access forbidden", chat_res["reply"])

    def test_error_mapping_404_model_not_found(self):
        err = server.LLMError("API error 404: The requested model does not exist")
        err.status_code = 404
        with patch("server.http_post", side_effect=err):
            res = server.test_llm_connection(provider="openai", api_key="sk-test404Key12345", model="nonexistent-model-xyz")
            self.assertFalse(res["ok"])
            self.assertEqual(res["status_code"], 404)
            self.assertIn("HTTP 404", res["message"])
            self.assertIn("nonexistent-model-xyz", res["message"])
            self.assertIn("Key NOT saved", res["message"])

            chat_res = server.chat("test prompt", mode="developer", source="pc")
            self.assertIn("HTTP 404", chat_res["reply"])
            self.assertIn("not found on provider", chat_res["reply"])

    def test_error_mapping_429_quota_limit(self):
        err = server.LLMError("API error 429: Rate limit exceeded or quota exhausted")
        err.status_code = 429
        with patch("server.http_post", side_effect=err):
            res = server.test_llm_connection(provider="openai", api_key="sk-test429Key12345", model="gpt-4o")
            self.assertFalse(res["ok"])
            self.assertEqual(res["status_code"], 429)
            self.assertIn("HTTP 429", res["message"])
            self.assertIn("Quota or rate limit exceeded", res["message"])
            self.assertIn("Key NOT saved", res["message"])

            chat_res = server.chat("test prompt", mode="developer", source="pc")
            self.assertIn("HTTP 429", chat_res["reply"])
            self.assertIn("quota or rate limit exceeded", chat_res["reply"])

    def test_error_mapping_5xx_provider_outage(self):
        for code in (500, 502, 503, 504):
            err = server.LLMError(f"API error {code}: Bad Gateway / Server Error")
            err.status_code = code
            with patch("server.http_post", side_effect=err):
                res = server.test_llm_connection(provider="openai", api_key="sk-test5xxKey12345", model="gpt-4o")
                self.assertFalse(res["ok"])
                self.assertEqual(res["status_code"], code)
                self.assertIn(f"HTTP {code}", res["message"])
                self.assertIn("Provider service outage", res["message"])
                self.assertIn("Key NOT saved", res["message"])

                chat_res = server.chat("test prompt", mode="developer", source="pc")
                self.assertIn(f"HTTP {code}", chat_res["reply"])
                self.assertIn("Provider outage or server error", chat_res["reply"])

    def test_error_mapping_network_timeout_dns(self):
        err = server.LLMError("Could not reach the AI provider: <urlopen error [Errno 11001] getaddrinfo failed>")
        with patch("server.http_post", side_effect=err):
            res = server.test_llm_connection(provider="openai", api_key="sk-testNetKey12345", model="gpt-4o")
            self.assertFalse(res["ok"])
            self.assertIsNone(res["status_code"])
            self.assertIn("Network error", res["message"])
            self.assertIn("Key NOT saved", res["message"])

            chat_res = server.chat("test prompt", mode="developer", source="pc")
            self.assertIn("Network error", chat_res["reply"])

if __name__ == "__main__":
    unittest.main()
