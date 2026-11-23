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

    def test_config_secrets_remain_encrypted_on_disk_after_load_config_migration(self):
        """
        Item 3 Config migration:
        - Shows that config.json secrets remain encrypted on disk after load_config runs the migration.
        - Uses update_json for atomic migration without decrypting secrets.
        """
        encrypted_secret = "dpapi:AQAAANCMnd8BFdERjHoAwE/Cl+sBAAAA_TEST_ENCRYPTED_KEY_VALUE"
        initial_disk_config = {
            "api_key": encrypted_secret,
            "wake_word_enabled": True,
            "encrypt_keys": True,
        }
        with open(server.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(initial_disk_config, f, indent=2)

        # Execute load_config (alias to get_config)
        self.assertTrue(hasattr(server, "load_config"))
        cfg = server.load_config()

        # In-memory config has migrated wake-word
        self.assertFalse(cfg["wake_word_enabled"])
        self.assertTrue(cfg["wake_word_migrated_banner"])

        # Read the raw file directly from disk to verify secrets remained encrypted
        with open(server.CONFIG_FILE, "r", encoding="utf-8") as f:
            disk_after = json.load(f)

        self.assertFalse(disk_after["wake_word_enabled"])
        self.assertFalse(disk_after["wake_word_user_choice"])
        self.assertTrue(disk_after["wake_word_migrated_banner"])
        # CRITICAL ASSERTION: The secret on disk is still the exact encrypted ciphertext!
        self.assertEqual(disk_after["api_key"], encrypted_secret)

    def test_dismiss_wake_word_banner_clears_flag_on_disk(self):
        """Clear wake_word_migrated_banner when the user dismisses the banner."""
        with open(server.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"wake_word_enabled": True}, f)

        # Trigger migration
        cfg = server.load_config()
        self.assertTrue(cfg["wake_word_migrated_banner"])

        # Dismiss banner route
        code, data = self._post("/api/config/dismiss_wake_word_banner", {})
        self.assertEqual(code, 200)
        self.assertTrue(data.get("ok"))
        self.assertFalse(data.get("wake_word_migrated_banner"))

        # Verify disk file has banner cleared
        with open(server.CONFIG_FILE, "r", encoding="utf-8") as f:
            disk_after = json.load(f)
        self.assertFalse(disk_after.get("wake_word_migrated_banner", False))

        # Also test dismissal via POST /api/config
        code2, data2 = self._post("/api/config", {"wake_word_migrated_banner": False})
        self.assertEqual(code2, 200)
        self.assertTrue(data2.get("ok"))

    def test_enable_wake_word_restart_stays_enabled_and_full_backup(self):
        """
        Item 1 Requirement:
        - Enable wake word via Settings (/api/config).
        - Restart (call get_config()). Wake word stays enabled (wake_word_user_choice=true prevents re-migration).
        - Legacy config with wake_word_enabled true and no choice flag is migrated off once.
        - Secrets stay encrypted on disk.
        - Backup file config.json.bak contains full content, never partial content.
        """
        encrypted_secret = "dpapi:AQAAANCMnd8BFdERjHoAwE/Cl+sBAAAA_SECRET_ON_DISK"
        initial_config = {
            "api_key": encrypted_secret,
            "wake_word_enabled": True,  # legacy config without choice flag
            "encrypt_keys": True,
            "user_name": "Alice",
            "model": "claude-3-5-sonnet",
        }
        with open(server.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(initial_config, f, indent=2)

        # 1. First boot / migration: legacy config migrated off once
        cfg1 = server.get_config()
        self.assertFalse(cfg1["wake_word_enabled"])
        self.assertFalse(cfg1["wake_word_user_choice"])
        self.assertTrue(cfg1["wake_word_migrated_banner"])

        # Check disk after migration: secret remained encrypted, full backup exists
        with open(server.CONFIG_FILE, "r", encoding="utf-8") as f:
            disk1 = json.load(f)
        self.assertEqual(disk1["api_key"], encrypted_secret)
        self.assertEqual(disk1["user_name"], "Alice")
        bak_file = server.CONFIG_FILE.with_name(server.CONFIG_FILE.name + ".bak")
        self.assertTrue(bak_file.exists())
        with open(bak_file, "r", encoding="utf-8") as f:
            bak1 = json.load(f)
        self.assertEqual(bak1["api_key"], encrypted_secret)
        self.assertEqual(bak1["user_name"], "Alice")

        # 2. User explicitly enables wake-word in Settings UI
        code, data = self._post("/api/config", {"wake_word_enabled": True})
        self.assertEqual(code, 200)
        self.assertTrue(data.get("ok"))

        # Verify on disk that wake_word_user_choice is True and banner cleared
        with open(server.CONFIG_FILE, "r", encoding="utf-8") as f:
            disk2 = json.load(f)
        self.assertTrue(disk2["wake_word_enabled"])
        self.assertTrue(disk2["wake_word_user_choice"])
        self.assertFalse(disk2.get("wake_word_migrated_banner", False))
        self.assertEqual(disk2["api_key"], encrypted_secret)

        # 3. Simulate server restart: re-read config from disk
        server._CONFIG_CACHE = None
        cfg_restarted = server.get_config()
        self.assertTrue(cfg_restarted["wake_word_enabled"])
        self.assertTrue(cfg_restarted["wake_word_user_choice"])
        self.assertFalse(cfg_restarted.get("wake_word_migrated_banner", False))

        # Check backup file has full content
        with open(bak_file, "r", encoding="utf-8") as f:
            bak2 = json.load(f)
        self.assertTrue(bak2["wake_word_enabled"])
        self.assertTrue(bak2["wake_word_user_choice"])
        self.assertEqual(bak2["api_key"], encrypted_secret)
        self.assertEqual(bak2["user_name"], "Alice")


if __name__ == "__main__":
    unittest.main()
