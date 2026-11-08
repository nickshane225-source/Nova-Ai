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
            server.execute_model_tags(tags, cfg, source="pc", mode="developer")
        
        events = audit_logger.get_recent_audit_events(limit=5)
        self.assertTrue(any(e["tool"] == "READ_FILE" and e["status"] == "EXECUTED" for e in events))

    def test_HIGH_06_audit_panel_fields_brackets_colors_and_ordering(self):
        """Regression test for HIGH-06:
        Verify web/app.js Audit Log panel:
        - reads ev.guardian (with fallback to ev.guardian_verdict)
        - normalizes '[SAFE]' / 'SAFE' and '[DANGEROUS]' / 'DANGEROUS' without bracket mismatch
        - colors EXECUTED / APPROVED / ALLOWED rows green (#2ed573), AWAITING_CONFIRMATION amber (#ffa502), DENIED / BLOCKED red (#ff4757)
        - renders events in reverse chronological order (newest first via .slice().reverse())
        """
        app_js = (Path(__file__).resolve().parent / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("ev.guardian || ev.guardian_verdict", app_js)
        self.assertIn("events.slice().reverse()", app_js)
        self.assertIn('stUpper === "EXECUTED"', app_js)
        self.assertIn('verdictNorm === "SAFE"', app_js)
        self.assertNotIn("verdict === '[SAFE]'", app_js)

    def test_HIGH_07_get_recent_audits_last_n_and_conversational_approvals_logged(self):
        """Regression test for HIGH-07:
        - get_recent_audits(limit=N) returns the LAST N lines
        - Every real approval and denial path (conversational 'yes'/'no' in _chat_inner, /api/confirm, Telegram, Discord)
          writes an audit entry preserving the Guardian verdict.
        """
        import server
        import telegram_gateway
        import discord_gateway

        # 1. Write 120 events and verify get_recent_audits(limit=25) returns the LAST 25 (95..119)
        for i in range(120):
            audit_logger.log_audit_event(
                channel="pc",
                tool=f"SEQ_{i}",
                preview=f"cmd_{i}",
                guardian_verdict="SAFE",
                status="EXECUTED",
            )
        last_25 = audit_logger.get_recent_audits(limit=25)
        self.assertEqual(len(last_25), 25)
        self.assertEqual(last_25[0]["tool"], "SEQ_95")
        self.assertEqual(last_25[-1]["tool"], "SEQ_119")

        # 2. Conversational approval ('yes') and denial ('no') through real server.chat()
        cfg = dict(server.DEFAULT_CONFIG)
        cfg["confirm_destructive"] = True

        with server.LOCK:
            server.HISTORIES["developer"].clear()
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()

        # Step 2a: Trigger a pending action via chat() and approve conversationally with "yes"
        with patch("server.get_config", return_value=cfg), \
             patch("server.call_llm", return_value="Let me run that. [[CMD: echo hello_audit_approve]]"), \
             patch("server.run_skill", return_value="hello_audit_approve") as mock_skill:
            res1 = server.chat("run echo", source="pc", mode="developer")
            self.assertIsNotNone(res1.get("pending"))

            res_yes = server.chat("yes", source="pc", mode="developer")
            self.assertIn("Approved and executed CMD", res_yes.get("reply", ""))
            mock_skill.assert_called_once()

        recent_after_yes = audit_logger.get_recent_audits(limit=5)
        self.assertTrue(
            any(e["tool"] == "CMD" and e["status"] == "APPROVED" and e["channel"] == "pc" and e["guardian"] in ("SAFE", "DANGEROUS") for e in recent_after_yes),
            f"Expected conversational APPROVED audit event with Guardian verdict, got: {recent_after_yes}"
        )

        # Step 2b: Trigger a pending action via chat() and deny conversationally with "no"
        with patch("server.get_config", return_value=cfg), \
             patch("server.call_llm", return_value="Let me run that. [[CMD: echo hello_audit_deny]]"), \
             patch("server.run_skill", return_value="should_not_run") as mock_skill_deny:
            res2 = server.chat("run echo 2", source="pc", mode="developer")
            self.assertIsNotNone(res2.get("pending"))

            res_no = server.chat("no", source="pc", mode="developer")
            self.assertIn("Action CMD was cancelled", res_no.get("reply", ""))
            mock_skill_deny.assert_not_called()

        recent_after_no = audit_logger.get_recent_audits(limit=5)
        self.assertTrue(
            any(e["tool"] == "CMD" and e["status"] == "DENIED" and e["channel"] == "pc" and "hello_audit_deny" in e["preview"] for e in recent_after_no),
            f"Expected conversational DENIED audit event, got: {recent_after_no}"
        )

        # 3. Real /api/confirm approval and denial preserve guardian verdict
        exec_res = server.execute_model_tags([("CMD", "echo web_confirm_test", 0, 10)], cfg, source="pc", mode="developer")
        p_id = exec_res["pending_info"]["id"]

        class DummyConfirmHandler(server.Handler):
            def __init__(self, payload):
                self.path = "/api/confirm"
                self.headers = {
                    "Host": "127.0.0.1:8765",
                    "Origin": "http://127.0.0.1:8765",
                    "Cookie": f"nova_session={server.SESSION_TOKEN}",
                    "X-Nova-Token": server.API_SESSION_TOKEN,
                }
                self.command = "POST"
                self.requestline = "POST /api/confirm HTTP/1.1"
                self._payload = payload
                self.sent_code = None
                self.sent_body = None
            def _body(self):
                return self._payload
            def _send(self, code, body, ctype="application/json"):
                self.sent_code = code
                self.sent_body = body

        with patch("server.get_config", return_value=cfg), \
             patch("server.run_skill", return_value="web_confirm_ok"):
            h = DummyConfirmHandler({"id": p_id, "approve": True})
            h.do_POST()
            self.assertEqual(h.sent_code, 200)

        recent_web = audit_logger.get_recent_audits(limit=5)
        self.assertTrue(
            any(e["tool"] == "CMD" and e["status"] == "APPROVED" and "web_confirm_test" in e["preview"] and e["guardian"] in ("SAFE", "DANGEROUS") for e in recent_web),
            f"Expected /api/confirm APPROVED audit event with guardian verdict, got: {recent_web}"
        )

        # 4. Telegram & Discord gateway handle_remote_confirm log guardian verdict
        exec_tg = server.execute_model_tags([("CMD", "echo tg_confirm_test", 0, 10)], cfg, source="telegram", mode="developer")
        tg_id = exec_tg["pending_info"]["id"]
        with patch("server.get_config", return_value=cfg), \
             patch("server.run_skill", return_value="tg_ok"):
            telegram_gateway.handle_remote_confirm(tg_id, approve=False)

        exec_dc = server.execute_model_tags([("CMD", "echo dc_confirm_test", 0, 10)], cfg, source="discord", mode="developer")
        dc_id = exec_dc["pending_info"]["id"]
        with patch("server.get_config", return_value=cfg), \
             patch("server.run_skill", return_value="dc_ok"):
            discord_gateway.handle_remote_confirm(dc_id, approve=True)

        recent_gw = audit_logger.get_recent_audits(limit=6)
        self.assertTrue(any(e["channel"] == "telegram" and e["status"] == "DENIED" and e["guardian"] in ("SAFE", "DANGEROUS") for e in recent_gw))
        self.assertTrue(any(e["channel"] == "discord" and e["status"] == "APPROVED" and e["guardian"] in ("SAFE", "DANGEROUS") for e in recent_gw))


if __name__ == "__main__":
    unittest.main()
