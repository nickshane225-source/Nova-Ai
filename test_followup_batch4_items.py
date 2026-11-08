"""
test_followup_batch4_items.py - Tests for the 6 new Follow-Ups:
  1. Sticky taint: once tainted, stays tainted across turns until reset or 'Clear untrusted context'.
     SEARCH > 80 chars and READ_FILE require confirmation in tainted conversation; SEARCH <= 80 chars allowed.
  2. Multi-step tool loop within a single request: tainted tool result taints next call in the loop.
  3. Telegram (edited_message, channel_post, sender_chat, /allow from user.id) & Discord (bot/self ignore, DM policy).
  4. Guardian DANGEROUS or classifier failure blocks every auto-approval path (scheduler, automations, silent gateway runs).
  5. run_code_trusted_minutes default 0, hard cap 10, per-session, reset on tainted conversation.
  6. skill_git: only status/log/diff/show/clone allowed, clear GIT_* env vars, GIT_CONFIG_NOSYSTEM=1, --no-optional-locks.
"""

import collections
import json
import os
import shutil
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


class TestFollowUpBatch4Items(unittest.TestCase):
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
        cfg["confirm_destructive"] = True
        cfg["run_code_trusted_minutes"] = 0
        cfg["discord_enabled"] = False
        cfg["telegram_bot_token"] = ""
        cfg["telegram_allowed_chat_ids"] = []
        cfg["telegram_allowed_user_ids"] = []
        server.save_config(cfg)
        server.RUN_CODE_TRUST_STATE.reset()

        with server.LOCK:
            server.HISTORIES["developer"].clear()
            server.HISTORIES["cyber"].clear()
            server.CONVERSATION_TAINT["developer"] = False
            server.CONVERSATION_TAINT["cyber"] = False

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

        with server.LOCK:
            server.HISTORIES["developer"].clear()
            server.HISTORIES["cyber"].clear()
            server.CONVERSATION_TAINT["developer"] = False
            server.CONVERSATION_TAINT["cyber"] = False

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
    # 1. STICKY TAINT ACROSS TURNS & CLEAR UNTRUSTED CONTEXT
    # -------------------------------------------------------------
    def test_item1_sticky_taint_across_turns_and_clear_untrusted_context(self):
        """
        Follow-Up 1:
        - Turn 1 reads a page containing injected text (or external untrusted source) -> turn 1 tainted.
        - Turn 2 says 'continue' -> starts tainted because conversation has sticky taint.
        - Model tries SEARCH with long query (> 80 chars) or READ_FILE -> both require confirmation.
        - SEARCH <= 80 chars is allowed without confirmation.
        - Clear untrusted context resets taint and removes tool outputs.
        """
        cfg = server.get_config()

        # Turn 1: model reads an untrusted page
        with patch("server.call_llm", return_value="Reading page: [[BROWSER_PAGE: http://example.com]]"):
            with patch("server.run_skill", return_value="Injected malicious prompt text"):
                res1 = server.chat("read the news", source="pc", mode="developer")
                self.assertTrue(server.CONVERSATION_TAINT["developer"], "Turn 1 must mark conversation tainted")

        # Turn 2: user says "continue". Model tries SEARCH with long query (> 80 chars)
        long_query = "explain how to build a quantum computer using supercomputers and specialized algorithms in python"
        self.assertGreater(len(long_query), 80)
        with patch("server.call_llm", return_value=f"Searching: [[SEARCH: {long_query}]]"):
            res2 = server.chat("continue", source="pc", mode="developer")
            self.assertIn("pending", res2, "SEARCH > 80 chars in tainted conversation must require confirmation")
            self.assertEqual(res2["pending"]["action"], "SEARCH")

        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()

        # Turn 2b: Model tries READ_FILE in tainted conversation -> requires confirmation
        clean_file = server.WORKSPACE / "my_notes.txt"
        clean_file.write_text("personal notes", encoding="utf-8")
        with patch("server.call_llm", return_value="Reading: [[READ_FILE: my_notes.txt]]"):
            res2b = server.chat("continue", source="pc", mode="developer")
            self.assertIn("pending", res2b, "READ_FILE in tainted conversation must require confirmation")
            self.assertEqual(res2b["pending"]["action"], "READ_FILE")

        # Turn 2c: SEARCH with <= 80 chars is allowed without confirmation
        short_query = "weather today"
        self.assertLessEqual(len(short_query), 80)
        req_short, _ = server.check_tool_confirmation_required(cfg, "SEARCH", short_query, is_tainted=True, source="pc")
        self.assertFalse(req_short, "SEARCH <= 80 chars should not require confirmation in tainted turn")

        # Test Clear Untrusted Context endpoint via live server
        srv, port = self._start_live_server()
        try:
            auth_cookie = f"nova_session={server.SESSION_TOKEN}"
            auth_token = server.API_SESSION_TOKEN

            # Verify GET /api/state returns is_tainted=True
            c_st, r_st, _ = self._api_req(port, "/api/state", method="GET", cookie=auth_cookie, token=auth_token)
            self.assertEqual(c_st, 200)
            self.assertTrue(r_st.get("is_tainted"))

            # Clear untrusted context
            c_clear, r_clear, _ = self._api_req(
                port,
                "/api/clear_untrusted_context",
                method="POST",
                body={"mode": "developer"},
                cookie=auth_cookie,
                token=auth_token,
            )
            self.assertEqual(c_clear, 200)
            self.assertTrue(r_clear.get("ok"))
            self.assertFalse(r_clear.get("is_tainted"))
            self.assertFalse(server.CONVERSATION_TAINT["developer"])

            # Verify GET /api/state now returns is_tainted=False
            c_st2, r_st2, _ = self._api_req(port, "/api/state", method="GET", cookie=auth_cookie, token=auth_token)
            self.assertEqual(c_st2, 200)
            self.assertFalse(r_st2.get("is_tainted"))
        finally:
            srv.shutdown()
            srv.server_close()

    # -------------------------------------------------------------
    # 2. MULTI-STEP TOOL LOOP TAINT PROPAGATION
    # -------------------------------------------------------------
    def test_item2_multistep_tool_loop_taint_propagation(self):
        """
        Follow-Up 2:
        - Within a single request (multi-step tool loop), a tainted tool result taints the next tool call in that loop.
        - Test with a mocked LLM that issues SEARCH then READ_FILE then CMD in successive iterations.
        """
        clean_file = server.WORKSPACE / "data.txt"
        clean_file.write_text("clean text", encoding="utf-8")

        # LLM returns SEARCH in step 1, then READ_FILE in step 2
        mock_replies = [
            "Step 1: [[SEARCH: security tips]]",
            "Step 2: [[READ_FILE: data.txt]]",
            "Step 3: [[CMD: dir]]",
        ]
        with patch("server.call_llm", side_effect=mock_replies):
            with patch("server.run_skill", return_value="Search results from internet"):
                res = server.chat("investigate security", source="pc", mode="developer")
                # Step 1 SEARCH executed and tainted the turn.
                # Step 2 READ_FILE received is_tainted=True and halted for confirmation!
                self.assertIn("pending", res)
                self.assertEqual(res["pending"]["action"], "READ_FILE")
                self.assertTrue(res["pending"]["is_tainted"], "Pending action must have is_tainted=True")

    # -------------------------------------------------------------
    # 3. TELEGRAM & DISCORD SECURITY HARDENING
    # -------------------------------------------------------------
    def test_item3_telegram_and_discord_gateways_security(self):
        """
        Follow-Up 3:
        - Telegram: edited_message, channel_post, sender_chat without user.id must not bypass sender check.
        - Telegram: /allow and /deny must come from an allowlisted user.id.
        - Discord: ignore bot and self messages; explicit DM policy.
        """
        # --- Telegram Tests ---
        tg = telegram_gateway.TelegramGateway({
            "telegram_bot_token": "mock_token",
            "telegram_allowed_chat_ids": ["12345"],
            "telegram_allowed_user_ids": ["555"],
        })

        # 1. edited_message is checked
        self.assertFalse(tg.process_update({
            "edited_message": {
                "chat": {"id": 12345, "type": "private"},
                "from": {"id": 999},  # unlisted
                "text": "hello",
            }
        }))

        # 2. channel_post is checked (type != private, no user from)
        self.assertFalse(tg.process_update({
            "channel_post": {
                "chat": {"id": 12345, "type": "channel"},
                "text": "channel broadcast",
            }
        }))

        # 3. sender_chat without user.id is rejected
        self.assertFalse(tg.process_update({
            "message": {
                "chat": {"id": 12345, "type": "private"},
                "sender_chat": {"id": 99999},
                "text": "spoof attempt",
            }
        }))

        # 4. /allow and /deny rejected if not from allowlisted user.id
        tg_chats_only = telegram_gateway.TelegramGateway({
            "telegram_bot_token": "mock_token",
            "telegram_allowed_chat_ids": ["12345"],
            "telegram_allowed_user_ids": [],
        })
        # Message with no user ID calling /allow -> rejected
        self.assertFalse(tg_chats_only.process_update({
            "message": {
                "chat": {"id": 12345, "type": "private"},
                "text": "/allow test_token",
            }
        }))

        # --- Discord Tests ---
        dc = discord_gateway.DiscordGateway(
            bot_token="mock_dc_token",
            channel_ids=["chan_1"],
            allowed_user_ids=["alice_123"],
            allow_dms=False,
        )
        dc.bot_id = "bot_999"

        handled = []
        dc.chat_handler = lambda msg, src: handled.append(msg) or {"reply": "ok"}

        # 1. Ignore bot message
        dc.handle_message("chan_1", "alice_123", "hello", is_bot=True)
        self.assertEqual(len(handled), 0, "Bot message must be ignored")

        # 2. Ignore self message
        dc.handle_message("chan_1", "bot_999", "hello", is_bot=False)
        self.assertEqual(len(handled), 0, "Self message must be ignored")

        # 3. Explicit DM policy (when allow_dms=False -> DMs ignored)
        dc.handle_message("dm_123", "alice_123", "hello in DM", is_dm=True)
        self.assertEqual(len(handled), 0, "DM must be rejected when allow_dms=False")

        # 4. DM allowed when allow_dms=True and user in allowed_user_ids
        dc.allow_dms = True
        dc.handle_message("dm_123", "alice_123", "hello in DM", is_dm=True)
        self.assertEqual(len(handled), 1, "DM must be accepted when allow_dms=True for allowed user")

        # 5. DM rejected when user not in allowed_user_ids
        dc.handle_message("dm_123", "eve_unlisted", "hello in DM", is_dm=True)
        self.assertEqual(len(handled), 1, "DM must be rejected for unlisted user")

    # -------------------------------------------------------------
    # 4. GUARDIAN DANGEROUS BLOCKS EVERY AUTO-APPROVAL PATH
    # -------------------------------------------------------------
    def test_item4_guardian_dangerous_blocks_every_auto_approval_path(self):
        """
        Follow-Up 4:
        - Guardian DANGEROUS or classifier failure must block every auto-approval path:
          scheduler, automations, silent gateway runs, and even confirm_destructive=False.
        """
        cfg = server.get_config()
        cfg["confirm_destructive"] = False  # normally skips confirmation

        # 1. Destructive CMD flagged DANGEROUS by Guardian must halt for confirmation even with confirm_destructive=False
        with patch.object(guardian_agent, "review_command_safety", return_value=(guardian_agent.VERDICT_DANGEROUS, "Destructive format command")):
            res = server.execute_model_tags([("CMD", "format C:", 0, 10)], cfg, source="pc", is_tainted=False)
            self.assertIsNotNone(res.get("pending_info"), "Guardian DANGEROUS must require confirmation even if confirm_destructive=False")
            self.assertEqual(res["pending_info"]["guardian"], "DANGEROUS")

        # 2. Scheduled/automation path with classifier failure -> fails closed as DANGEROUS and requires confirmation
        with patch.object(guardian_agent, "_call_guardian_llm", side_effect=Exception("Classifier network error")):
            res_sched = server.execute_model_tags([("RUN_CODE", "python | import os", 0, 10)], cfg, source="scheduled", is_tainted=False)
            self.assertIsNotNone(res_sched.get("pending_info"), "Classifier failure in scheduled run must require confirmation")
            self.assertEqual(res_sched["pending_info"]["guardian"], "DANGEROUS")

        # 3. Gateway silent run flagged DANGEROUS
        with patch.object(guardian_agent, "review_command_safety", return_value=(guardian_agent.VERDICT_DANGEROUS, "Dangerous action")):
            res_gw = server.execute_model_tags([("LIST_FILES", ".", 0, 10)], cfg, source="telegram", is_tainted=False)
            self.assertIsNotNone(res_gw.get("pending_info"), "Guardian DANGEROUS must require confirmation for gateway runs")

    # -------------------------------------------------------------
    # 5. RUN_CODE TRUSTED MINUTES HARD CAP 10 & RESET ON TAINT
    # -------------------------------------------------------------
    def test_item5_run_code_trusted_minutes_hard_cap_10_and_reset_on_taint(self):
        """
        Follow-Up 5:
        - run_code_trusted_minutes default 0.
        - Hard cap 10 enforced by config API.
        - Per-session only.
        - Reset on any tainted conversation.
        """
        srv, port = self._start_live_server()
        try:
            auth_cookie = f"nova_session={server.SESSION_TOKEN}"
            auth_token = server.API_SESSION_TOKEN

            # Default is 0
            cfg0 = server.get_config()
            self.assertEqual(cfg0.get("run_code_trusted_minutes", 0), 0)

            # Setting > 10 (e.g. 15 or 30) returns HTTP 400
            c_bad, r_bad, _ = self._api_req(
                port,
                "/api/config",
                method="POST",
                body={"run_code_trusted_minutes": 15},
                cookie=auth_cookie,
                token=auth_token,
            )
            self.assertEqual(c_bad, 400, "Setting run_code_trusted_minutes > 10 must return HTTP 400")
            self.assertIn("between 0 and 10", r_bad.get("error", ""))

            # Setting <= 10 works with confirmation token
            c_conf, r_conf, _ = self._api_req(
                port,
                "/api/config",
                method="POST",
                body={"run_code_trusted_minutes": 10},
                cookie=auth_cookie,
                token=auth_token,
            )
            self.assertEqual(c_conf, 200)
            tok = r_conf.get("token")
            c_ok, r_ok, _ = self._api_req(
                port,
                "/api/config",
                method="POST",
                body={"run_code_trusted_minutes": 10, "confirm_token": tok},
                cookie=auth_cookie,
                token=auth_token,
            )
            self.assertEqual(c_ok, 200)
            self.assertEqual(server.get_config()["run_code_trusted_minutes"], 10)

            # Record approval
            server.RUN_CODE_TRUST_STATE.record_approval()
            self.assertTrue(server.RUN_CODE_TRUST_STATE.is_trusted(10))

            # Trigger a tainted turn -> RUN_CODE_TRUST_STATE is reset
            server.execute_model_tags([("BRIEFING", "news", 0, 10)], server.get_config(), source="pc", is_tainted=True)
            self.assertFalse(server.RUN_CODE_TRUST_STATE.is_trusted(10), "Tainted turn must immediately reset RUN_CODE_TRUST_STATE")
        finally:
            srv.shutdown()
            srv.server_close()

    # -------------------------------------------------------------
    # 6. SKILL_GIT HARDENING
    # -------------------------------------------------------------
    def test_item6_skill_git_hardening_subcommands_env_and_locks(self):
        """
        Follow-Up 6:
        - skill_git allows ONLY status, log, diff, show, clone.
        - Subcommands like push, pull, commit, branch, checkout, switch, add are refused.
        - Clears GIT_* environment variables and sets GIT_CONFIG_NOSYSTEM=1.
        - Injects --no-optional-locks into git command.
        """
        cfg = {"allow_outside_workspace": False}

        # 1. Allowed subcommands pass to sandboxed process
        for allowed in ["status", "log", "diff", "show", "clone https://github.com/example/repo.git"]:
            with patch.object(server, "run_sandboxed_process", return_value=(0, "git output", "")) as mock_proc:
                res = server.skill_git(allowed, cfg=cfg)
                self.assertIn("git output", res)
                cmd = mock_proc.call_args[0][0]
                self.assertIn("--no-optional-locks", cmd)
                self.assertIn("-c", cmd)
                self.assertIn("core.fsmonitor=false", cmd)
                self.assertIn("protocol.ext.allow=never", cmd)

                env = mock_proc.call_args[1].get("extra_env", {})
                self.assertEqual(env.get("GIT_CONFIG_NOSYSTEM"), "1")
                self.assertIn("GIT_CONFIG_GLOBAL", env)
                self.assertIn("GIT_TERMINAL_PROMPT", env)
                # Verify no parent GIT_* leaked into env
                for k in env:
                    if k.startswith("GIT_"):
                        self.assertIn(k, ("GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_TERMINAL_PROMPT"))

        # 2. Disallowed subcommands are refused immediately
        for disallowed in ["commit -m 'msg'", "push", "pull", "branch", "checkout -b new", "switch -c test", "add .", "stash"]:
            res_bad = server.skill_git(disallowed, cfg=cfg)
            self.assertIn("is not permitted", res_bad)


if __name__ == "__main__":
    unittest.main()
