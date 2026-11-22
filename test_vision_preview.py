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

            # Execution via skill_screen_analyze directly also refuses
            res = server.skill_screen_analyze("show passwords")

        self.assertIsNone(p_entry)
        self.assertIsNotNone(err)
        self.assertIn("refused", err.lower())
        self.assertIn("1password", err.lower())
        self.assertIn("Vision capture refused", res)
        self.assertIn("1password", res.lower())

    def test_bytes_sent_equals_bytes_previewed_and_no_second_capture(self):
        """
        Item 2: Vision preview
        - Capture ONCE at confirmation time.
        - Store exact bytes in the pending entry.
        - Send exactly those bytes after approval (no second capture).
        """
        import base64
        cfg = {"vision_preview": True}
        capture_calls = []

        def _tracking_capture(target_path):
            target = Path(target_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.fake_png)
            capture_calls.append(str(target))
            return target

        with patch.object(server, "get_active_window_title", return_value="Desktop Explorer"), \
             patch.object(server, "_capture_desktop_png", side_effect=_tracking_capture):
            p_entry, p_info, err = server.create_pending_action(
                cfg=cfg,
                name="VISION",
                arg="what is on screen",
                source="pc",
                is_tainted=True,
                reason="Review screen"
            )

        self.assertIsNone(err)
        self.assertIsNotNone(p_entry)
        self.assertEqual(len(capture_calls), 1, "Must capture exactly once at confirmation time")
        self.assertIn("captured_image_bytes", p_entry)
        self.assertEqual(p_entry["captured_image_bytes"], self.fake_png)

        # Base64 in preview must match the exact captured bytes
        expected_b64 = base64.b64encode(self.fake_png).decode("ascii")
        self.assertEqual(p_entry["image_preview"], f"data:image/png;base64,{expected_b64}")

        # Now simulate approval execution
        captured_vision_payloads = []

        def _mock_call_llm_vision(c, prompt, b64_img):
            captured_vision_payloads.append((prompt, b64_img))
            return "Vision analysis result"

        with patch.object(server, "call_llm_vision", side_effect=_mock_call_llm_vision), \
             patch.object(server, "_capture_desktop_png", side_effect=_tracking_capture):
            res = server.run_skill(
                cfg=cfg,
                name=p_entry["name"],
                arg=p_entry["arg"],
                source="pc",
                is_confirmed=True,
                captured_bytes=p_entry.get("captured_image_bytes"),
            )

        # Assert no second screenshot capture occurred!
        self.assertEqual(len(capture_calls), 1, "Must NOT take a second screenshot during approved execution")
        # Assert exact bytes were sent
        self.assertEqual(len(captured_vision_payloads), 1)
        self.assertEqual(captured_vision_payloads[0][1], expected_b64)
        self.assertIn("Vision analysis result", res)

    def test_missing_preview_causes_action_refusal(self):
        """If a preview was required and cannot be produced, refuse the action."""
        cfg = {"vision_preview": True}
        # Simulate capture returning None / failing
        with patch.object(server, "get_active_window_title", return_value="Desktop Explorer"), \
             patch.object(server, "_capture_desktop_png", return_value=None):
            p_entry, p_info, err = server.create_pending_action(
                cfg=cfg,
                name="VISION",
                arg="check screen",
                source="pc",
                is_tainted=False,
                reason="Required preview failure"
            )

        self.assertIsNone(p_entry)
        self.assertIsNone(p_info)
        self.assertIsNotNone(err)
        self.assertIn("Refused: Vision preview was required but could not be produced", err)

    def test_non_pc_or_tainted_vision_is_pc_only(self):
        """Vision from non-PC or tainted contexts is approvable on the PC only (pc_only)."""
        cfg = {"vision_preview": True}
        with patch.object(server, "get_active_window_title", return_value="Desktop Explorer"), \
             patch.object(server, "_capture_desktop_png", side_effect=self._mock_capture):
            p_entry, p_info, err = server.create_pending_action(
                cfg=cfg,
                name="VISION",
                arg="inspect screen",
                source="telegram",
                is_tainted=False,
                reason="Telegram vision call"
            )

        self.assertIsNone(err)
        self.assertIsNotNone(p_entry)
        self.assertTrue(p_entry.get("pc_only"), "Non-PC vision call must be flagged pc_only")
        self.assertTrue(p_info.get("pc_only"), "Pending info must be flagged pc_only")

    def test_zero_pillow_or_third_party_imports(self):
        """Verify NO Pillow or third-party imaging dependencies exist in the codebase."""
        import sys
        for mod in ("PIL", "PIL.Image", "PIL.ImageGrab", "pillow"):
            self.assertNotIn(mod, sys.modules)


if __name__ == "__main__":
    unittest.main()
