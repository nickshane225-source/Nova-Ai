"""
Unit tests for Phase 1: Security hardening and Confirmation Gate.
Zero pip dependencies - Python standard library only.
"""
import unittest
import os
import sys
import time
import secrets
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import server
import scheduler_engine
import guardian_agent

class TestPhase1Security(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(server.DEFAULT_CONFIG)
        self.cfg["confirm_destructive"] = True
        self.cfg["remote_allow_dangerous"] = False
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()
        with server.FAILS_LOCK:
            server.FAILS.clear()
        server.CONVERSATION_TAINT.clear()
        with server.WORKSPACE_WRITES_LOCK:
            server.WORKSPACE_WRITES_HISTORY.clear()
        server.SESSION_WORKSPACE_WRITES_COUNT = 0
        with server.WORKSPACE_WRITES_LOCK:
            server.WORKSPACE_WRITES_HISTORY.clear()
            server.SESSION_WORKSPACE_WRITES_COUNT = 0
        server.RUN_CODE_TRUST_STATE.reset()

    # --- 1A. GIT HARDENING ---
    def test_git_shell_operators_blocked(self):
        for bad in ["status; rm -rf /", "diff | cat", "status && whoami", "log > out.txt", "log `id`"]:
            res = server.skill_git(bad, cfg=self.cfg)
            self.assertIn("Refused: shell operators are not permitted", res)

    def test_git_flags_blocked(self):
        for bad in ["-C /etc status", "--git-dir=/root status", "--work-tree=C:\\ status", "-c user.name=evil status", "--exec-path=/bin status"]:
            res = server.skill_git(bad, cfg=self.cfg)
            self.assertIn("disallowed for security", res)

    def test_git_disallowed_subcommands(self):
        for bad in ["config --list", "filter-branch", "archive", "fast-export"]:
            res = server.skill_git(bad, cfg=self.cfg)
            self.assertIn("is not permitted", res)

    def test_git_remote_modification_blocked(self):
        res = server.skill_git("remote add evil https://evil.com", cfg=self.cfg)
        self.assertTrue("is not permitted" in res or "disallowed" in res)
        res = server.skill_git("remote set-url origin https://evil.com", cfg=self.cfg)
        self.assertTrue("is not permitted" in res or "disallowed" in res)

    def test_git_allowed_subcommands_syntax(self):
        # status, diff, log, add, etc. should pass through git parser
        with patch("server.run_sandboxed_process", return_value=(0, "On branch master\nnothing to commit", "")):
            res = server.skill_git("status", cfg=self.cfg)
            self.assertIn("On branch master", res)

    # --- 1B. PROCESS SANDBOX FOR RUN_CODE, CMD, POWERSHELL ---
    def test_sanitized_subprocess_env(self):
        with patch.dict(os.environ, {
            "API_KEY": "sk-secret123",
            "ANTHROPIC_TOKEN": "ant-token-456",
            "AWS_SECRET_ACCESS_KEY": "secret789",
            "DB_PASSWORD": "pass",
            "USER_CREDENTIALS": "creds",
            "PATH": os.environ.get("PATH", ""),
        }):
            env = server.get_sanitized_subprocess_env(server.WORKSPACE)
            for key in env:
                self.assertNotIn("KEY", key.upper())
                self.assertNotIn("TOKEN", key.upper())
                self.assertNotIn("SECRET", key.upper())
                self.assertNotIn("PASSWORD", key.upper())
                self.assertNotIn("CREDENTIAL", key.upper())
            self.assertEqual(env["HOME"], str(server.WORKSPACE.resolve()))
            self.assertEqual(env["USERPROFILE"], str(server.WORKSPACE.resolve()))

    def test_destructive_patterns_blocked(self):
        for cmd in ["format C:", "del /s C:\\Windows", "rd /s /q C:\\", "rm -rf /", "shutdown /r /t 0", "reg delete HKLM\\Software"]:
            res = server.skill_cmd(cmd, cfg=self.cfg)
            self.assertIn("blocked destructive system pattern", res)
            res_ps = server.skill_powershell(cmd, cfg=self.cfg)
            self.assertIn("blocked destructive system pattern", res_ps)

    # --- 1C. CONFIRMATION GATE & RISK TABLE ---
    def test_risk_table_always_confirm(self):
        # CMD & POWERSHELL always confirm
        req, _ = server.check_tool_confirmation_required(self.cfg, "CMD", "dir")
        self.assertTrue(req)
        req, _ = server.check_tool_confirmation_required(self.cfg, "POWERSHELL", "Get-Process")
        self.assertTrue(req)

        # Destructive SYSTEM actions
        req, _ = server.check_tool_confirmation_required(self.cfg, "SYSTEM", "shutdown")
        self.assertTrue(req)
        req, _ = server.check_tool_confirmation_required(self.cfg, "SYSTEM", "restart")
        self.assertTrue(req)
        req, _ = server.check_tool_confirmation_required(self.cfg, "SYSTEM", "stats")
        self.assertFalse(req)

        # GIT push/pull/clone
        req, _ = server.check_tool_confirmation_required(self.cfg, "GIT", "push origin main")
        self.assertTrue(req)
        # In Phase 2C deny-by-default, GIT status also requires confirmation
        req, _ = server.check_tool_confirmation_required(self.cfg, "GIT", "status")
        self.assertTrue(req)

        # ORGANIZE & DELETE_NOTE
        req, _ = server.check_tool_confirmation_required(self.cfg, "ORGANIZE", "C:\\test")
        self.assertTrue(req)
        req, _ = server.check_tool_confirmation_required(self.cfg, "DELETE_NOTE", "123")
        self.assertTrue(req)

    def test_taint_tracking_confirmation(self):
        # NOTE is in NO_CONFIRM_TOOLS -> safe when untainted desktop
        req, _ = server.check_tool_confirmation_required(self.cfg, "NOTE", "My note | content", is_tainted=False)
        self.assertFalse(req)
        # Requires confirm when tainted
        req, reason = server.check_tool_confirmation_required(self.cfg, "WRITE_FILE", "test.py | print(1)", is_tainted=True)
        self.assertTrue(req)
        self.assertIn("untrusted", reason)

    def test_run_code_always_confirm_and_trusted_minutes(self):
        # By default run_code_trusted_minutes is 0 -> always confirm
        for lang in ["python", "node", "cmd", "powershell", "shell"]:
            req, reason = server.check_tool_confirmation_required(self.cfg, "RUN_CODE", f"{lang} | print(1)", is_tainted=False)
            self.assertTrue(req)
            self.assertIn("Code execution requires user approval", reason)

        # Set trusted minutes to 5
        cfg_trust = dict(self.cfg)
        cfg_trust["run_code_trusted_minutes"] = 5

        # Before any approval, still requires confirm
        with server.RUN_CODE_TRUST_LOCK:
            server.LAST_RUN_CODE_APPROVED_TIME = 0.0
        req, _ = server.check_tool_confirmation_required(cfg_trust, "RUN_CODE", "python|print(1)", is_tainted=False, source="pc")
        self.assertTrue(req)

        # After approval, untainted desktop is auto-approved
        with server.RUN_CODE_TRUST_LOCK:
            server.LAST_RUN_CODE_APPROVED_TIME = time.time()
        req, _ = server.check_tool_confirmation_required(cfg_trust, "RUN_CODE", "python|print(1)", is_tainted=False, source="pc")
        self.assertFalse(req)

        # Tainted turn still requires confirm even with trusted window
        req_tainted, _ = server.check_tool_confirmation_required(cfg_trust, "RUN_CODE", "python|print(1)", is_tainted=True, source="pc")
        self.assertTrue(req_tainted)

        # Phone source still requires confirm even with trusted window
        req_phone, _ = server.check_tool_confirmation_required(cfg_trust, "RUN_CODE", "python|print(1)", is_tainted=False, source="phone")
        self.assertTrue(req_phone)

        # Expired window requires confirm
        with server.RUN_CODE_TRUST_LOCK:
            server.LAST_RUN_CODE_APPROVED_TIME = time.time() - 360
        req_exp, _ = server.check_tool_confirmation_required(cfg_trust, "RUN_CODE", "python|print(1)", is_tainted=False, source="pc")
        self.assertTrue(req_exp)

    def test_self_healing_confirmation_gate_and_taint(self):
        # 1. Healing inherits taint and stops on confirmation
        self.cfg["run_code_trusted_minutes"] = 5
        server.RUN_CODE_TRUST_STATE.record_approval()

        with patch("server.get_config", return_value=self.cfg):
            with patch("guardian_agent.review_command_safety", side_effect=lambda cfg, tool, arg, **kw: (guardian_agent.VERDICT_SAFE, "safe") if tool == "RUN_CODE" else (guardian_agent.VERDICT_DANGEROUS, "danger")):
                with patch("server.call_llm") as mock_llm:
                    mock_llm.side_effect = [
                        "Running code: [[RUN_CODE: python | 1/0]]",
                        "Healing: [[CMD: dir]]",
                        "Done."
                    ]
                    with patch("server.run_skill") as mock_skill:
                        mock_skill.side_effect = [
                            "Exit code: 1\nTraceback (most recent call last):\nZeroDivisionError: division by zero"
                        ]
                        res = server.chat("fix my code", source="pc", mode="developer")
                        self.assertIn("pending", res)
                        self.assertEqual(res["pending"]["action"], "CMD")
                        self.assertTrue(res["pending"]["preview"].startswith("dir"))

    def test_sensitive_files_access_denied(self):
        # Refuse data/config.json, data/nova_brain.db, nova_browser_profile, and .env
        cfg = {"allow_outside_workspace": True}
        data_cfg = server.DATA / "config.json"
        res_read = server.skill_read_file(str(data_cfg), cfg=cfg)
        self.assertIn("Access denied", res_read)

        res_write = server.skill_write_file(f"{data_cfg} | test", cfg=cfg)
        self.assertIn("Access denied", res_write)

        res_edit = server.skill_edit_file(f"{data_cfg} | old | new", cfg=cfg)
        self.assertIn("Access denied", res_edit)

        brain_db = server.DATA / "nova_brain.db"
        self.assertIn("Access denied", server.skill_read_file(str(brain_db), cfg=cfg))

        env_file = server.ROOT / ".env"
        self.assertIn("Access denied", server.skill_read_file(str(env_file), cfg=cfg))

        # Check LIST_FILES skips sensitive files
        list_res = server.skill_list_files(str(server.DATA), cfg=cfg)
        self.assertNotIn("config.json", list_res)

    def test_dpapi_key_encryption_and_migration(self):
        if server.OS != "Windows" or not server.is_dpapi_available():
            raise unittest.SkipTest("DPAPI only testable on Windows with crypt32")

        test_secret = "sk-test-super-secret-key-12345"
        enc = server.encrypt_dpapi(test_secret)
        self.assertTrue(enc.startswith("dpapi:"))
        self.assertNotEqual(enc, test_secret)

        dec = server.decrypt_dpapi(enc)
        self.assertEqual(dec, test_secret)

        # Test save_config and get_config
        with tempfile.TemporaryDirectory() as tmp_dir:
            orig_cfg_file = server.CONFIG_FILE
            try:
                server.CONFIG_FILE = Path(tmp_dir) / "config.json"
                cfg_data = {
                    "api_key": test_secret,
                    "encrypt_keys": True,
                }
                server.save_config(cfg_data)
                
                # On disk it must be encrypted
                disk_content = server.CONFIG_FILE.read_text(encoding="utf-8")
                self.assertNotIn(test_secret, disk_content)
                self.assertIn("dpapi:", disk_content)

                # In memory get_config must return decrypted plaintext
                loaded = server.get_config()
                self.assertEqual(loaded["api_key"], test_secret)
            finally:
                server.CONFIG_FILE = orig_cfg_file

    def test_confirmation_voice_auto_approval_and_denial(self):
        # Set up a pending action
        action_id = "test_act"
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS[action_id] = {
                "id": action_id,
                "name": "NOTE",
                "arg": "Test | Confirmation content",
                "mode": "developer",
                "source": "pc",
                "created_at": time.time(),
                "expires_at": time.time() + 120,
                "reason": "Test approval",
                "is_tainted": False
            }
        with server.LOCK:
            server.HISTORIES["developer"] = [{"role": "assistant", "content": "[Action Requires Confirmation: Test approval]"}]

        # User says "yes" -> approves and executes
        res = server.chat("yes", source="pc", mode="developer")
        self.assertIn("Approved and executed NOTE", res["reply"])
        with server.PENDING_LOCK:
            self.assertNotIn(action_id, server.PENDING_ACTIONS)

        # Now test denial
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS[action_id] = {
                "id": action_id,
                "name": "CMD",
                "arg": "dir",
                "mode": "developer",
                "source": "pc",
                "created_at": time.time(),
                "expires_at": time.time() + 120,
                "reason": "Test deny",
                "is_tainted": False
            }
        with server.LOCK:
            server.HISTORIES["developer"] = [{"role": "assistant", "content": "[Action Requires Confirmation: Test deny]"}]

        res_deny = server.chat("cancel", source="pc", mode="developer")
        self.assertIn("was cancelled", res_deny["reply"])
        with server.PENDING_LOCK:
            self.assertNotIn(action_id, server.PENDING_ACTIONS)

    # --- 1D. MOBILE REMOTE RESTRICTIONS ---
    def test_mobile_safe_tools_allowlist(self):
        # Blocked tools on phone
        for tool in ["RUN_CODE", "CMD", "POWERSHELL", "OPEN_APP", "WRITE_FILE", "EDIT_FILE", "GIT"]:
            res = server.run_skill(self.cfg, tool, "dummy", source="phone")
            self.assertIn("disabled on mobile remote for security", res)

        # Allowed tools on phone
        res_vol = server.run_skill(self.cfg, "VOLUME", "mute", source="phone")
        self.assertNotIn("disabled on mobile remote", res_vol)

    def test_mobile_token_length(self):
        saved_dict = {}
        def mock_save(c):
            saved_dict.update(c)
        with patch("server.save_config", side_effect=mock_save), patch("server.load_json", return_value={}):
            server.FAILS["192.168.1.50"] = [5, time.time()]
            server.regenerate_token()
            self.assertEqual(len(server.FAILS), 0, "regenerate_token must clear FAILS lockout")
            self.assertIn("remote_token", saved_dict)
            self.assertGreaterEqual(len(saved_dict["remote_token"]), 32)

    def test_mobile_fails_lockout(self):
        class MockRemoteRequest:
            def __init__(self, ip):
                self.client_address = (ip, 50000)
                self.headers = {"X-Nova-Token": "wrong-token"}
                self.status = None
                self.data = None
            _auth = server.RemoteHandler._auth
            def _send(self, status, data, ctype="application/json"):
                self.status = status
                self.data = data

        with patch("server.get_config", return_value={"remote_enabled": True, "remote_token": "correct-secret-token-32-chars-long"}):
            req = MockRemoteRequest("192.168.1.100")
            for i in range(8):
                ok = req._auth()
                self.assertFalse(ok)
                self.assertEqual(req.status, 401)
            # 9th attempt -> 429 lockout
            ok = req._auth()
            self.assertFalse(ok)
            self.assertEqual(req.status, 429)
            self.assertIn("15 minutes", req.data["error"])

    # --- 1E. LOCAL PROTECTION & NOTIFICATIONS ---
    def test_local_only_sec_fetch_site_and_referer(self):
        class MockReq:
            def __init__(self, headers):
                self.headers = headers
                self.command = "GET"
            _local_only = server.Handler._local_only

        # Cross-site Sec-Fetch-Site rejected
        req_bad = MockReq({"Host": "127.0.0.1:8765", "Sec-Fetch-Site": "cross-site"})
        self.assertFalse(req_bad._local_only())

        # Same-origin allowed
        req_ok = MockReq({"Host": "127.0.0.1:8765", "Sec-Fetch-Site": "same-origin"})
        self.assertTrue(req_ok._local_only())

        # Bad Referer rejected
        req_ref_bad = MockReq({"Host": "127.0.0.1:8765", "Referer": "http://evil.com/page"})
        self.assertFalse(req_ref_bad._local_only())

        # Local Referer allowed
        req_ref_ok = MockReq({"Host": "127.0.0.1:8765", "Referer": "http://127.0.0.1:8765/index.html"})
        self.assertTrue(req_ref_ok._local_only())

        # POST without any Origin / Referer / Sec-Fetch-Site rejected
        req_post_blind = MockReq({"Host": "127.0.0.1:8765"})
        req_post_blind.command = "POST"
        self.assertFalse(req_post_blind._local_only())

        # POST with Origin allowed
        req_post_ok = MockReq({"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"})
        req_post_ok.command = "POST"
        self.assertTrue(req_post_ok._local_only())

    def test_notifications_non_clearing_and_clear(self):
        sched = scheduler_engine.SchedulerEngine()
        sched.notifications = [{"id": 1, "title": "Test", "message": "Msg", "type": "test"}]
        # get does not clear
        notifs1 = sched.get_pending_notifications()
        self.assertEqual(len(notifs1), 1)
        notifs2 = sched.get_pending_notifications()
        self.assertEqual(len(notifs2), 1)
        # clear explicitly clears
        sched.clear_notifications()
        self.assertEqual(len(sched.get_pending_notifications()), 0)

if __name__ == "__main__":
    unittest.main()
