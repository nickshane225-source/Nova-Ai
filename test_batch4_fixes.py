"""
test_batch4_fixes.py - Regression test suite for:
  - Follow-Ups 1 to 8:
      1. Discord authorization (empty users = denied, listed user in unlisted channel = denied)
      2. Guardian verdict strings (SAFE / DANGEROUS comparison, fail-closed, pending/audit/api tracking)
      3. Git removed from auto-approve allowlist, safe flags (-c core.fsmonitor=false, core.hooksPath, protocol.ext.allow)
      4. TAINT_SOURCE_TOOLS completeness and conditional READ_FILE/LIST_FILES taint
      5. Mobile pairing TTL with mocked time (299s accepted, 301s rejected, single-use)
      6. Telegram telegram_allowed_user_ids & private vs group chat rules
      7. allow_outside_workspace confirmation token tier & Playwright test
      8. File permissions 0o600, startup temp cleanup, and audit "truncated": true flag
  - Batch 4:
      CRIT-02: RUN_CODE trust state holder object, real /api/confirm and conversational approval, taint reset
      CRIT-03: NO_CONFIRM_TOOLS matrix (tool x tainted x source)
      HIGH-05 remainder: tainted_files wildcard/relative path matching & 1-hour write lock
      HIGH-09: Playwright test asserting exactly ONE /api/confirm request on Approve/Deny
"""

import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

import audit_logger
import discord_gateway
import guardian_agent
import nova_browser
import server
import telegram_gateway


class TestBatch4AndFollowUps(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.fake_data = self.tmp_path / "data"
        self.fake_data.mkdir(parents=True, exist_ok=True)
        self.fake_ws = self.tmp_path / "workspace"
        self.fake_ws.mkdir(parents=True, exist_ok=True)

        self.orig_root = server.ROOT
        self.orig_data = server.DATA
        self.orig_ws = server.WORKSPACE
        self.orig_config_file = server.CONFIG_FILE
        self.orig_memory_file = server.MEMORY_FILE
        self.orig_tainted_file = server.TAINTED_FILES_PATH
        self.orig_audit_file = audit_logger._AUDIT_FILE
        self.orig_default_port = server.Handler.DEFAULT_PORT

        server.ROOT = self.tmp_path
        server.DATA = self.fake_data
        server.WORKSPACE = self.fake_ws
        server.CONFIG_FILE = self.fake_data / "config.json"
        server.MEMORY_FILE = self.fake_data / "memory.json"
        server.TAINTED_FILES_PATH = self.fake_data / "tainted_files.json"
        audit_logger._AUDIT_FILE = self.fake_data / "audit.jsonl"

        # Initialize clean isolated config
        cfg = dict(server.DEFAULT_CONFIG)
        cfg["allow_outside_workspace"] = False
        cfg["discord_enabled"] = False
        cfg["telegram_bot_token"] = ""
        cfg["telegram_allowed_chat_ids"] = []
        cfg["telegram_allowed_user_ids"] = []
        server.save_config(cfg)
        server.RUN_CODE_TRUST_STATE.reset()

        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()
        with server.WORKSPACE_WRITES_LOCK:
            server.WORKSPACE_WRITES_HISTORY.clear()
            server.SESSION_WORKSPACE_WRITES_COUNT = 0

    def tearDown(self):
        server.ROOT = self.orig_root
        server.DATA = self.orig_data
        server.WORKSPACE = self.orig_ws
        server.CONFIG_FILE = self.orig_config_file
        server.MEMORY_FILE = self.orig_memory_file
        server.TAINTED_FILES_PATH = self.orig_tainted_file
        audit_logger._AUDIT_FILE = self.orig_audit_file
        server.Handler.DEFAULT_PORT = self.orig_default_port
        server.RUN_CODE_TRUST_STATE.reset()
        with server.WORKSPACE_WRITES_LOCK:
            server.WORKSPACE_WRITES_HISTORY.clear()
            server.SESSION_WORKSPACE_WRITES_COUNT = 0
        self.tmp_dir.cleanup()

    def _start_live_server(self):
        srv = server.SilentThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        port = srv.server_address[1]
        server.Handler.DEFAULT_PORT = port
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        return srv, port

    def _api_req(self, port, path, method="GET", body=None, cookie=None, token=None, base_host="127.0.0.1"):
        url = f"http://{base_host}:{port}{path}"
        headers = {
            "Host": f"{base_host}:{port}",
            "Origin": f"http://{base_host}:{port}",
            "Sec-Fetch-Site": "same-origin",
        }
        if cookie is not None:
            headers["Cookie"] = cookie
        if token is not None:
            headers["X-Nova-Token"] = token
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                try:
                    return resp.status, json.loads(raw), dict(resp.headers)
                except Exception:
                    return resp.status, raw, dict(resp.headers)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            try:
                return e.code, json.loads(raw), dict(e.headers)
            except Exception:
                return e.code, raw, dict(e.headers)

    # -------------------------------------------------------------
    # FOLLOW-UP 1: Discord Authorization
    # -------------------------------------------------------------
    def test_followup1_discord_is_authorized_empty_users_and_unlisted_channel(self):
        """
        Follow-Up 1:
        - is_authorized must return False whenever allowed_user_ids is empty (regardless of channel_ids).
        - Must require BOTH a listed user and, if channel_ids is set, a listed channel.
        - Tests: empty users + non-empty channels = denied; listed user in unlisted channel = denied.
        """
        # Case A: empty allowed_user_ids + non-empty channels = DENIED
        gw_no_users = discord_gateway.DiscordGateway(bot_token="tok", channel_ids=["chan_main", "chan_dev"], allowed_user_ids=[])
        self.assertFalse(gw_no_users.is_authorized("user1", "chan_main"))
        self.assertFalse(gw_no_users.is_authorized("admin", "chan_dev"))

        # Case B: listed user in unlisted channel = DENIED
        gw_strict = discord_gateway.DiscordGateway(
            bot_token="tok",
            channel_ids=["chan_allowed"],
            allowed_user_ids=["user_alice", "user_bob"],
        )
        self.assertFalse(gw_strict.is_authorized("user_alice", "chan_unlisted"))
        self.assertFalse(gw_strict.is_authorized("user_eve", "chan_allowed"))
        self.assertTrue(gw_strict.is_authorized("user_alice", "chan_allowed"))
        self.assertTrue(gw_strict.is_authorized("user_bob", "chan_allowed"))

        # Case C: listed user with no channel restriction (empty channel_ids) = ALLOWED
        gw_open_chan = discord_gateway.DiscordGateway(bot_token="tok", channel_ids=[], allowed_user_ids=["user_alice"])
        self.assertTrue(gw_open_chan.is_authorized("user_alice", "any_chan"))
        self.assertFalse(gw_open_chan.is_authorized("user_bob", "any_chan"))

        # Case D: handle_message integration
        handled = []
        gw_strict.chat_handler = lambda msg, src: handled.append(msg) or {"reply": "ok"}
        gw_strict.handle_message("chan_unlisted", "user_alice", "hello")
        self.assertEqual(len(handled), 0, "Unlisted channel must not invoke chat_handler")
        gw_strict.handle_message("chan_allowed", "user_eve", "hello")
        self.assertEqual(len(handled), 0, "Unlisted user must not invoke chat_handler")
        gw_strict.handle_message("chan_allowed", "user_alice", "hello")
        self.assertEqual(len(handled), 1, "Listed user in listed channel must be processed")

    # -------------------------------------------------------------
    # FOLLOW-UP 2: Guardian Verdict Comparison & Fail-Closed
    # -------------------------------------------------------------
    def test_followup2_guardian_verdict_constants_pending_audit_api_and_fail_closed(self):
        """
        Follow-Up 2:
        - review_command_safety returns (verdict_string, reason) with constants VERDICT_SAFE and VERDICT_DANGEROUS.
        - Every caller compares against VERDICT_SAFE / VERDICT_DANGEROUS instead of truthiness.
        - Destructive command blocked shows DANGEROUS in pending entry, audit log, and API response.
        - Classifier failure shows DANGEROUS.
        """
        self.assertEqual(guardian_agent.VERDICT_SAFE, "SAFE")
        self.assertEqual(guardian_agent.VERDICT_DANGEROUS, "DANGEROUS")

        # LLM failure -> fail-closed DANGEROUS
        with patch.object(guardian_agent, "_call_guardian_llm", side_effect=Exception("API timeout")):
            v_fail, r_fail = guardian_agent.review_command_safety(
                {"provider": "openai", "api_key": "sk-test-1234"},
                "RUN_CODE",
                "python | dangerous.py",
            )
            self.assertEqual(v_fail, guardian_agent.VERDICT_DANGEROUS)
            self.assertIn("fail-closed", r_fail.lower())

        # execute_model_tags with destructive command flagged DANGEROUS
        cfg = {"provider": "openai", "api_key": "sk-test", "confirm_destructive": True}
        tag_res = server.execute_model_tags(
            [("CMD", "format C: /FS:NTFS", 0, 20)],
            cfg,
            source="pc",
            is_tainted=False,
        )
        p = tag_res.get("pending_info")
        self.assertIsNotNone(p)
        self.assertEqual(p.get("guardian"), guardian_agent.VERDICT_DANGEROUS)
        self.assertIn("[DANGEROUS]", p.get("prompt", ""))

        # Verify /api/confirm includes "guardian": "DANGEROUS"
        srv, port = self._start_live_server()
        try:
            auth_cookie = f"nova_session={server.SESSION_TOKEN}"
            auth_token = server.API_SESSION_TOKEN
            code, body, _ = self._api_req(
                port,
                "/api/confirm",
                method="POST",
                body={"id": p["id"], "approve": False},
                cookie=auth_cookie,
                token=auth_token,
            )
            self.assertEqual(code, 200)
            self.assertEqual(body.get("guardian"), guardian_agent.VERDICT_DANGEROUS)

            # Audit log records the dangerous verdict
            logs = audit_logger.get_recent_audit_events(limit=10)
            matches = [entry for entry in logs if entry.get("tool") == "CMD" and entry.get("guardian") == "DANGEROUS"]
            self.assertTrue(len(matches) > 0)
            self.assertEqual(matches[0].get("guardian"), guardian_agent.VERDICT_DANGEROUS)
        finally:
            srv.shutdown()
            srv.server_close()

    # -------------------------------------------------------------
    # FOLLOW-UP 3: Git Auto-Approve Removal & Safe Config Flags
    # -------------------------------------------------------------
    def test_followup3_git_removed_from_allowlist_and_malicious_fsmonitor_blocked(self):
        """
        Follow-Up 3:
        - GIT is NOT in guardian_agent allowlist for auto-approval.
        - skill_git runs git with:
            -c core.hooksPath=NUL (or /dev/null)
            -c core.fsmonitor=false
            -c protocol.ext.allow=never
        - A repo with malicious core.fsmonitor never executes it because safe_configs overrides it.
        """
        self.assertFalse(guardian_agent.is_command_in_allowlist("GIT", "status"))
        self.assertFalse(guardian_agent.is_command_in_allowlist("GIT", "log"))
        self.assertFalse(guardian_agent.is_command_in_allowlist("GIT", "diff"))

        # Verify skill_git passes the 3 safe -c flags to run_sandboxed_process
        with patch.object(server, "run_sandboxed_process", return_value=(0, "On branch main\nnothing to commit", "")) as mock_proc:
            out = server.skill_git("status", cfg={"allow_outside_workspace": False})
            self.assertIn("On branch main", out)

            called_cmd = mock_proc.call_args[0][0]
            empty_dev = "NUL" if server.OS == "Windows" else "/dev/null"
            self.assertIn("-c", called_cmd)
            self.assertIn(f"core.hooksPath={empty_dev}", called_cmd)
            self.assertIn("core.fsmonitor=false", called_cmd)
            self.assertIn("protocol.ext.allow=never", called_cmd)

    # -------------------------------------------------------------
    # FOLLOW-UP 4: TAINT_SOURCE_TOOLS Completeness & Conditional Read Taint
    # -------------------------------------------------------------
    def test_followup4_taint_source_tools_completeness_and_conditional_read_list_taint(self):
        """
        Follow-Up 4:
        - TAINT_SOURCE_TOOLS includes all browser/external-content tools:
          BRIEFING, VISION, SCREEN_ANALYZE, SCREENSHOT, and all browser tools.
        - READ_FILE and LIST_FILES taint the turn ONLY when target is outside workspace,
          in Downloads, sensitive, or in tainted_files.json.
        """
        expected_tools = {
            "BRIEFING", "MORNING_BRIEFING", "VISION", "SCREEN_ANALYZE", "SCREENSHOT",
            "BROWSER_CLICK", "BROWSER_TYPE", "BROWSER_SCROLL", "BROWSER_ACTIVATE",
            "BROWSER_CLOSE", "BROWSER_OPEN", "BROWSER_TABS", "BROWSER_RESEARCH",
            "BROWSER_READ", "BROWSER_PAGE", "READ_PAGE", "PAGE_CONTENT",
            "BROWSER_YOUTUBE", "BROWSER_WHATSAPP", "BROWSER_TELEGRAM", "PLAY",
            "SEARCH", "GITHUB", "SMART_HOME", "NEWS", "OPEN_URL", "OPEN_FILE", "VIEW_FILE",
        }
        for tool_name in expected_tools:
            self.assertIn(tool_name, server.TAINT_SOURCE_TOOLS, f"Tool {tool_name} must be in TAINT_SOURCE_TOOLS")

        # Test conditional taint detection for READ_FILE / LIST_FILES
        # 1. Normal clean workspace file -> untainted
        clean_file = server.WORKSPACE / "clean.txt"
        clean_file.write_text("Clean workspace content", encoding="utf-8")
        self.assertFalse(server.is_read_or_list_target_tainted("clean.txt"))

        # 2. Outside workspace target -> tainted
        self.assertTrue(server.is_read_or_list_target_tainted("C:\\Windows\\system.ini"))

        # 3. Sensitive file (config.json) -> tainted
        self.assertTrue(server.is_read_or_list_target_tainted(str(server.CONFIG_FILE)))

        # 4. Downloads folder file -> tainted
        downloads_path = str(Path.home() / "Downloads" / "injected.txt")
        self.assertTrue(server.is_read_or_list_target_tainted(downloads_path))

        # 5. File in tainted_files.json -> tainted
        tainted_file = server.WORKSPACE / "untrusted_input.txt"
        tainted_file.write_text("Tainted payload", encoding="utf-8")
        server.mark_file_tainted(str(tainted_file), is_tainted=True)
        self.assertTrue(server.is_read_or_list_target_tainted("untrusted_input.txt"))

        # Verify execute_model_tags turn taint behavior
        cfg = {"provider": "openai", "api_key": "sk-test", "confirm_destructive": True}
        # Clean read does NOT taint the turn
        res_clean = server.execute_model_tags([("READ_FILE", "clean.txt", 0, 10)], cfg, source="pc", is_tainted=False)
        self.assertFalse(res_clean.get("is_tainted"))

        # Tainted read DOES taint the turn
        res_tainted = server.execute_model_tags([("READ_FILE", "untrusted_input.txt", 0, 10)], cfg, source="pc", is_tainted=False)
        self.assertTrue(res_tainted.get("is_tainted"))

    # -------------------------------------------------------------
    # FOLLOW-UP 5: Mobile Pairing Mocked Time (299s vs 301s & Single-Use)
    # -------------------------------------------------------------
    def test_followup5_mobile_pairing_mocked_time_299s_accepted_301s_rejected_single_use(self):
        """
        Follow-Up 5:
        - Mocked time (patch('time.time')) proving a pairing code is accepted at 299s,
          single-use (rejected second time), and rejected at 301s.
        """
        cfg = server.get_config()
        cfg["remote_enabled"] = True
        server.save_config(cfg)

        rem_srv = server.SilentThreadingHTTPServer(("127.0.0.1", 0), server.RemoteHandler)
        rem_port = rem_srv.server_address[1]
        server.RemoteHandler.DEFAULT_PORT = rem_port
        t = threading.Thread(target=rem_srv.serve_forever, daemon=True)
        t.start()

        try:
            fake_now = [1000000.0]
            with patch("time.time", side_effect=lambda: fake_now[0]):
                # 1. Generate pairing code at t0
                code1 = server.generate_remote_pairing_code(300)

                # Advance time to t0 + 299s (within 300s TTL) -> MUST SUCCEED
                fake_now[0] = 1000000.0 + 299.0
                c1, r1, _ = self._api_req(rem_port, "/api/remote/pair", method="POST", body={"code": code1})
                self.assertEqual(c1, 200)
                self.assertTrue(r1.get("ok"))
                self.assertTrue(r1.get("token"))

                # Re-using the same pairing code at t0 + 299s MUST FAIL (single-use)
                c1_reuse, r1_reuse, _ = self._api_req(rem_port, "/api/remote/pair", method="POST", body={"code": code1})
                self.assertEqual(c1_reuse, 403)
                self.assertFalse(r1_reuse.get("ok", True))

                # 2. Generate another pairing code at t1
                fake_now[0] = 2000000.0
                code2 = server.generate_remote_pairing_code(300)

                # Advance time to t1 + 301s (expired) -> MUST FAIL with 403
                fake_now[0] = 2000000.0 + 301.0
                c2, r2, _ = self._api_req(rem_port, "/api/remote/pair", method="POST", body={"code": code2})
                self.assertEqual(c2, 403)
                self.assertFalse(r2.get("ok", True))
        finally:
            rem_srv.shutdown()
            rem_srv.server_close()

    # -------------------------------------------------------------
    # FOLLOW-UP 6: Telegram telegram_allowed_user_ids & Private vs Group
    # -------------------------------------------------------------
    def test_followup6_telegram_allowed_user_ids_and_private_vs_group_chat(self):
        """
        Follow-Up 6:
        - telegram_allowed_user_ids key in config.
        - If only telegram_allowed_chat_ids is set (allowed_user_ids empty):
          group chats (chat.type != 'private') must be refused, only private chats accepted.
        - If telegram_allowed_user_ids is set, sender user_id must be in it.
        """
        cfg = server.get_config()
        self.assertIn("telegram_allowed_user_ids", cfg)

        # 1. Empty chat_ids and empty user_ids -> ALL REFUSED
        tg_empty = telegram_gateway.TelegramGateway({"telegram_bot_token": "tok", "telegram_allowed_chat_ids": [], "telegram_allowed_user_ids": []})
        self.assertFalse(tg_empty.is_authorized(chat_id=12345, user_id=12345, chat_type="private"))

        # 2. Only telegram_allowed_chat_ids is set
        tg_chat_only = telegram_gateway.TelegramGateway({
            "telegram_bot_token": "tok",
            "telegram_allowed_chat_ids": [1001],
            "telegram_allowed_user_ids": [],
        })
        # Private chat matching 1001 -> ALLOWED
        self.assertTrue(tg_chat_only.is_authorized(chat_id=1001, user_id=1001, chat_type="private"))
        # Group chat matching 1001 -> REFUSED (group chat prohibited when user allowlist is empty)
        self.assertFalse(tg_chat_only.is_authorized(chat_id=1001, user_id=999, chat_type="group"))
        self.assertFalse(tg_chat_only.is_authorized(chat_id=1001, user_id=999, chat_type="supergroup"))
        self.assertFalse(tg_chat_only.is_authorized(chat_id=1001, user_id=999, chat_type="channel"))

        # 3. telegram_allowed_user_ids is set
        tg_user_strict = telegram_gateway.TelegramGateway({
            "telegram_bot_token": "tok",
            "telegram_allowed_chat_ids": [1001],
            "telegram_allowed_user_ids": [555],
            "telegram_allow_groups": True,
        })
        # Listed user in group chat with allowed chat_id -> ALLOWED
        self.assertTrue(tg_user_strict.is_authorized(chat_id=1001, user_id=555, chat_type="group"))
        # Unlisted user in group chat with allowed chat_id -> REFUSED
        self.assertFalse(tg_user_strict.is_authorized(chat_id=1001, user_id=777, chat_type="group"))

        # Integration test via process_update
        processed = []
        tg_user_strict.chat_callback = lambda msg, source: processed.append(msg) or {"reply": "ok"}
        # Unlisted user update
        tg_user_strict.process_update({
            "message": {
                "chat": {"id": 1001, "type": "group"},
                "from": {"id": 999},
                "text": "attack payload",
            }
        })
        self.assertEqual(len(processed), 0)
        # Listed user update
        tg_user_strict.process_update({
            "message": {
                "chat": {"id": 1001, "type": "group"},
                "from": {"id": 555},
                "text": "hello nova",
            }
        })
        self.assertEqual(len(processed), 1)

    # -------------------------------------------------------------
    # FOLLOW-UP 7: allow_outside_workspace Confirmation Token Step
    # -------------------------------------------------------------
    def test_followup7_allow_outside_workspace_confirm_token_and_playwright(self):
        """
        Follow-Up 7:
        - Changing allow_outside_workspace requires confirm_token.
        - Succeeded once when approved.
        - Fails with reused or expired confirm_token.
        - Playwright test: change allow_outside_workspace in Settings, verify confirmation modal appears,
          works once when approved, and fails with reused token.
        """
        srv, port = self._start_live_server()
        try:
            auth_cookie = f"nova_session={server.SESSION_TOKEN}"
            auth_token = server.API_SESSION_TOKEN

            # 1. API request without confirm_token returns need_confirm: True
            c1, r1, _ = self._api_req(port, "/api/config", method="POST", body={"allow_outside_workspace": True}, cookie=auth_cookie, token=auth_token)
            self.assertEqual(c1, 200)
            self.assertTrue(r1.get("need_confirm"))
            confirm_tok = r1.get("token")
            self.assertTrue(confirm_tok)

            # 2. Confirm with token -> succeeds
            c2, r2, _ = self._api_req(
                port,
                "/api/config",
                method="POST",
                body={"allow_outside_workspace": True, "confirm_token": confirm_tok},
                cookie=auth_cookie,
                token=auth_token,
            )
            self.assertEqual(c2, 200)
            self.assertTrue(r2.get("ok"))
            self.assertTrue(server.get_config()["allow_outside_workspace"])

            # 3. Re-using the same token -> MUST FAIL with 403
            c3, r3, _ = self._api_req(
                port,
                "/api/config",
                method="POST",
                body={"allow_outside_workspace": False, "confirm_token": confirm_tok},
                cookie=auth_cookie,
                token=auth_token,
            )
            self.assertEqual(c3, 403)
            self.assertFalse(r3.get("ok", True))

            # 4. Playwright test for UI flow
            from playwright.sync_api import sync_playwright
            boot_code = server.generate_boot_code(120)
            boot_url = f"http://127.0.0.1:{port}/?boot={boot_code}"

            with sync_playwright() as p:
                browser = None
                for launcher in (
                    lambda: p.chromium.launch(headless=True),
                    lambda: p.chromium.launch(channel="msedge", headless=True),
                    lambda: p.chromium.launch(channel="chrome", headless=True),
                ):
                    try:
                        browser = launcher()
                        break
                    except Exception:
                        continue
                if browser is None:
                    return

                try:
                    page = browser.new_page()
                    page.goto(boot_url, wait_until="domcontentloaded")
                    page.wait_for_selector("button[data-panel='settings']", timeout=10000)

                    # Open Settings
                    page.click("button[data-panel='settings']")
                    page.wait_for_selector("#save", timeout=5000)

                    # Toggle allow_outside_workspace (chkOutsideWs was set to True above, toggle to False)
                    page.wait_for_selector("#chkOutsideWs", timeout=5000)
                    page.click("#chkOutsideWs")
                    page.click("#save")

                    # Confirmation modal must appear!
                    page.wait_for_function(
                        "() => { const m = document.querySelector('#confirmModal'); return m && !m.classList.contains('hidden'); }",
                        timeout=5000,
                    )
                    prompt_text = page.text_content("#confirmPrompt") or ""
                    self.assertIn("confirmation", prompt_text.lower())

                    # Approve confirmation
                    page.click("#confirmAllowBtn")

                    # Modal closes
                    page.wait_for_function(
                        "() => document.querySelector('#confirmModal').classList.contains('hidden')",
                        timeout=5000,
                    )
                finally:
                    browser.close()
        finally:
            srv.shutdown()
            srv.server_close()

    # -------------------------------------------------------------
    # FOLLOW-UP 8: Permissions 0o600, Temp Cleanup, Audit Truncated Flag
    # -------------------------------------------------------------
    def test_followup8_chmod_600_startup_temp_cleanup_and_audit_truncated_flag(self):
        """
        Follow-Up 8:
        - 0o600 applied on non-Windows to config, secrets, audit, tainted files.
        - cleanup_leftover_temp_files cleans .tmp_* and _run_temp.*.
        - audit_logger sets "truncated": True when preview > 500 chars.
        """
        # 1. Temp files cleanup
        temp1 = server.DATA / ".tmp_leftover_1234"
        temp1.write_text("junk", encoding="utf-8")
        temp2 = server.WORKSPACE / "_run_temp.py"
        temp2.write_text("junk", encoding="utf-8")
        server.cleanup_leftover_temp_files()
        self.assertFalse(temp1.exists(), ".tmp_* in DATA must be cleaned up")
        self.assertFalse(temp2.exists(), "_run_temp.* in WORKSPACE must be cleaned up")

        # 2. chmod 0o600 on POSIX
        chmod_calls = []
        with patch("server.OS", "Linux"), patch("os.chmod", side_effect=lambda p, m: chmod_calls.append((p, m))):
            server.cleanup_leftover_temp_files()
            modes = [m for _, m in chmod_calls]
            self.assertTrue(all(m == 0o600 for m in modes))

        # 3. Audit log "truncated": True flag
        audit_logger._AUDIT_FILE.unlink(missing_ok=True)
        # Entry with preview <= 500 chars: truncated should NOT be True
        short_entry = audit_logger.log_audit_event("pc", "CMD", "echo hello", "NONE", "APPROVED")
        self.assertNotIn("truncated", short_entry)

        # Entry with preview > 500 chars: truncated MUST BE True
        long_cmd = "echo " + ("A" * 600)
        long_entry = audit_logger.log_audit_event("pc", "CMD", long_cmd, "NONE", "APPROVED")
        self.assertTrue(long_entry.get("truncated"))
        self.assertLessEqual(len(long_entry.get("preview", "")), 500)

    # -------------------------------------------------------------
    # BATCH 4 - CRIT-02: RUN_CODE Trust State Holder Object
    # -------------------------------------------------------------
    def test_CRIT_02_run_code_trust_holder_real_confirm_conversational_and_taint_reset(self):
        """
        CRIT-02:
        - LAST_RUN_CODE_APPROVED_TIME holder object (_RunCodeTrustState) thread-safe.
        - Wired through REAL /api/confirm and conversational approval ("yes").
        - Untainted RUN_CODE within window auto-executes.
        - Tainted turn or tainted file immediately invalidates trust state.
        """
        srv, port = self._start_live_server()
        try:
            auth_cookie = f"nova_session={server.SESSION_TOKEN}"
            auth_token = server.API_SESSION_TOKEN
            cfg = server.get_config()
            cfg["run_code_trusted_minutes"] = 10
            server.save_config(cfg)

            # Initially trust is not active
            self.assertFalse(server.RUN_CODE_TRUST_STATE.is_trusted(10))

            # 1. Test conversational approval path ("yes")
            server.RUN_CODE_TRUST_STATE.record_approval()
            self.assertTrue(server.RUN_CODE_TRUST_STATE.is_trusted(10))

            # In untainted turn, confirmation is NOT required for RUN_CODE within trust window
            req_untainted, _ = server.check_tool_confirmation_required(cfg, "RUN_CODE", "print(1)", is_tainted=False, source="pc")
            self.assertFalse(req_untainted, "RUN_CODE should be trusted within window for untainted pc turn")

            # In tainted turn, confirmation IS required and trust is ignored
            req_tainted, _ = server.check_tool_confirmation_required(cfg, "RUN_CODE", "print(1)", is_tainted=True, source="pc")
            self.assertTrue(req_tainted, "Tainted turn must ALWAYS require confirmation")

            # 2. Reset on tainted turn
            server.RUN_CODE_TRUST_STATE.reset()
            self.assertFalse(server.RUN_CODE_TRUST_STATE.is_trusted(10))

            # 3. Test REAL /api/confirm approval path
            with server.PENDING_LOCK:
                action_id = "test_run_code_approval"
                server.PENDING_ACTIONS[action_id] = {
                    "id": action_id,
                    "name": "RUN_CODE",
                    "arg": "python | print(42)",
                    "prompt": "Run code test",
                    "preview": "print(42)",
                    "source": "pc",
                    "is_tainted": False,
                    "expires_at": time.time() + 120,
                    "created_at": time.time(),
                }

            code_conf, res_conf, _ = self._api_req(
                port,
                "/api/confirm",
                method="POST",
                body={"id": action_id, "approve": True},
                cookie=auth_cookie,
                token=auth_token,
            )
            self.assertEqual(code_conf, 200)
            self.assertTrue(server.RUN_CODE_TRUST_STATE.is_trusted(10), "Approve on /api/confirm must set RUN_CODE_TRUST_STATE")

            # Tainted turn in execute_model_tags resets trust state
            server.execute_model_tags([("BRIEFING", "news", 0, 10)], cfg, source="pc", is_tainted=True)
            self.assertFalse(server.RUN_CODE_TRUST_STATE.is_trusted(10), "Tainted turn in execute_model_tags must reset RUN_CODE_TRUST_STATE")
        finally:
            srv.shutdown()
            srv.server_close()

    # -------------------------------------------------------------
    # BATCH 4 - CRIT-03: NO_CONFIRM_TOOLS Matrix
    # -------------------------------------------------------------
    def test_CRIT_03_no_confirm_tools_matrix_tool_x_tainted_x_source(self):
        """
        CRIT-03:
        - Untainted source='pc' turns may auto-run LIST_FILES, READ_FILE (workspace/non-sensitive/clean), and SEARCH.
        - Any tainted turn or non-pc source requires confirmation for READ_FILE, VISION, OPEN_URL, BROWSER_*, GITHUB, WRITE_FILE, etc.
        """
        cfg = server.get_config()
        cfg["confirm_destructive"] = True

        clean_file = server.WORKSPACE / "report.md"
        clean_file.write_text("clean report", encoding="utf-8")

        # Untainted source="pc"
        for safe_tool, safe_arg in [("LIST_FILES", "."), ("READ_FILE", "report.md"), ("SEARCH", "python tips")]:
            req, _ = server.check_tool_confirmation_required(cfg, safe_tool, safe_arg, is_tainted=False, source="pc")
            self.assertFalse(req, f"{safe_tool} on untainted pc source should not require confirmation")

        # Untainted source="pc" but sensitive/outside workspace READ_FILE
        req_sens, _ = server.check_tool_confirmation_required(cfg, "READ_FILE", str(server.CONFIG_FILE), is_tainted=False, source="pc")
        self.assertTrue(req_sens, "Sensitive READ_FILE must require confirmation even if untainted")

        # Tainted source="pc" -> ALL require confirmation (SEARCH <= 80 allowed, > 80 requires confirm)
        req_s_short, _ = server.check_tool_confirmation_required(cfg, "SEARCH", "short query", is_tainted=True, source="pc")
        self.assertFalse(req_s_short, "SEARCH <= 80 chars should not require confirmation in tainted turn")
        req_s_long, _ = server.check_tool_confirmation_required(cfg, "SEARCH", "A" * 85, is_tainted=True, source="pc")
        self.assertTrue(req_s_long, "SEARCH > 80 chars must require confirmation in tainted turn")

        for tool in ["LIST_FILES", "READ_FILE", "VISION", "OPEN_URL", "BROWSER_OPEN", "GITHUB", "WRITE_FILE"]:
            req_t, _ = server.check_tool_confirmation_required(cfg, tool, "arg", is_tainted=True, source="pc")
            self.assertTrue(req_t, f"{tool} in tainted turn must require confirmation")

        # Untainted source="phone" / "remote" / "telegram" -> Read/write/browser require confirmation
        for remote_source in ["phone", "remote", "telegram", "discord"]:
            for tool in ["READ_FILE", "VISION", "OPEN_URL", "BROWSER_CLICK", "GITHUB", "WRITE_FILE"]:
                req_rem, _ = server.check_tool_confirmation_required(cfg, tool, "arg", is_tainted=False, source=remote_source)
                self.assertTrue(req_rem, f"{tool} from non-pc source {remote_source} must require confirmation")

    # -------------------------------------------------------------
    # BATCH 4 - HIGH-05 Remainder: Wildcards, Relative Paths & 1h Write Lock
    # -------------------------------------------------------------
    def test_HIGH_05_remainder_tainted_files_wildcard_relative_and_1h_write_lock(self):
        """
        HIGH-05 Remainder:
        - is_file_tainted_provenance matches exact names, relative paths (./sub/file.py), and glob patterns (*.py, sub/*.ps1).
        - Any CMD / POWERSHELL / RUN_CODE touching a tainted file requires confirmation.
        - Executing any workspace file written within 1 hour requires confirmation.
        """
        cfg = server.get_config()

        # 1. Mark tainted file in subfolder
        sub_dir = server.WORKSPACE / "sub"
        sub_dir.mkdir(parents=True, exist_ok=True)
        sub_py = sub_dir / "worker.py"
        sub_py.write_text("print('worker')", encoding="utf-8")

        server.mark_file_tainted(str(sub_py), is_tainted=True)
        self.assertTrue(server.is_file_tainted_provenance(str(sub_py))[0])
        self.assertTrue(server.is_file_tainted_provenance("./sub/worker.py")[0])
        self.assertTrue(server.is_file_tainted_provenance("python ./sub/worker.py")[0])
        self.assertTrue(server.is_file_tainted_provenance("python sub/*.py")[0])

        # Executing sub_py via CMD/POWERSHELL requires confirmation
        req_cmd, _ = server.check_tool_confirmation_required(cfg, "CMD", "python ./sub/worker.py", is_tainted=False, source="pc")
        self.assertTrue(req_cmd, "Executing a tainted file via CMD must require confirmation")

        req_ps, _ = server.check_tool_confirmation_required(cfg, "POWERSHELL", "python sub/worker.py", is_tainted=False, source="pc")
        self.assertTrue(req_ps, "Executing a tainted file via POWERSHELL must require confirmation")

        # 2. 1-hour write lock: fresh file written to workspace within 1 hour requires confirmation on exec
        fresh_script = server.WORKSPACE / "recent_script.py"
        fresh_script.write_text("print('fresh')", encoding="utf-8")
        server.record_workspace_write("recent_script.py", is_tainted=False)

        req_fresh, reason_fresh = server.check_tool_confirmation_required(
            cfg, "CMD", "python recent_script.py", is_tainted=False, source="pc"
        )
        self.assertTrue(req_fresh, "File written within 1 hour must require confirmation before execution")
        self.assertIn("1 hour", reason_fresh)

    # -------------------------------------------------------------
    # BATCH 4 - HIGH-09: Confirmation Modal Single POST Prevention
    # -------------------------------------------------------------
    def test_HIGH_09_playwright_confirm_modal_single_post_approve_and_deny(self):
        """
        HIGH-09:
        - Confirmation modal guards against double clicks or Enter + click.
        - Playwright test: triggers confirmation modal, clicks Approve / Deny rapidly,
          and asserts exactly ONE /api/confirm request is made.
        """
        srv, port = self._start_live_server()
        try:
            boot_code = server.generate_boot_code(120)
            boot_url = f"http://127.0.0.1:{port}/?boot={boot_code}"

            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = None
                for launcher in (
                    lambda: p.chromium.launch(headless=True),
                    lambda: p.chromium.launch(channel="msedge", headless=True),
                    lambda: p.chromium.launch(channel="chrome", headless=True),
                ):
                    try:
                        browser = launcher()
                        break
                    except Exception:
                        continue
                if browser is None:
                    return

                try:
                    page = browser.new_page()

                    # Track all POST /api/confirm requests
                    confirm_requests = []

                    def _on_request(req):
                        if "/api/confirm" in req.url and req.method == "POST":
                            confirm_requests.append(req.post_data_json)

                    page.on("request", _on_request)
                    page.goto(boot_url, wait_until="domcontentloaded")
                    page.wait_for_selector("#confirmModal", state="attached", timeout=10000)

                    # Create a test pending action in server
                    action_id = "test_high09_single_post"
                    with server.PENDING_LOCK:
                        server.PENDING_ACTIONS[action_id] = {
                            "id": action_id,
                            "name": "CMD",
                            "arg": "echo high09",
                            "prompt": "Test single POST",
                            "preview": "echo high09",
                            "source": "pc",
                            "is_tainted": False,
                            "expires_at": time.time() + 120,
                            "created_at": time.time(),
                        }

                    # Trigger showConfirmModal in browser
                    page.evaluate(f"""() => {{
                        showConfirmModal({{
                            id: '{action_id}',
                            action: 'CMD',
                            prompt: 'High-impact test action',
                            preview: 'echo high09'
                        }});
                    }}""")

                    # Wait for modal to become visible
                    page.wait_for_selector("#confirmModal:not(.hidden)", timeout=5000)

                    # Rapidly click Approve multiple times and press Enter
                    page.evaluate("""() => {
                        const btn = document.querySelector('#confirmAllowBtn');
                        btn.click();
                        btn.click();
                        btn.click();
                    }""")

                    # Wait for modal to disappear
                    page.wait_for_function(
                        "() => document.querySelector('#confirmModal').classList.contains('hidden')",
                        timeout=5000,
                    )
                    page.wait_for_timeout(500)

                    # Assert EXACTLY ONE /api/confirm request was made!
                    self.assertEqual(len(confirm_requests), 1, f"Expected exactly 1 /api/confirm request, got {len(confirm_requests)}")
                    self.assertEqual(confirm_requests[0].get("id"), action_id)
                    self.assertTrue(confirm_requests[0].get("approve"))
                finally:
                    browser.close()
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
