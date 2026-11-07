"""
Comprehensive Audit & Deep Fuzzing Test Suite for Nova AI.
Tests every API endpoint, security barrier, edge case, and boundary condition.
Zero third-party pip dependencies - Python standard library only.
"""
import io
import json
import os
import sys
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Ensure local imports resolve
sys.path.insert(0, str(Path(__file__).resolve().parent))
import server
import memory_engine
import scheduler_engine
import guardian_agent
import plan_mode
import telegram_gateway
import integrations


class TestComprehensiveAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.SilentThreadingHTTPServer.allow_reuse_address = True
        cls.port = 8799
        cls.server = server.SilentThreadingHTTPServer(("127.0.0.1", cls.port), server.Handler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.shutdown()
            cls.server.server_close()
        except Exception:
            pass

    def _req(self, path, method="GET", data=None, headers=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        hdrs = {
            "Host": f"127.0.0.1:{self.port}",
            "Origin": f"http://127.0.0.1:{self.port}",
            "Sec-Fetch-Site": "same-origin",
        }
        if headers:
            hdrs.update(headers)
        body_bytes = None
        if data is not None:
            if isinstance(data, (dict, list)):
                body_bytes = json.dumps(data).encode("utf-8")
                hdrs["Content-Type"] = "application/json"
            elif isinstance(data, bytes):
                body_bytes = data
            elif isinstance(data, str):
                body_bytes = data.encode("utf-8")

        req = urllib.request.Request(url, data=body_bytes, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = resp.read()
                try:
                    parsed = json.loads(raw.decode("utf-8"))
                except Exception:
                    parsed = raw.decode("utf-8", errors="replace")
                return resp.status, parsed
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except Exception:
                parsed = raw.decode("utf-8", errors="replace")
            return e.code, parsed

    # --- 1. HOST HEADER & CSRF PROTECTION ---
    def test_dns_rebinding_rejected(self):
        code, _ = self._req("/api/state", headers={"Host": "attacker.com"})
        self.assertEqual(code, 403)

    def test_cross_site_fetch_rejected(self):
        code, _ = self._req("/api/state", headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(code, 403)

    # --- 2. GET ENDPOINTS NORMAL & CORNER CASES ---
    def test_get_api_state(self):
        code, res = self._req("/api/state")
        self.assertEqual(code, 200)
        self.assertIn("config", res)
        self.assertNotIn("api_key", res["config"])  # Secret not exposed

    def test_get_api_news(self):
        code, res = self._req("/api/news")
        self.assertEqual(code, 200)
        self.assertIsInstance(res, list)

    def test_get_api_activity(self):
        code, res = self._req("/api/activity")
        self.assertEqual(code, 200)
        self.assertIn("busy", res)

    def test_get_api_browser_status(self):
        code, res = self._req("/api/browser/status")
        self.assertEqual(code, 200)

    def test_get_api_events_malformed_after(self):
        code, res = self._req("/api/events?after=not_a_number")
        self.assertEqual(code, 200)
        self.assertIn("events", res)

    def test_get_api_notifications(self):
        code, res = self._req("/api/notifications")
        self.assertEqual(code, 200)

    def test_get_api_timers(self):
        code, res = self._req("/api/timers")
        self.assertEqual(code, 200)

    def test_get_api_automations(self):
        code, res = self._req("/api/automations")
        self.assertEqual(code, 200)

    def test_get_api_skills(self):
        code, res = self._req("/api/skills?mode=developer")
        self.assertEqual(code, 200)
        code2, res2 = self._req("/api/skills?mode=cyber")
        self.assertEqual(code2, 200)

    def test_get_api_notes_empty_and_unicode(self):
        code, res = self._req("/api/notes?q=")
        self.assertEqual(code, 200)
        code2, res2 = self._req("/api/notes?q=%E0%A6%AC%E0%A6%BE%E0%A6%82%E0%A6%B2%E0%A6%BE")
        self.assertEqual(code2, 200)

    def test_get_api_audit(self):
        code, res = self._req("/api/audit?limit=10")
        self.assertEqual(code, 200)
        self.assertIn("events", res)

    def test_get_favicon_ico(self):
        code, res = self._req("/favicon.ico")
        self.assertIn(code, (200, 204))

    # --- 3. POST ENDPOINTS INPUT VALIDATION & FUZZING ---
    def test_post_chat_empty_body(self):
        code, res = self._req("/api/chat", method="POST", data={})
        self.assertEqual(code, 400)

    def test_post_chat_malformed_json(self):
        code, res = self._req("/api/chat", method="POST", data="this is not json", headers={"Content-Type": "application/json"})
        self.assertEqual(code, 400)

    def test_post_chat_huge_input(self):
        huge_text = "hello " * 20000
        code, res = self._req("/api/chat", method="POST", data={"message": huge_text})
        self.assertEqual(code, 413)

    def test_post_config_unknown_key_rejected(self):
        code, res = self._req("/api/config", method="POST", data={"malicious_injected_key": "val"})
        self.assertEqual(code, 400)
        self.assertIn("Unknown configuration key", res.get("error", ""))

    def test_post_config_invalid_numbers(self):
        code, res = self._req("/api/config", method="POST", data={"run_code_trusted_minutes": "not_an_int"})
        self.assertEqual(code, 400)

    def test_post_confirm_nonexistent_action(self):
        code, res = self._req("/api/confirm", method="POST", data={"id": "nonexistent_id", "approve": True})
        self.assertEqual(code, 404)

    # --- 4. DELETE ENDPOINTS ---
    def test_delete_note_empty_body(self):
        code, res = self._req("/api/notes", method="DELETE", data={})
        self.assertEqual(code, 400)

    def test_delete_timer_nonexistent(self):
        code, res = self._req("/api/timers", method="DELETE", data={"id": 999999})
        self.assertEqual(code, 404)

    def test_delete_automation_nonexistent(self):
        code, res = self._req("/api/automations", method="DELETE", data={"id": 999999})
        self.assertEqual(code, 404)

    # --- 5. WORKSPACE BOUNDARY & WINDOWS RESERVED NAMES ---
    def test_workspace_reserved_device_names(self):
        for name in ("CON", "PRN", "AUX", "NUL", "COM1", "LPT1"):
            with self.assertRaises(ValueError):
                server.resolve_workspace_path(name)

    def test_workspace_blocks_sensitive_nova_files(self):
        with self.assertRaises(PermissionError):
            server.resolve_workspace_path(r"..\data\config.json")
        with self.assertRaises(PermissionError):
            server.resolve_workspace_path(r"..\data\nova_brain.db")

    # --- 6. GUARDIAN AI SAFETY REVIEWER BOUNDARIES ---
    def test_guardian_extreme_dangerous_inputs(self):
        commands = [
            ("RUN_CODE", "rm -rf / --no-preserve-root"),
            ("CMD", "format C: /y /q"),
            ("POWERSHELL", "Remove-Item -Recurse -Force C:\\Windows"),
            ("CMD", "echo %COMSPEC% > \\\\.\\physicaldrive0")
        ]
        for tool, cmd in commands:
            safe, reason = guardian_agent.review_command_safety({}, tool, cmd)
            self.assertFalse(safe, f"Expected dangerous for {cmd}")

    # --- 7. PLAN MODE ROBUSTNESS ---
    def test_plan_mode_empty_and_corrupt_tags(self):
        self.assertEqual(plan_mode.parse_plan_tag("")["steps"], [])
        self.assertEqual(plan_mode.parse_plan_tag("   ")["steps"], [])
        self.assertEqual(plan_mode.parse_plan_tag("Single Title")["steps"], [])

    # --- 8. EXTENSIONS & CONNECTOR APIS ---
    def test_diagnostics_endpoint(self):
        code, res = self._req("/api/diagnostics")
        self.assertEqual(code, 200)
        self.assertIsInstance(res, dict)
        self.assertIn("overall_status", res)
        self.assertIn("checks", res)

    def test_usage_endpoint(self):
        for route in ("/api/metrics/usage", "/api/usage"):
            code, res = self._req(route)
            self.assertEqual(code, 200)
            self.assertIsInstance(res, dict)
            self.assertIn("summary", res)
            self.assertIn("budget", res)

    def test_github_api_missing_repo(self):
        code, res = self._req("/api/github")
        self.assertEqual(code, 400)
        self.assertFalse(res.get("ok"))

        code_post, res_post = self._req("/api/github", method="POST", data={})
        self.assertEqual(code_post, 400)
        self.assertFalse(res_post.get("ok"))

    def test_github_api_error_handling(self):
        from unittest.mock import patch
        connector = integrations.get_integration("github")
        with patch.object(connector, "run", side_effect=RuntimeError("Simulated network outage")):
            code_get, res_get = self._req("/api/github?repo=pocketpaw/pocketpaw&action=info")
            self.assertEqual(code_get, 500)
            self.assertFalse(res_get.get("ok"))
            self.assertIn("GitHub connector error", res_get.get("error", ""))

            code_post, res_post = self._req("/api/github", method="POST", data={"repo": "pocketpaw/pocketpaw", "action": "info"})
            self.assertEqual(code_post, 500)
            self.assertFalse(res_post.get("ok"))
            self.assertIn("GitHub connector error", res_post.get("error", ""))


if __name__ == "__main__":
    unittest.main()
