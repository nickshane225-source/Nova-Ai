"""
Unit tests for OS-level Mouse, Keyboard, Hotkeys, and Active Window Automation in server.py
"""
import unittest
from unittest.mock import MagicMock, patch
import ctypes
import server

class TestOSAutomation(unittest.TestCase):
    def setUp(self):
        # Mock ctypes.windll.user32 to prevent actual mouse movements/keystrokes
        self.mock_user32 = MagicMock()
        self.mock_user32.GetSystemMetrics.side_effect = lambda idx: 1920 if idx == 0 else 1080
        self.mock_user32.GetForegroundWindow.return_value = 12345
        self.mock_user32.GetWindowTextLengthW.return_value = 8
        def fake_get_window_text(hwnd, buf, maxlen):
            buf.value = "TestApp"
            return 7
        self.mock_user32.GetWindowTextW.side_effect = fake_get_window_text

        self.patcher = patch.object(ctypes.windll, "user32", self.mock_user32)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_mouse_move_validation(self):
        # Valid coordinate parse
        res = server.run_skill({}, "MOUSE_MOVE", "100, 200")
        self.assertIn("Moved mouse cursor", res)
        self.mock_user32.SetCursorPos.assert_called_with(100, 200)

        # Invalid coordinate parse
        res_err = server.run_skill({}, "MOUSE_MOVE", "invalid")
        self.assertIn("Refused", res_err)

    def test_mouse_click_validation(self):
        # Click without coords (current pos)
        res_current = server.run_skill({}, "MOUSE_CLICK", "left")
        self.assertIn("Clicked left button", res_current)
        self.assertTrue(self.mock_user32.mouse_event.called)

        # Click with coords
        res_coords = server.run_skill({}, "MOUSE_CLICK", "200, 300 | right")
        self.assertIn("Clicked right button", res_coords)
        self.mock_user32.SetCursorPos.assert_called_with(200, 300)

    def test_type_keys_validation(self):
        res = server.run_skill({}, "TYPE_KEYS", "hello world")
        self.assertIn("Typed text", res)
        self.assertTrue(self.mock_user32.keybd_event.called)

    def test_hotkey_validation(self):
        res = server.run_skill({}, "HOTKEY", "ctrl+c")
        self.assertIn("Dispatched hotkey", res)
        self.assertTrue(self.mock_user32.keybd_event.called)

    def test_active_window(self):
        res = server.run_skill({}, "ACTIVE_WINDOW", "")
        self.assertIsInstance(res, str)
        self.assertTrue(len(res) > 0)

if __name__ == "__main__":
    unittest.main()
