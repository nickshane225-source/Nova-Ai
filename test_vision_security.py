"""
test_vision_security.py - Verify VISION gating and UI banner:
1. The first VISION call per conversation requires confirmation.
2. Subsequent calls in the same untainted conversation auto-run once confirmed.
3. Tainted or non-PC turns always require confirmation.
4. Different conversation requires its own confirmation.
5. Clearing conversation resets the confirmation.
6. skill_screen_analyze emits vision_start and vision_end events.
"""

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

import server


class TestVisionSecurity(unittest.TestCase):

    def setUp(self):
        with server.CONVERSATION_VISION_LOCK:
            server.CONVERSATION_VISION_CONFIRMED.clear()
        with server.LOCK:
            server.EVENTS.clear()

    def tearDown(self):
        with server.CONVERSATION_VISION_LOCK:
            server.CONVERSATION_VISION_CONFIRMED.clear()

    def test_01_first_vision_call_per_conversation_requires_confirmation(self):
        """First VISION call in an untainted PC conversation requires user confirmation."""
        cfg = server.get_config()
        conv_id = "pc:chat_1"

        req, reason = server.check_tool_confirmation_required(
            cfg=cfg,
            name="VISION",
            arg="What is on my screen?",
            is_tainted=False,
            source="pc",
            conv_id=conv_id,
        )
        self.assertTrue(req, "First VISION call must require confirmation")
        self.assertIn("first call in this conversation", reason.lower())

    def test_02_subsequent_vision_call_allowed_after_confirmation(self):
        """After confirmation, subsequent untainted PC calls in the same conversation auto-run."""
        cfg = server.get_config()
        conv_id = "pc:chat_1"

        # Simulate user confirmation via CONVERSATION_VISION_CONFIRMED
        with server.CONVERSATION_VISION_LOCK:
            server.CONVERSATION_VISION_CONFIRMED.add(conv_id)

        req, reason = server.check_tool_confirmation_required(
            cfg=cfg,
            name="VISION",
            arg="Check this window now",
            is_tainted=False,
            source="pc",
            conv_id=conv_id,
        )
        self.assertFalse(req, "Subsequent untainted VISION call should not require confirmation")

    def test_03_tainted_or_non_pc_vision_always_requires_confirmation(self):
        """Tainted or remote VISION calls always require confirmation even if previously confirmed."""
        cfg = server.get_config()
        conv_id = "pc:chat_1"

        with server.CONVERSATION_VISION_LOCK:
            server.CONVERSATION_VISION_CONFIRMED.add(conv_id)

        # Tainted turn
        req, _ = server.check_tool_confirmation_required(
            cfg=cfg,
            name="VISION",
            arg="Analyze screen",
            is_tainted=True,
            source="pc",
            conv_id=conv_id,
        )
        self.assertTrue(req, "Tainted turn must require confirmation")

        # Non-PC source
        req, _ = server.check_tool_confirmation_required(
            cfg=cfg,
            name="VISION",
            arg="Analyze screen",
            is_tainted=False,
            source="telegram",
            conv_id="telegram:user1",
        )
        self.assertTrue(req, "Non-PC turn must require confirmation")

    def test_04_different_conversation_requires_its_own_confirmation(self):
        """A different conversation does not inherit confirmation from another conversation."""
        cfg = server.get_config()
        conv1 = "pc:chat_1"
        conv2 = "pc:chat_2"

        with server.CONVERSATION_VISION_LOCK:
            server.CONVERSATION_VISION_CONFIRMED.add(conv1)

        req, reason = server.check_tool_confirmation_required(
            cfg=cfg,
            name="VISION",
            arg="What is open?",
            is_tainted=False,
            source="pc",
            conv_id=conv2,
        )
        self.assertTrue(req, "New conversation must require its own confirmation")

    def test_05_screen_analyze_emits_vision_start_and_end_events(self):
        """skill_screen_analyze emits vision_start and vision_end events for the UI banner."""
        with patch("server._capture_desktop_png", return_value=Path("test_dummy.png")), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_bytes", return_value=b"fake_image_bytes"), \
             patch("server.call_llm_vision", return_value="Looks like code"):
            res = server.skill_screen_analyze("What is on screen?")
            self.assertIn("Screen Vision Analysis", res)

            # Check that events were pushed
            with server.LOCK:
                event_types = [e.get("type") for e in server.EVENTS]
            self.assertIn("vision_start", event_types)
            self.assertIn("vision_end", event_types)

    def test_06_vision_confirmed_set_is_bounded(self):
        with server.CONVERSATION_VISION_LOCK:
            for i in range(600):
                server.CONVERSATION_VISION_CONFIRMED.add(f"pc:conv_{i}")
            self.assertLessEqual(len(server.CONVERSATION_VISION_CONFIRMED), 500)
            self.assertNotIn("pc:conv_0", server.CONVERSATION_VISION_CONFIRMED)
            self.assertIn("pc:conv_599", server.CONVERSATION_VISION_CONFIRMED)

    def test_07_vision_confirmed_resets_on_reset_and_clear_untrusted(self):
        import json, threading, urllib.request
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
            with server.CONVERSATION_VISION_LOCK:
                server.CONVERSATION_VISION_CONFIRMED.add("pc:developer")
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/reset",
                data=json.dumps({"mode": "developer"}).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
            with server.CONVERSATION_VISION_LOCK:
                self.assertNotIn("pc:developer", server.CONVERSATION_VISION_CONFIRMED)

            with server.CONVERSATION_VISION_LOCK:
                server.CONVERSATION_VISION_CONFIRMED.add("pc:developer")
            req2 = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/clear_untrusted_context",
                data=json.dumps({"mode": "developer"}).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req2, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
            with server.CONVERSATION_VISION_LOCK:
                self.assertNotIn("pc:developer", server.CONVERSATION_VISION_CONFIRMED)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_08_vision_refuses_password_manager_and_banking_windows(self):
        for title in ("1Password - Vault", "Bitwarden Password Manager", "Chase Online Banking - Chrome"):
            with patch("server.get_active_window_title", return_value=title), \
                 patch("server._capture_desktop_png") as mock_cap:
                res = server.skill_screen_analyze("read my screen")
                self.assertIn("refused", res.lower())
                mock_cap.assert_not_called()

        with patch("server.get_active_window_title", return_value="server.py - Visual Studio Code"), \
             patch("server._capture_desktop_png", return_value=Path("test_dummy.png")), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_bytes", return_value=b"fake"), \
             patch("server.call_llm_vision", return_value="Code editor"):
            res = server.skill_screen_analyze("read my screen")
            self.assertIn("Code editor", res)


if __name__ == "__main__":
    unittest.main()
