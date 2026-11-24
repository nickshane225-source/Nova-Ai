import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path
import server

class TestItem3MismatchCheckerAqAiza(unittest.TestCase):
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

    def test_aq_and_aiza_valid_formats_never_called_invalid(self):
        # AIza on Gemini produces no mismatch
        msg_aiza = server.detect_api_key_provider_mismatch("gemini", "AIza" + "SyD-mockedGoogleKey123456789")
        self.assertIsNone(msg_aiza)

        # AQ. on Gemini returns specific guidance note
        msg_aq = server.detect_api_key_provider_mismatch("gemini", "AQ." + "mockedGoogleStudioKey123456789")
        self.assertIsNotNone(msg_aq)
        self.assertEqual(
            msg_aq,
            "If this key was created for Vertex/Agent Platform express mode, it will not work with the Gemini API endpoint."
        )
        self.assertNotIn("invalid", msg_aq.lower())
        self.assertNotIn("wrong provider", msg_aq.lower())

        # Also works on native endpoint
        msg_aq_native = server.detect_api_key_provider_mismatch("gemini-native", "AQ." + "mockedGoogleStudioKey123456789")
        self.assertIn("Vertex/Agent Platform express mode", msg_aq_native)

    def test_aq_and_aiza_on_wrong_provider_flags_google_gemini(self):
        msg_wrong = server.detect_api_key_provider_mismatch("anthropic", "AQ." + "mockedKey123456789")
        self.assertIn("starts with 'AQ.' (Google Gemini)", msg_wrong)
        self.assertIn("provider is set to 'anthropic'", msg_wrong)

        msg_aiza_wrong = server.detect_api_key_provider_mismatch("anthropic", "AIza" + "SyD-mockedKey123456789")
        self.assertIn("starts with 'AIza' (Google Gemini)", msg_aiza_wrong)

    def test_aq_connection_failure_includes_vertex_note_not_wrong_provider(self):
        err = server.LLMError("API error 401: Unauthorized")
        err.status_code = 401
        with patch("server.http_post", side_effect=err):
            res = server.test_llm_connection(
                provider="gemini",
                api_key="AQ.mockedKeyFailingAuth123456789",
                model="gemini-2.5-flash"
            )
            self.assertFalse(res["ok"])
            self.assertEqual(res["category"], "invalid_key")
            self.assertIn("Vertex/Agent Platform express mode", res["message"])
            self.assertNotIn("Wrong provider", res["message"])
            self.assertIn("Key NOT saved", res["message"])

if __name__ == "__main__":
    unittest.main()
