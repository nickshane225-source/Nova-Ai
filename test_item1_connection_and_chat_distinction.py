import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path
import server

class TestItem1ConnectionAndChatDistinction(unittest.TestCase):
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

    def test_connection_failure_shows_http_status_and_not_saved(self):
        err = server.LLMError("API error 401: Unauthorized access to resource")
        err.status_code = 401
        with patch("server.http_post", side_effect=err):
            res = server.test_llm_connection(
                provider="anthropic",
                api_key="sk-ant-" + "mockedKeyForTestingOnly123456789",
                model="claude-3-5-sonnet-latest"
            )
            self.assertFalse(res["ok"])
            self.assertEqual(res["status_code"], 401)
            self.assertIn("HTTP 401", res["message"])
            self.assertIn("Key NOT saved", res["message"])

    def test_chat_distinguishes_no_key_from_401_rejection(self):
        # Case A: No API key set
        cfg = server.get_config()
        cfg["api_key"] = ""
        server.save_config(cfg)
        res_no_key = server.chat("Hello assistant", mode="developer", source="pc")
        self.assertIn("No API key set", res_no_key["reply"])
        self.assertNotIn("HTTP 401", res_no_key["reply"])

        # Case B: Key set, but provider rejects with HTTP 401
        cfg["api_key"] = "sk-" + "mockedKeyRejectedByProvider123456789"
        server.save_config(cfg)
        err = server.LLMError("API error 401: Invalid bearer token")
        err.status_code = 401
        with patch("server.http_post", side_effect=err):
            res_401 = server.chat("Hello assistant", mode="developer", source="pc")
            self.assertIn("API key rejected by provider (HTTP 401)", res_401["reply"])
            self.assertNotIn("No API key set", res_401["reply"])

if __name__ == "__main__":
    unittest.main()
