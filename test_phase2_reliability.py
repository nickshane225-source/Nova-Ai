"""
Unit tests for Phase 2: Reliability, Error Handling, and Mode Isolation.
Zero pip dependencies - Python standard library only.
"""
import unittest
import os
import sys
import time
import ctypes
import platform
from unittest.mock import patch, MagicMock

import server
import scheduler_engine

class TestPhase2Reliability(unittest.TestCase):
    def setUp(self):
        with server.LOCK:
            server.HISTORIES["developer"].clear()
            server.HISTORIES["cyber"].clear()

    # --- 2A. THREAD-SAFE HISTORY RESET ---
    def test_history_reset_isolation(self):
        with server.LOCK:
            server.HISTORIES["developer"].append({"role": "user", "content": "dev msg"})
            server.HISTORIES["cyber"].append({"role": "user", "content": "cyber msg"})

        class MockReq:
            def __init__(self, body):
                self.headers = {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"}
                self.command = "POST"
                self.path = "/api/reset"
                self._test_body = body
                self.status = None
                self.data = None
            _local_only = server.Handler._local_only
            do_POST = server.Handler.do_POST
            def _body(self):
                return self._test_body
            def _send(self, status, data, ctype="application/json"):
                self.status = status
                self.data = data

        # Reset only developer
        req_dev = MockReq({"mode": "developer"})
        req_dev.do_POST()
        self.assertEqual(req_dev.status, 200)
        with server.LOCK:
            self.assertEqual(len(server.HISTORIES["developer"]), 0)
            self.assertEqual(len(server.HISTORIES["cyber"]), 1)

        # Reset cyber
        req_cyber = MockReq({"mode": "cyber"})
        req_cyber.do_POST()
        self.assertEqual(req_cyber.status, 200)
        with server.LOCK:
            self.assertEqual(len(server.HISTORIES["developer"]), 0)
            self.assertEqual(len(server.HISTORIES["cyber"]), 0)

    # --- 2B. MODE-ISOLATED SCHEDULER ACTIONS ---
    def test_scheduler_mode_isolation(self):
        sched = scheduler_engine.SchedulerEngine()
        t_dev = sched.add_timer("1s", "Dev timer", mode="developer")
        t_cyber = sched.add_timer("1s", "Cyber timer", mode="cyber")
        auto_cyber = sched.add_recurring_task("every 1s", "SYSTEM: stats", "Cyber Auto", mode="cyber")

        time.sleep(1.2)
        sched.check_timers()
        notifs = sched.get_pending_notifications()

        dev_notifs = [n for n in notifs if n.get("mode") == "developer"]
        cyber_notifs = [n for n in notifs if n.get("mode") == "cyber"]

        self.assertTrue(any("Dev timer" in n.get("message", "") for n in dev_notifs))
        self.assertTrue(any("Cyber timer" in n.get("message", "") for n in cyber_notifs))
        self.assertTrue(any("Cyber Auto" in n.get("message", "") for n in cyber_notifs))

    # --- 2C. BROWSER ROUTES CATCH CDP CRASHES CLEANLY ---
    def test_browser_routes_catch_crashes(self):
        class MockReq:
            def __init__(self, path, body):
                self.headers = {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"}
                self.command = "POST"
                self.path = path
                self._test_body = body
                self.status = None
                self.data = None
            _local_only = server.Handler._local_only
            do_POST = server.Handler.do_POST
            def _body(self):
                return self._test_body
            def _send(self, status, data, ctype="application/json"):
                self.status = status
                self.data = data

        with patch("nova_browser.open_or_activate", side_effect=RuntimeError("CDP connection lost")):
            req = MockReq("/api/browser/open", {"url": "https://example.com"})
            req.do_POST()
            self.assertEqual(req.status, 200)
            self.assertFalse(req.data["ok"])
            self.assertIn("CDP connection lost", req.data["error"])

        with patch("nova_browser.activate_tab", side_effect=RuntimeError("Tab closed unexpectedly")):
            req = MockReq("/api/browser/activate", {"tab_id": "123"})
            req.do_POST()
            self.assertEqual(req.status, 200)
            self.assertFalse(req.data["ok"])
            self.assertIn("Tab closed unexpectedly", req.data["error"])

    # --- 2D. NOTIFICATION CAP AT 100 ---
    def test_notification_cap(self):
        sched = scheduler_engine.SchedulerEngine()
        for i in range(150):
            sched._push_notification({"id": i, "title": f"T{i}", "message": f"M{i}", "type": "test"})
        self.assertEqual(len(sched.notifications), 100)
        self.assertEqual(sched.notifications[0]["id"], 50)
        self.assertEqual(sched.notifications[-1]["id"], 149)

    # --- 2E. 64-BIT CTYPES HANDLES ---
    def test_win32_ctypes_signatures(self):
        if platform.system() != "Windows":
            self.skipTest("Windows-specific ctypes test")
        self.assertIsNotNone(server.ctypes)
        u32 = server.ctypes.windll.user32
        self.assertEqual(u32.GetForegroundWindow.restype, server.ctypes.c_void_p)
        self.assertEqual(u32.GetWindowTextLengthW.argtypes, [server.ctypes.c_void_p])
        self.assertEqual(u32.GetWindowTextW.argtypes, [server.ctypes.c_void_p, server.ctypes.c_wchar_p, server.ctypes.c_int])

    # --- 2F. STRICT CONFIG VALIDATION ---
    def test_config_unknown_key_rejected(self):
        class MockReq:
            def __init__(self, body):
                self.headers = {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"}
                self.command = "POST"
                self.path = "/api/config"
                self._test_body = body
                self.status = None
                self.data = None
            _local_only = server.Handler._local_only
            do_POST = server.Handler.do_POST
            def _body(self):
                return self._test_body
            def _send(self, status, data, ctype="application/json"):
                self.status = status
                self.data = data

        req = MockReq({"malicious_unknown_key": "injected_val"})
        req.do_POST()
        self.assertEqual(req.status, 400)
        self.assertIn("Unknown configuration key", req.data["error"])

    def test_config_voice_bounds_clamped(self):
        class MockReq:
            def __init__(self, body):
                self.headers = {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"}
                self.command = "POST"
                self.path = "/api/config"
                self._test_body = body
                self.status = None
                self.data = None
            _local_only = server.Handler._local_only
            do_POST = server.Handler.do_POST
            def _body(self):
                return self._test_body
            def _send(self, status, data, ctype="application/json"):
                self.status = status
                self.data = data

        # Out of bounds voice settings should be clamped
        req = MockReq({"voice_rate": 5.0, "voice_pitch": -1.0, "voice_volume": 2.5})
        with patch("server.save_json") as mock_save:
            req.do_POST()
            self.assertEqual(req.status, 200)
            saved_cfg = mock_save.call_args[0][1]
            self.assertEqual(saved_cfg["voice_rate"], 2.0)
            self.assertEqual(saved_cfg["voice_pitch"], 0.0)
            self.assertEqual(saved_cfg["voice_volume"], 1.0)

    def test_config_max_tokens_validation(self):
        class MockReq:
            def __init__(self, body):
                self.headers = {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"}
                self.command = "POST"
                self.path = "/api/config"
                self._test_body = body
                self.status = None
                self.data = None
            _local_only = server.Handler._local_only
            do_POST = server.Handler.do_POST
            def _body(self):
                return self._test_body
            def _send(self, status, data, ctype="application/json"):
                self.status = status
                self.data = data

        # Under 256 rejected
        req_low = MockReq({"max_tokens": 100})
        req_low.do_POST()
        self.assertEqual(req_low.status, 400)

        # Over 8192 rejected
        req_high = MockReq({"max_tokens": 10000})
        req_high.do_POST()
        self.assertEqual(req_high.status, 400)

        # Valid accepted
        req_valid = MockReq({"max_tokens": 4096})
        with patch("server.save_json") as mock_save:
            req_valid.do_POST()
            self.assertEqual(req_valid.status, 200)
            saved_cfg = mock_save.call_args[0][1]
            self.assertEqual(saved_cfg["max_tokens"], 4096)

    def test_state_masks_secrets(self):
        class MockReq:
            def __init__(self):
                self.headers = {"Host": "127.0.0.1:8765"}
                self.path = "/api/state"
                self.status = None
                self.data = None
            _local_only = server.Handler._local_only
            do_GET = server.Handler.do_GET
            def _send(self, status, data, ctype="application/json"):
                self.status = status
                self.data = data

        with patch("server.get_config", return_value={
            "api_key": "sk-super-secret-key",
            "remote_token": "token-secret-123",
            "remote_key": "C:\\path\\to\\privkey.pem",
            "provider": "anthropic",
            "character": "jarvis"
        }):
            req = MockReq()
            req.do_GET()
            self.assertEqual(req.status, 200)
            cfg = req.data["config"]
            self.assertNotIn("api_key", cfg)
            self.assertNotIn("remote_token", cfg)
            self.assertNotIn("remote_key", cfg)
            self.assertTrue(cfg["has_key"])

    # --- 2G. GIT SUBCOMMAND FLAG ALLOWLIST (PHASE 2A) ---
    def test_git_subcommand_flag_allowlist(self):
        # 1. Valid flags and commands allowed
        with patch("server.run_sandboxed_process", return_value=(0, "ok", "")) as mock_proc:
            for valid_cmd in [
                "status", "status -s", "status -b", "status -u",
                "diff --stat", "diff -p",
                "log -n 5", "log --oneline", "log --oneline -n 5",
                "add -A", "commit -m 'Initial commit'", "commit -m msg",
                "branch -a", "checkout -b new-feat", "switch -c new-feat",
                "init -b main", "restore --staged",
                "pull -u", "push --force"
            ]:
                res = server.skill_git(valid_cmd)
                self.assertNotIn("is not permitted", res)
                self.assertNotIn("disallowed for security", res)

            # Verify safe_configs includes core.hooksPath= override
            called_cmd = mock_proc.call_args[0][0]
            self.assertIn("core.hooksPath=", " ".join(called_cmd))

        # 2. Unlisted/dangerous flags rejected
        for bad_cmd in [
            "log --output=x",
            "diff --no-index a b",
            "push --receive-pack=evil",
            "fetch --upload-pack=evil",
            "-c x=y status",
            "status --output=hack.txt",
            "diff --paginate",
            "log --exec=calc.exe",
            "checkout --no-index",
            "commit --ext-diff",
            "clone -o hack"
        ]:
            res = server.skill_git(bad_cmd)
            self.assertIn("disallowed for security", res)

        # 3. Path outside workspace rejected
        outside_p = r"C:\Windows\System32" if platform.system() == "Windows" else "/etc"
        res_path = server.skill_git(f"add {outside_p}")
        self.assertEqual(res_path, "Path is outside the Nova workspace.")

        # 4. Dangerous URLs rejected
        for bad_url in [
            "clone file:///x",
            "clone file:///etc/passwd",
            "clone ext::sh -c evil",
            "remote get-url ftp://bad.com"
        ]:
            res_url = server.skill_git(bad_url)
            self.assertIn("is not permitted", res_url)

    # --- 2H. CONFIRMATION BINDING & RESTRICTIONS (PHASE 2B) ---
    def test_confirmation_binding_rules(self):
        with patch("server.call_llm", return_value="Fallback"):
            with server.PENDING_LOCK:
                server.PENDING_ACTIONS.clear()

            # Rule (d): Reject sentences longer than 3 words
            with server.PENDING_LOCK:
                server.PENDING_ACTIONS["act1"] = {
                    "id": "act1", "name": "NOTE", "arg": "Test", "mode": "developer",
                    "source": "pc", "created_at": time.time(), "expires_at": time.time() + 120,
                    "reason": "Confirm note", "is_tainted": False
                }
            with server.LOCK:
                server.HISTORIES["developer"].append({"role": "assistant", "content": "[Action Requires Confirmation: Confirm note]"})

            res_long = server.chat("yes please do it right now my friend", source="pc", mode="developer")
            self.assertNotIn("Approved and executed NOTE", res_long["reply"])
            with server.PENDING_LOCK:
                self.assertIn("act1", server.PENDING_ACTIONS)

            # Rule (e): Reject if multiple pending actions in that mode
            with server.PENDING_LOCK:
                server.PENDING_ACTIONS["act2"] = {
                    "id": "act2", "name": "NOTE", "arg": "Test 2", "mode": "developer",
                    "source": "pc", "created_at": time.time(), "expires_at": time.time() + 120,
                    "reason": "Confirm note 2", "is_tainted": False
                }
            with server.LOCK:
                server.HISTORIES["developer"] = [{"role": "assistant", "content": "[Action Requires Confirmation: Confirm note]"}]
            res_multi = server.chat("yes", source="pc", mode="developer")
            self.assertNotIn("Approved and executed NOTE", res_multi["reply"])

            # Clean to 1 pending action
            with server.PENDING_LOCK:
                server.PENDING_ACTIONS.clear()
                server.PENDING_ACTIONS["act1"] = {
                    "id": "act1", "name": "NOTE", "arg": "Test", "mode": "developer",
                    "source": "pc", "created_at": time.time() - 70, # Older than 60s
                    "expires_at": time.time() + 120, "reason": "Confirm note", "is_tainted": False
                }
            with server.LOCK:
                server.HISTORIES["developer"] = [{"role": "assistant", "content": "[Action Requires Confirmation: Confirm note]"}]
            # Rule (c): Reject if older than 60s
            res_old = server.chat("yes", source="pc", mode="developer")
            self.assertNotIn("Approved and executed NOTE", res_old["reply"])

            # Rule (b): Desktop cannot approve phone action
            with server.PENDING_LOCK:
                server.PENDING_ACTIONS.clear()
                server.PENDING_ACTIONS["act_phone"] = {
                    "id": "act_phone", "name": "NOTE", "arg": "Test", "mode": "developer",
                    "source": "phone", "created_at": time.time(),
                    "expires_at": time.time() + 120, "reason": "Confirm note", "is_tainted": False
                }
            with server.LOCK:
                server.HISTORIES["developer"] = [{"role": "assistant", "content": "[Action Requires Confirmation: Confirm note]"}]
            res_cross = server.chat("yes", source="pc", mode="developer")
            self.assertNotIn("Approved and executed NOTE", res_cross["reply"])

            # Tainted turn or mobile source requires desktop UI Allow button
            with server.PENDING_LOCK:
                server.PENDING_ACTIONS.clear()
                server.PENDING_ACTIONS["act_taint"] = {
                    "id": "act_taint", "name": "NOTE", "arg": "Test", "mode": "developer",
                    "source": "pc", "created_at": time.time(),
                    "expires_at": time.time() + 120, "reason": "Confirm note", "is_tainted": True
                }
            with server.LOCK:
                server.HISTORIES["developer"] = [{"role": "assistant", "content": "[Action Requires Confirmation: Confirm note]"}]
            res_tainted = server.chat("yes", source="pc", mode="developer")
            self.assertIn("requires your confirmation via the desktop Allow button", res_tainted["reply"])
            with server.PENDING_LOCK:
                self.assertIn("act_taint", server.PENDING_ACTIONS)

            # Valid approval: correct "yes" within 60 seconds after prompt approves
            with server.PENDING_LOCK:
                server.PENDING_ACTIONS.clear()
                server.PENDING_ACTIONS["act_valid"] = {
                    "id": "act_valid", "name": "NOTE", "arg": "Test Title | Test Note Content", "mode": "developer",
                    "source": "pc", "created_at": time.time(),
                    "expires_at": time.time() + 120, "reason": "Confirm note", "is_tainted": False
                }
            with server.LOCK:
                server.HISTORIES["developer"] = [{"role": "assistant", "content": "[Action Requires Confirmation: Confirm note]"}]
            res_approve = server.chat("yes", source="pc", mode="developer")
            self.assertIn("Approved and executed NOTE", res_approve["reply"])

            # Expired pending is rejected
            with server.PENDING_LOCK:
                server.PENDING_ACTIONS.clear()
                server.PENDING_ACTIONS["act_expired"] = {
                    "id": "act_expired", "name": "NOTE", "arg": "Test Title | Test Note Content", "mode": "developer",
                    "source": "pc", "created_at": time.time() - 150,
                    "expires_at": time.time() - 30, "reason": "Confirm note", "is_tainted": False
                }
            with server.LOCK:
                server.HISTORIES["developer"] = [{"role": "assistant", "content": "[Action Requires Confirmation: Confirm note]"}]
            res_exp = server.chat("yes", source="pc", mode="developer")
            self.assertNotIn("Approved and executed NOTE", res_exp["reply"])

            # Real pending action ID generation from execute_model_tags
            res_tags = server.execute_model_tags([("RUN_CODE", "python | 1", 0, 10)], server.get_config(), source="pc", mode="developer")
            self.assertIsNotNone(res_tags.get("pending_info"))
            real_act_id = res_tags["pending_info"]["id"]
            self.assertEqual(len(real_act_id), 16)
            int(real_act_id, 16)  # validates hexadecimal
            self.assertIn(real_act_id, server.PENDING_ACTIONS)

    # --- 2I. TOOL CLASSIFICATION & DENY BY DEFAULT (PHASE 2C) ---
    def test_tool_classification_and_deny_by_default(self):
        cfg = dict(server.DEFAULT_CONFIG)

        # 1. ALWAYS_CONFIRM tools
        for tool, arg in [
            ("BROWSER_WHATSAPP", "John | hello"),
            ("BROWSER_TELEGRAM", "Chat | hello"),
            ("CLOSE_APP", "notepad"),
            ("SYSTEM", "empty_recycle_bin"),
            ("SCHEDULE_AUTO", "every 1h | SYSTEM: stats"),
            ("AUTOMATE", "daily | NOTE: check"),
            ("FORGET", "my secret note"),
            ("DELETE_NOTE", "my note"),
            ("SMART_HOME", "http://ha/api | POST | {}"),
            ("SMART_HOME", "http://ha/api | DELETE"),
        ]:
            req, reason = server.check_tool_confirmation_required(cfg, tool, arg, is_tainted=False, source="pc")
            self.assertTrue(req, f"{tool} should require confirmation")

        # SMART_HOME GET does not require confirmation when untainted desktop
        req_get, _ = server.check_tool_confirmation_required(cfg, "SMART_HOME", "http://ha/api | GET", is_tainted=False, source="pc")
        self.assertFalse(req_get)

        # 2. Deny by default: unknown or unlisted tool requires confirmation
        req_unknown, reason = server.check_tool_confirmation_required(cfg, "UNKNOWN_CUSTOM_TOOL", "arg", is_tainted=False, source="pc")
        self.assertTrue(req_unknown)
        self.assertIn("requires user confirmation", reason)

        # 3. NFKC Normalization of tags
        full_width_tag = "ＣＭＤ"
        req_fw, _ = server.check_tool_confirmation_required(cfg, full_width_tag, "dir", is_tainted=False, source="pc")
        self.assertTrue(req_fw)

    # --- 2J. TAINT SOURCES & PERSISTENCE (PHASE 2D) ---
    def test_taint_sources_expansion(self):
        for tool in ["BRIEFING", "BROWSER_TABS", "SEARCH_NOTES", "ACTIVE_WINDOW", "LIST_FILES", "READ_FILE", "VISION"]:
            self.assertIn(tool, server.TAINT_SOURCE_TOOLS)

        # Mobile input initiates turn tainted
        with patch("server.call_llm", return_value="Here is info: [[NOTE: Title | Text]]"):
            res = server.chat("write note", source="phone", mode="developer")
            # Turn started tainted because source="phone"
            self.assertIn("actions", res)

    # --- 2K. PROTECT /api/config SENSITIVE KEYS (PHASE 2E) ---
    def test_protect_api_config_sensitive_keys(self):
        class MockReq:
            def __init__(self, body):
                self.headers = {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"}
                self.command = "POST"
                self.path = "/api/config"
                self._test_body = body
                self.status = None
                self.data = None
            _local_only = server.Handler._local_only
            do_POST = server.Handler.do_POST
            def _body(self):
                return self._test_body
            def _send(self, status, data, ctype="application/json"):
                self.status = status
                self.data = data

        # 1. Modifying sensitive key without confirm_token returns need_confirm: true and a token
        req1 = MockReq({"confirm_destructive": False})
        req1.do_POST()
        self.assertEqual(req1.status, 200)
        self.assertTrue(req1.data.get("need_confirm"))
        self.assertIn("confirm_destructive", req1.data.get("keys", []))
        token = req1.data.get("token")
        self.assertTrue(bool(token))

        # 2. Resending with that token allows the modification
        req2 = MockReq({"confirm_destructive": False, "confirm_token": token})
        with patch("server.save_config") as mock_save:
            req2.do_POST()
            self.assertEqual(req2.status, 200)
            self.assertTrue(req2.data.get("ok"))
            mock_save.assert_called_once()
            self.assertFalse(mock_save.call_args[0][0]["confirm_destructive"])

        # 3. Mobile remote (source="phone") is strictly rejected (403)
        req_phone = MockReq({"confirm_destructive": False, "source": "phone"})
        req_phone.do_POST()
        self.assertEqual(req_phone.status, 403)
        self.assertIn("Modifying security settings is not allowed from mobile remote", req_phone.data["error"])

if __name__ == "__main__":
    unittest.main()
