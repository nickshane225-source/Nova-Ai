import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server


class TestWakeWordMigration(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.orig_data = server.DATA
        self.orig_config_file = server.CONFIG_FILE
        server.DATA = Path(self.tmp_dir)
        server.CONFIG_FILE = server.DATA / "config.json"
        server._CONFIG_CACHE = None
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

    def test_legacy_wake_word_migrated_to_false_with_banner(self):
        # Saved config with wake_word_enabled=True and no wake_word_user_choice
        with open(server.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"wake_word_enabled": True}, f)

        cfg = server.get_config()
        self.assertFalse(cfg["wake_word_enabled"])
        self.assertFalse(cfg["wake_word_user_choice"])
        self.assertTrue(cfg["wake_word_migrated_banner"])

        # Check persisted file on disk
        with open(server.CONFIG_FILE, "r", encoding="utf-8") as f:
            disk_data = json.load(f)
        self.assertFalse(disk_data.get("wake_word_enabled"))
        self.assertFalse(disk_data.get("wake_word_user_choice"))

    def test_user_choice_preserved_and_not_overwritten(self):
        # User explicitly opted in
        with open(server.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"wake_word_enabled": True, "wake_word_user_choice": True}, f)

        cfg = server.get_config()
        self.assertTrue(cfg["wake_word_enabled"])
        self.assertTrue(cfg["wake_word_user_choice"])
        self.assertFalse(cfg.get("wake_word_migrated_banner", False))

    def test_saving_wake_word_marks_choice_and_clears_banner(self):
        with open(server.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"wake_word_enabled": True}, f)

        # Trigger migration first
        cfg = server.get_config()
        self.assertTrue(cfg["wake_word_migrated_banner"])

        # User saves wake_word_enabled in Settings
        code, data = self._post("/api/config", {"wake_word_enabled": True})
        self.assertEqual(code, 200)
        self.assertTrue(data.get("ok"))

        saved = server.get_config()
        self.assertTrue(saved["wake_word_enabled"])
        self.assertTrue(saved["wake_word_user_choice"])
        self.assertFalse(saved["wake_word_migrated_banner"])


if __name__ == "__main__":
    unittest.main()
