"""
Unit tests for Task 3: Guardian AI Safety Reviewer (guardian_agent.py).
Zero third-party pip dependencies - Python standard library only.
"""
import json
import unittest
from unittest.mock import patch

import guardian_agent


class TestGuardianAgent(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "provider": "openai",
            "api_key": "mock-key",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
        }

    def test_local_rails_block_destructive_commands(self):
        # Known destructive commands must be flagged as DANGEROUS immediately by local rails
        destructive = [
            ("CMD", "rm -rf /"),
            ("CMD", "format C: /FS:NTFS"),
            ("POWERSHELL", "Remove-Item -Recurse -Force C:\\Windows"),
            ("CMD", "del /s /q C:\\Windows\\System32"),
            ("CMD", "reg delete HKLM\\Software /f"),
            ("RUN_CODE", "import os; os.system('rm -rf /')"),
        ]
        for tool, cmd in destructive:
            is_safe, reason = guardian_agent.review_command_safety(self.cfg, tool, cmd)
            self.assertFalse(is_safe, f"Expected {cmd} to be dangerous")
            self.assertIn("DANGEROUS", reason.upper())

    def test_read_only_tools_are_classified_safe(self):
        read_only = [
            ("LIST_FILES", "."),
            ("READ_FILE", "README.md"),
            ("GIT", "status"),
            ("CMD", "dir"),
        ]
        for tool, cmd in read_only:
            is_safe, reason = guardian_agent.review_command_safety(self.cfg, tool, cmd)
            self.assertTrue(is_safe, f"Expected {tool} {cmd} to be safe")
            self.assertIn("SAFE", reason.upper())

    def test_llm_safety_evaluation_safe(self):
        mock_reply = json.dumps({"status": "SAFE", "reason": "Purely prints greetings to stdout"})
        with patch("guardian_agent._call_guardian_llm", return_value=mock_reply):
            is_safe, reason = guardian_agent.review_command_safety(self.cfg, "RUN_CODE", "python | print('Hello world')")
            self.assertTrue(is_safe)
            self.assertIn("prints greetings", reason)

    def test_llm_safety_evaluation_dangerous(self):
        mock_reply = json.dumps({"status": "DANGEROUS", "reason": "Modifies system background process"})
        with patch("guardian_agent._call_guardian_llm", return_value=mock_reply):
            is_safe, reason = guardian_agent.review_command_safety(self.cfg, "POWERSHELL", "Stop-Process -Name explorer")
            self.assertFalse(is_safe)
            self.assertIn("Modifies system", reason)

    def test_llm_failure_fails_closed_as_dangerous(self):
        with patch("guardian_agent._call_guardian_llm", side_effect=Exception("Network error")):
            is_safe, reason = guardian_agent.review_command_safety(self.cfg, "RUN_CODE", "python | script.py")
            self.assertFalse(is_safe)
            self.assertIn("fail-closed", reason.lower())


if __name__ == "__main__":
    unittest.main()
