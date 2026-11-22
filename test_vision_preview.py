import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import server


class TestVisionPreview(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.tmp_path = Path(self.tmp_dir)
        self.orig_workspace = server.WORKSPACE
        self.orig_data = server.DATA
        self.orig_config_file = server.CONFIG_FILE
        server.WORKSPACE = self.tmp_path / "ws"
        server.WORKSPACE.mkdir(parents=True, exist_ok=True)
        server.DATA = self.tmp_path / "data"
        server.DATA.mkdir(parents=True, exist_ok=True)
        server.CONFIG_FILE = server.DATA / "config.json"
        server._CONFIG_CACHE = None
        server.PENDING_ACTIONS.clear()

        # Dummy fake png screenshot
        self.fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRtestimagebytes"

    def tearDown(self):
        server.PENDING_ACTIONS.clear()
        server._CONFIG_CACHE = None
        server.WORKSPACE = self.orig_workspace
        server.DATA = self.orig_data
        server.CONFIG_FILE = self.orig_config_file
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _mock_capture(self, target_path):
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.fake_png)
        return target

    def test_vision_preview_default_on_in_tainted_context(self):
        cfg = {"vision_preview": None}
        with patch.object(server, "get_active_window_title", return_value="Visual Studio Code - server.py"), \
             patch.object(server, "_capture_desktop_png", side_effect=self._mock_capture):
            p_entry, p_info, err = server.create_pending_action(
                cfg=cfg,
                name="VISION",
                arg="inspect screen",
                source="pc",
                is_tainted=True,
                reason="Tainted vision test"
            )

        self.assertIsNone(err)
        self.assertIsNotNone(p_entry)
        self.assertIn("image_preview", p_entry)
        self.assertTrue(p_entry["image_preview"].startswith("data:image/png;base64,"))
        self.assertIn("image_preview", p_info)
        self.assertIn("DESKTOP SCREENSHOT PREVIEW CAPTURED", p_entry["preview"])

    def test_vision_preview_default_on_in_non_pc_source(self):
        cfg = {"vision_preview": None}
        with patch.object(server, "get_active_window_title", return_value="Notepad - notes.txt"), \
             patch.object(server, "_capture_desktop_png", side_effect=self._mock_capture):
            p_entry, p_info, err = server.create_pending_action(
                cfg=cfg,
                name="SCREEN_ANALYZE",
                arg="what is this",
                source="discord",
                is_tainted=False,
                reason="Discord vision request"
            )

        self.assertIsNone(err)
        self.assertIsNotNone(p_entry)
        self.assertIn("image_preview", p_entry)
        self.assertTrue(p_entry["image_preview"].startswith("data:image/png;base64,"))

    def test_vision_preview_explicit_disabled(self):
        cfg = {"vision_preview": False}
        with patch.object(server, "get_active_window_title", return_value="Notepad"), \
             patch.object(server, "_capture_desktop_png", side_effect=self._mock_capture):
            p_entry, p_info, err = server.create_pending_action(
                cfg=cfg,
                name="VISION",
                arg="inspect screen",
                source="pc",
                is_tainted=True,
                reason="Tainted but preview off"
            )

        self.assertIsNone(err)
        self.assertIsNotNone(p_entry)
        self.assertNotIn("image_preview", p_entry)
        self.assertEqual(p_entry["preview"], "inspect screen")

    def test_sensitive_window_title_refusal(self):
        cfg = {"vision_block_sensitive_windows": True, "vision_preview": True}
        with patch.object(server, "get_active_window_title", return_value="1Password - Personal Vault"), \
             patch.object(server, "_capture_desktop_png", side_effect=self._mock_capture):
            p_entry, p_info, err = server.create_pending_action(
                cfg=cfg,
                name="VISION",
                arg="show passwords",
                source="pc",
                is_tainted=False,
                reason="Check passwords"
            )

            # Execution via skill_screen_analyze
            res = server.skill_screen_analyze("show passwords")

        self.assertIn("VISION REFUSED", p_entry["preview"])
        self.assertIn("1password", p_entry["preview"].lower())
        self.assertNotIn("image_preview", p_entry)
        self.assertIn("Vision capture refused", res)
        self.assertIn("1password", res.lower())


if __name__ == "__main__":
    unittest.main()
