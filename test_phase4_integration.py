"""
Unit tests for Phase 4: Standard Library Dependencies and ORGANIZE Gate.
Zero pip dependencies - Python standard library only.
"""
import unittest
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import server

class TestPhase4Integration(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(server.DEFAULT_CONFIG)
        self.cfg["confirm_destructive"] = True

    def test_screenshot_saves_to_workspace(self):
        with patch("server._capture_desktop_png") as mock_capture:
            target_path = server.WORKSPACE / "screenshots" / "test_shot.png"
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.touch()
            mock_capture.return_value = target_path

            res = server.skill_screenshot()
            self.assertIn("Screenshot saved to", res)
            self.assertTrue(str(server.WORKSPACE.resolve()) in res)
            self.assertNotIn("Pictures", res)

    def test_organize_requires_confirmation(self):
        # ORGANIZE requires confirmation in risk table
        req, reason = server.check_tool_confirmation_required(self.cfg, "ORGANIZE", "downloads")
        self.assertTrue(req)
        self.assertIn("Moving or sorting files requires user approval", reason)

        # Bypass when confirm_destructive is False
        cfg_bypass = dict(self.cfg)
        cfg_bypass["confirm_destructive"] = False
        req2, _ = server.check_tool_confirmation_required(cfg_bypass, "ORGANIZE", "downloads")
        self.assertFalse(req2)

    def test_zero_pip_dependencies_in_server(self):
        # Check imports in server.py
        import ast
        server_py = Path(server.__file__).resolve()
        tree = ast.parse(server_py.read_text(encoding="utf-8"))
        stdlib_names = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else set()
        local_names = {
            "server", "nova_browser", "memory_engine", "scheduler_engine", "skills_engine",
            "audit_logger", "guardian_agent", "plan_mode", "telegram_gateway", "integrations",
            "usage_tracker", "diagnostics", "discord_gateway", "ssrf_guard"
        }
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    self.assertTrue(root in stdlib_names or root in local_names, f"Non-stdlib import found: {root}")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root = node.module.split(".")[0]
                    self.assertTrue(root in stdlib_names or root in local_names, f"Non-stdlib import found: {root}")

if __name__ == "__main__":
    unittest.main()
