"""
Unit tests for Task 1: Append-Only Security Audit Logger (audit_logger.py).
Zero third-party pip dependencies - Python standard library only.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import audit_logger


class TestAuditLogger(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.audit_file = Path(self.temp_dir.name) / "audit.jsonl"
        audit_logger.set_audit_file(self.audit_file)

    def tearDown(self):
        self.temp_dir.cleanup()
        audit_logger.set_audit_file(None)

    def test_log_audit_event_creates_file_and_appends_jsonl(self):
        self.assertFalse(self.audit_file.exists())
        
        entry1 = audit_logger.log_audit_event(
            channel="web",
            tool="CMD",
            preview="dir C:\\workspace",
            guardian_verdict="SAFE",
            status="EXECUTED"
        )
        self.assertTrue(self.audit_file.exists())
        self.assertEqual(entry1["channel"], "web")
        self.assertEqual(entry1["tool"], "CMD")
        self.assertEqual(entry1["guardian"], "SAFE")
        self.assertEqual(entry1["status"], "EXECUTED")
        self.assertIn("timestamp", entry1)

        entry2 = audit_logger.log_audit_event(
            channel="telegram",
            tool="RUN_CODE",
            preview="print('hello')",
            guardian_verdict="SAFE",
            status="APPROVED"
        )
        self.assertEqual(entry2["channel"], "telegram")

        # Read JSONL file directly and assert lines
        lines = [line.strip() for line in self.audit_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(lines), 2)
        parsed1 = json.loads(lines[0])
        parsed2 = json.loads(lines[1])
        self.assertEqual(parsed1["tool"], "CMD")
        self.assertEqual(parsed2["tool"], "RUN_CODE")

    def test_log_audit_event_masks_sensitive_secrets(self):
        sensitive_cmd = "git clone https://x-token-auth:ghp_1234567890abcdef@github.com/repo --sk-ant-api03-abcdef123456"
        entry = audit_logger.log_audit_event(
            channel="web",
            tool="GIT",
            preview=sensitive_cmd,
            guardian_verdict="DANGEROUS",
            status="BLOCKED"
        )
        self.assertNotIn("ghp_1234567890abcdef", entry["preview"])
        self.assertNotIn("sk-ant-api03-abcdef123456", entry["preview"])
        self.assertIn("[MASKED_SECRET]", entry["preview"])

    def test_read_recent_audit_events(self):
        for i in range(10):
            audit_logger.log_audit_event(
                channel="web",
                tool=f"TOOL_{i}",
                preview=f"arg_{i}",
                guardian_verdict="SAFE",
                status="EXECUTED"
            )
        recent = audit_logger.get_recent_audit_events(limit=5)
        self.assertEqual(len(recent), 5)
        self.assertEqual(recent[-1]["tool"], "TOOL_9")

    def test_server_execute_model_tags_logs_audit(self):
        import server
        cfg = dict(server.DEFAULT_CONFIG)
        cfg["confirm_destructive"] = False  # Allows execution without modal
        tags = [("READ_FILE", "test.txt", "", "")]
        with patch("server.run_skill", return_value="file content here"):
            server.execute_model_tags(tags, cfg, source="web", mode="developer")
        
        events = audit_logger.get_recent_audit_events(limit=5)
        self.assertTrue(any(e["tool"] == "READ_FILE" and e["status"] == "EXECUTED" for e in events))


if __name__ == "__main__":
    unittest.main()
