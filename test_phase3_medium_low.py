"""
Unit tests for Phase 3: Medium / Low Priority Security & Reliability Enhancements.
- 3A: Request Limits (10 MB body cap, HTTP 413, JSON depth limit, 30s socket timeout)
- 3B: CDP Browser Flags (--remote-debugging-address=127.0.0.1, --remote-allow-origins)
- 3C: Confirmation Preview (Full command/code up to 20,000 chars with explicit truncated marker)
- 3D: Telemetry Masking (Authorization: Bearer, api_key=, tokens, config secrets in logs/events/activity)
- 3E: Windows Reserved Names (CON, PRN, AUX, NUL, COM1-9, LPT1-9 rejected)
- 3F: Cyber Mode Tool Restrictions (PLAY, VOLUME, BROWSER_YOUTUBE, SMART_HOME blocked in Cyber mode)
"""
import io
import json
import time
import unittest
from unittest.mock import patch, MagicMock

import server
import nova_browser
import scheduler_engine

class TestPhase3MediumLow(unittest.TestCase):
    # --- 3A: REQUEST LIMITS ---
    def test_request_body_size_and_depth_limits(self):
        class DummyHandler(server.BaseHandler):
            def __init__(self, raw_bytes, headers_dict):
                self.headers = headers_dict
                self.rfile = io.BytesIO(raw_bytes)
                self.sent_status = None
                self.sent_body = None

            def _send(self, code, body, ctype="application/json"):
                self.sent_status = code
                self.sent_body = body

        # 1. Body exceeds 10 MB -> 413 Payload Too Large
        oversized = 11 * 1024 * 1024
        h1 = DummyHandler(b"", {"Content-Length": str(oversized)})
        res1 = h1._body()
        self.assertIsNone(res1)
        self.assertEqual(h1.sent_status, 413)

        # 2. JSON depth limit exceeded (> 50 levels) -> 400 Bad Request
        deep = {"a": None}
        curr = deep
        for _ in range(60):
            curr["a"] = {"a": None}
            curr = curr["a"]
        deep_bytes = json.dumps(deep).encode("utf-8")
        h2 = DummyHandler(deep_bytes, {"Content-Length": str(len(deep_bytes))})
        res2 = h2._body()
        self.assertIsNone(res2)
        self.assertEqual(h2.sent_status, 400)

        # 3. Timeout is set to 30s on BaseHandler
        self.assertEqual(server.BaseHandler.timeout, 30)

    # --- 3B: CDP BROWSER FLAGS ---
    def test_cdp_browser_flags(self):
        with patch("nova_browser.is_cdp_available", return_value=False), \
             patch("nova_browser.get_browser_executable", return_value="fake_chrome.exe"), \
             patch("nova_browser.subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            res = nova_browser.launch_browser()
            self.assertTrue(mock_popen.called)
            args = mock_popen.call_args[0][0]
            self.assertIn("--remote-debugging-address=127.0.0.1", args)
            self.assertIn(f"--remote-allow-origins=http://127.0.0.1:{nova_browser.CDP_PORT}", args)

    # --- 3C: CONFIRMATION PREVIEW TRUNCATION & LENGTH LIMITS ---
    def test_confirmation_preview_truncation(self):
        # 1. RUN_CODE > 2000 chars is rejected immediately with error
        huge_cmd = "echo " + ("A" * 25000)
        tags = [("RUN_CODE", f"python | {huge_cmd}", 0, 100)]
        cfg = dict(server.DEFAULT_CONFIG)
        cfg["confirm_destructive"] = True

        tag_result = server.execute_model_tags(tags, cfg, mode="developer", source="pc", is_tainted=False)
        self.assertIsNone(tag_result.get("pending_info"))
        self.assertIn("exceeds maximum allowed length of 2,000 characters", tag_result["actions"][0]["result"])

        # 2. Confirmation preview: 20,000-char truncation removed for actions requiring confirmation
        huge_file_content = "bigfile.txt|" + ("A" * 25000)
        file_tags = [("WRITE_FILE", huge_file_content, 0, 100)]
        file_result = server.execute_model_tags(file_tags, cfg, mode="developer", source="pc", is_tainted=True)
        pending = file_result.get("pending_info")
        self.assertIsNotNone(pending)
        preview = pending.get("preview", "")
        self.assertNotIn("truncated", preview)
        self.assertEqual(len(preview), len(huge_file_content))

    # --- 3D: TELEMETRY MASKING ---
    def test_telemetry_masking(self):
        # 1. Direct mask_secrets function
        sample1 = "Authorization: Bearer sk-1234567890abcdef"
        masked1 = server.mask_secrets(sample1)
        self.assertNotIn("1234567890abcdef", masked1)
        self.assertIn("Authorization: Bearer sk-1****", masked1)

        sample2 = "Connection string: api_key=sk-1234567890&token=sec9876543210"
        masked2 = server.mask_secrets(sample2)
        self.assertNotIn("1234567890", masked2)
        self.assertNotIn("9876543210", masked2)

        # 2. add_event telemetry masking
        ev = server.add_event(user="test", payload="Bearer secrettoken123456789")
        self.assertNotIn("secrettoken123456789", ev["payload"])

        # 3. act_step telemetry masking
        jid = server.act_start("desktop", "Run curl with api_key=sk-secretvalue9876")
        server.act_step(jid, "CMD", "curl http://api.com?api_key=sk-secretvalue9876", 0.5)
        st = server.activity_state()
        job = next((j for j in st["jobs"] if j["id"] == jid), None)
        self.assertIsNotNone(job)
        self.assertNotIn("secretvalue9876", job["task"])
        self.assertNotIn("secretvalue9876", job["steps"][0]["arg"])
        server.act_end(jid, ok=True)

    # --- 3E: WINDOWS RESERVED NAMES ---
    def test_windows_reserved_names_rejected(self):
        reserved_samples = ["CON.txt", "aux", "com1", "nul.py", "prn  ", "LPT9.dat"]
        for res_name in reserved_samples:
            # resolve_workspace_path raises ValueError
            with self.assertRaises(ValueError) as ctx:
                server.resolve_workspace_path(res_name)
            self.assertIn("Reserved Windows device name", str(ctx.exception))

            # File writing tool rejects cleanly without writing
            write_res = server.run_skill({}, "WRITE_FILE", f"{res_name} | payload")
            self.assertIn("Reserved Windows device name", write_res)

        # Normal relative path is accepted
        normal_p = server.resolve_workspace_path("valid_test_doc.txt")
        self.assertEqual(normal_p.name, "valid_test_doc.txt")

    # --- 3F: CYBER MODE TOOL RESTRICTION ---
    def test_cyber_mode_tool_restrictions(self):
        # Leisure / non-cyber tools return 'Not available in Cyber Mode'
        blocked_in_cyber = ["PLAY", "VOLUME", "BROWSER_YOUTUBE", "SMART_HOME", "OPEN_APP", "SYSTEM"]
        for tool in blocked_in_cyber:
            res = server.run_skill({}, tool, "arg", mode="cyber")
            self.assertEqual(res, "Not available in Cyber Mode", f"Tool {tool} should be blocked in Cyber Mode")

        # Allowed tools in Cyber Mode run without that rejection
        res_note = server.run_skill({}, "NOTE", "Cyber Finding | High severity CVE note", mode="cyber")
        self.assertNotEqual(res_note, "Not available in Cyber Mode")
        self.assertIn("Saved note", res_note)

    # --- FIX 1: API STATE ALLOWLIST & DPAPI COVERAGE ---
    def test_api_state_allowlist_and_dpapi_coverage(self):
        import tempfile
        from pathlib import Path

        class StateTestHandler(server.Handler):
            def __init__(self, path="/api/state"):
                self.path = path
                self.headers = {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"}
                self.command = "GET"
                self.requestline = f"GET {path} HTTP/1.1"
                self.sent_status = None
                self.sent_data = None

            def _send(self, code, body, ctype="application/json"):
                self.sent_status = code
                self.sent_data = body

        fake_cfg = dict(server.DEFAULT_CONFIG)
        for s in server.SECRET_FIELDS:
            fake_cfg[s] = f"fake_secret_{s}_value"
        fake_cfg["foo_secret_key"] = "unauthorized_leak"

        h = StateTestHandler()
        with patch("server.get_config", return_value=fake_cfg):
            h.do_GET()

        self.assertEqual(h.sent_status, 200)
        cfg_resp = h.sent_data["config"]

        # 1. Not a single secret value is returned
        for s in server.SECRET_FIELDS:
            self.assertNotIn(s, cfg_resp, f"Secret field {s} must not be present in /api/state response")
            self.assertTrue(cfg_resp.get(f"{s}_set"), f"{s}_set boolean flag should be True")

        # 2. Unknown invented field dropped by allowlist
        self.assertNotIn("foo_secret_key", cfg_resp, "Invented field foo_secret_key must be dropped by allowlist")
        self.assertNotIn("foo_secret_key_set", cfg_resp)

        # 3. DPAPI covers all SECRET_FIELDS on disk and decrypts in memory
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "config.json"
            orig_cfg = server.CONFIG_FILE
            server.CONFIG_FILE = cfg_path
            try:
                data = {s: f"val_{s}" for s in server.SECRET_FIELDS}
                data["encrypt_keys"] = True
                server.save_json(cfg_path, data)
                loaded = server.get_config()
                with open(cfg_path, "r", encoding="utf-8") as f:
                    disk_data = json.load(f)
                for s in server.SECRET_FIELDS:
                    if server.is_dpapi_available():
                        self.assertTrue(disk_data[s].startswith("dpapi:"), f"{s} should be encrypted with DPAPI on disk")
                    self.assertEqual(loaded[s], f"val_{s}", f"{s} should be decrypted in-memory")
            finally:
                server.CONFIG_FILE = orig_cfg

    # --- FIX 2: CYBER MODE PROMPT VS ALLOWLIST DRIFT ---
    def test_cyber_prompt_matches_allowed_tools_strictly(self):
        import re
        advertised = set(re.findall(r"\[\[([A-Z0-9_]+)", server.CYBER_SKILL_DOC))
        self.assertEqual(advertised, server.CYBER_ALLOWED_TOOLS)
        self.assertEqual(len(server.CYBER_ALLOWED_TOOLS), 13)
        self.assertEqual(len(advertised), 13)
        sys_prompt = server.build_system({}, {"name": "Nova", "prompt": ""}, mode="cyber")
        sys_tags = set(re.findall(r"\[\[([A-Z0-9_]+)", sys_prompt))
        self.assertEqual(sys_tags, server.CYBER_ALLOWED_TOOLS)

    # --- FIX 3: AUTOMATION TAINT & DESKTOP CONFIRM ONLY ---
    def test_automation_taint_and_desktop_confirm_only(self):
        server.PENDING_ACTIONS.clear()
        mock_reply = "Scheduled run. [[WRITE_FILE: test_auto.py | print(1)]]"
        try:
            with patch("server.call_llm", return_value=mock_reply):
                res = server.chat("Run hourly backup", source="scheduler", is_automation=True)

            self.assertIsNotNone(res.get("pending"), f"Expected pending action, got: {res}")
            pending_id = res["pending"]["id"]
            self.assertIn(pending_id, server.PENDING_ACTIONS)
            pending_obj = server.PENDING_ACTIONS[pending_id]
            self.assertEqual(pending_obj.get("source"), "scheduler")
            self.assertTrue(pending_obj.get("is_tainted"))

            # Typing 'yes' in chat does NOT approve it
            with patch("server.call_llm", return_value="fallback"):
                res_yes = server.chat("yes", source="pc")
            self.assertIn("requires your confirmation via the desktop Allow button", res_yes["reply"])
            self.assertIn(pending_id, server.PENDING_ACTIONS)

            # /api/confirm with the desktop session does approve it
            class ConfirmTestHandler(server.Handler):
                def __init__(self, body_dict):
                    self.path = "/api/confirm"
                    self.headers = {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"}
                    self.command = "POST"
                    self.requestline = "POST /api/confirm HTTP/1.1"
                    self._body_override = body_dict
                    self.sent_status = None
                    self.sent_data = None
                def _body(self):
                    return self._body_override
                def _send(self, code, body, ctype="application/json"):
                    self.sent_status = code
                    self.sent_data = body

            h = ConfirmTestHandler({"id": pending_id, "approve": True})
            with patch("server.run_skill", return_value="File created successfully"):
                h.do_POST()

            self.assertEqual(h.sent_status, 200)
            self.assertTrue(h.sent_data.get("ok"))
            self.assertTrue(h.sent_data.get("approved"))
            self.assertNotIn(pending_id, server.PENDING_ACTIONS)
        finally:
            server.PENDING_ACTIONS.clear()

    # --- FIX 4: TAGS INSIDE MARKDOWN CODE FENCES ---
    def test_tags_inside_code_fences_ignored(self):
        # 1. Tag inside ```python ... ``` is ignored, tag outside is executed
        t1 = "Example code:\n```python\n[[WRITE_FILE: test.py | print(1)]]\n```\nOutside: [[RUN_CODE: python | print(2)]]"
        tags1 = server.extract_tags(t1)
        self.assertEqual(len(tags1), 1)
        self.assertEqual(tags1[0][0], "RUN_CODE")
        self.assertEqual(tags1[0][1], "python | print(2)")

        # 2. Tag inside single backticks is executed
        t2 = "In inline code: `[[NOTE: my note | hello]]`"
        tags2 = server.extract_tags(t2)
        self.assertEqual(len(tags2), 1)
        self.assertEqual(tags2[0][0], "NOTE")
        self.assertEqual(tags2[0][1], "my note | hello")

        # 3. Unclosed ``` does not throw and treats rest of text as fenced
        t3 = "Unclosed block:\n```\n[[CMD: dir]]\nprint('hello')"
        tags3 = server.extract_tags(t3)
        self.assertEqual(len(tags3), 0)

        # 4. Prompt instruction present in both Developer and Cyber mode
        sys_dev = server.build_system({}, {"name": "Nova", "prompt": ""}, mode="developer")
        self.assertIn("Do not put tool tags inside code blocks", sys_dev)
        sys_cyber = server.build_system({}, {"name": "Nova", "prompt": ""}, mode="cyber")
        self.assertIn("Do not put tool tags inside code blocks", sys_cyber)

    # --- FIX 5: SMART_HOME REDIRECTS BLOCKED ---
    def test_smart_home_redirects_blocked(self):
        import http.server
        import threading

        target_called = [False]

        class RedirectHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
                self.end_headers()
            def do_POST(self):
                self.do_GET()
            def log_message(self, *args):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), RedirectHandler)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.handle_request, daemon=True)
        t.start()

        try:
            res = server.skill_smart_home(f"http://127.0.0.1:{port}/control")
            self.assertEqual(res, "Refused: smart home redirects are blocked for security.")
            self.assertFalse(target_called[0])
        finally:
            srv.server_close()

    # --- FIX 6: SMART_HOME IP & SCHEME RESTRICTIONS ---
    def test_smart_home_ip_and_scheme_restrictions(self):
        # 1. Non-http(s) schemes rejected immediately
        res_file = server.skill_smart_home("file:///etc/passwd")
        self.assertIn("Refused", res_file)
        self.assertIn("only supports http and https", res_file)

        res_ftp = server.skill_smart_home("ftp://127.0.0.1/resource")
        self.assertIn("Refused", res_ftp)
        self.assertIn("only supports http and https", res_ftp)

        # 2. 169.254.0.0/16 (link-local / cloud metadata) rejected unconditionally
        res_meta = server.skill_smart_home("http://169.254.169.254/latest/meta-data/")
        self.assertIn("Refused", res_meta)
        self.assertIn("169.254.0.0/16", res_meta)

        # Even if 169.254.169.254 is configured in smart_home_hosts, it MUST still be rejected
        with patch("server.get_config", return_value={"smart_home_hosts": ["169.254.169.254"]}):
            res_meta_cfg = server.skill_smart_home("http://169.254.169.254/latest/meta-data/")
            self.assertIn("Refused", res_meta_cfg)
            self.assertIn("169.254.0.0/16", res_meta_cfg)

        # 3. Public IP address rejected when not in smart_home_hosts
        res_public = server.skill_smart_home("http://8.8.8.8/test")
        self.assertIn("Refused", res_public)
        self.assertIn("not an allowed private LAN address", res_public)

        # 4. Public IP address allowed when explicitly in smart_home_hosts
        ok, reason = server.is_allowed_smart_home_host("8.8.8.8", {"smart_home_hosts": ["8.8.8.8"]})
        self.assertTrue(ok)
        self.assertEqual(reason, "OK")

        # 5. LAN private IP addresses allowed without special configuration
        for lan_ip in ("127.0.0.1", "192.168.1.100", "10.0.0.1", "172.16.0.5"):
            ok_lan, _ = server.is_allowed_smart_home_host(lan_ip, {})
            self.assertTrue(ok_lan, f"Expected {lan_ip} to be allowed")

        # 6. Real local HTTP request to test server succeeds
        import http.server
        import threading

        class SmartHomeEchoHandler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                self.rfile.read(length)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "light_turned_on"}')
            def log_message(self, *args):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), SmartHomeEchoHandler)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.handle_request, daemon=True)
        t.start()

        try:
            res_live = server.skill_smart_home(f"http://127.0.0.1:{port}/api/toggle | POST | {{\"entity_id\": \"light.living_room\"}}")
            self.assertIn("succeeded (200)", res_live)
            self.assertIn("light_turned_on", res_live)
        finally:
            srv.server_close()

    # --- FIX 7: _LOCAL_ONLY STRICT PORT MATCHING ---
    def test_local_only_strict_port_matching(self):
        class MockReq:
            def __init__(self, headers, command="GET"):
                self.headers = headers
                self.command = command

        # Handler: expects port 8765
        self.assertTrue(server.Handler._local_only(MockReq({"Host": "127.0.0.1:8765"})))
        self.assertTrue(server.Handler._local_only(MockReq({"Host": "localhost:8765"})))
        # No port -> False
        self.assertFalse(server.Handler._local_only(MockReq({"Host": "127.0.0.1"})))
        self.assertFalse(server.Handler._local_only(MockReq({"Host": "localhost"})))
        # Wrong port -> False
        self.assertFalse(server.Handler._local_only(MockReq({"Host": "127.0.0.1:8766"})))
        self.assertFalse(server.Handler._local_only(MockReq({"Host": "127.0.0.1:8000"})))
        # Non-local host -> False
        self.assertFalse(server.Handler._local_only(MockReq({"Host": "attacker.com:8765"})))
        # Mismatched Origin port -> False
        self.assertFalse(server.Handler._local_only(MockReq({"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8766"})))

        # RemoteHandler: expects port 8766
        self.assertTrue(server.RemoteHandler._local_only(MockReq({"Host": "127.0.0.1:8766"})))
        self.assertTrue(server.RemoteHandler._local_only(MockReq({"Host": "localhost:8766"})))
        # Port 8765 rejected on RemoteHandler -> False
        self.assertFalse(server.RemoteHandler._local_only(MockReq({"Host": "127.0.0.1:8765"})))
        # No port -> False
        self.assertFalse(server.RemoteHandler._local_only(MockReq({"Host": "127.0.0.1"})))
        # Non-local host -> False
        self.assertFalse(server.RemoteHandler._local_only(MockReq({"Host": "attacker.com:8766"})))

    # --- FIX 8: AUTOMATION TOKENS EXPIRY, CAP, AND ONE-TIME TIMER ACTIONS ---
    def test_automation_tokens_expiry_cap_and_timer_actions(self):
        sched = scheduler_engine.SCHEDULER

        # 1. Token 5-minute expiry
        tok = sched.issue_automation_token()
        self.assertIsInstance(tok, str)
        # Advance expiration to the past
        with sched.lock:
            sched.active_automation_tokens[tok] = time.time() - 10
        self.assertFalse(sched.validate_and_consume_automation_token(tok))

        # 2. Token cap (MAX_AUTOMATION_TOKENS = 50) drops oldest
        issued_tokens = []
        for _ in range(55):
            issued_tokens.append(sched.issue_automation_token())

        with sched.lock:
            self.assertLessEqual(len(sched.active_automation_tokens), 50)

        # The first 5 issued tokens must have been purged/dropped
        for old_tok in issued_tokens[:5]:
            self.assertFalse(sched.validate_and_consume_automation_token(old_tok))

        # The newest 50 tokens must validate and be consumed on use
        for new_tok in issued_tokens[5:]:
            self.assertTrue(sched.validate_and_consume_automation_token(new_tok))
            # Second validation attempt must fail (consumed)
            self.assertFalse(sched.validate_and_consume_automation_token(new_tok))

        # 3. One-time timer carrying an action produces notification with token & action
        with sched.lock:
            sched.timers.clear()
            sched.notifications.clear()

        # Test skill invocation with action: [[REMIND: 1s | Clean cache | CMD: del temp.log]]
        res_skill = server.run_skill({}, "REMIND", "1s | Clean cache | CMD: del temp.log")
        self.assertIn("Scheduled reminder", res_skill)
        self.assertEqual(len(sched.timers), 1)
        timer_item = sched.timers[0]
        self.assertEqual(timer_item["action"], "CMD: del temp.log")

        # Simulate timer triggering
        timer_item["due"] = time.time() - 1
        sched.check_timers()

        notifs = sched.get_pending_notifications()
        self.assertEqual(len(notifs), 1)
        notif = notifs[0]
        self.assertEqual(notif["type"], "timer")
        self.assertEqual(notif["action"], "CMD: del temp.log")
        self.assertIn("automation_token", notif)
        auto_token = notif["automation_token"]

        # 4. Turn with invalid token rejected by /api/chat
        class MockChatReq:
            def __init__(self, body):
                self.headers = {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"}
                self.command = "POST"
                self.path = "/api/chat"
                self._test_body = body
                self.sent_status = None
                self.sent_data = None
            _local_only = server.Handler._local_only
            do_POST = server.Handler.do_POST
            def _body(self):
                return self._test_body
            def _send(self, status, data, ctype="application/json"):
                self.sent_status = status
                self.sent_data = data

        bad_req = MockChatReq({
            "message": "CMD: del temp.log",
            "is_automation": True,
            "automation_token": "fake_invalid_token"
        })
        bad_req.do_POST()
        self.assertEqual(bad_req.sent_status, 403)
        self.assertIn("Invalid or expired automation token", bad_req.sent_data.get("error", ""))

        # 5. Turn with valid token succeeds, consumes token, and is tainted
        good_req = MockChatReq({
            "message": "CMD: del temp.log",
            "is_automation": True,
            "automation_token": auto_token
        })
        try:
            with patch("server.call_llm", return_value="Deleting logs now. [[CMD: del temp.log]]"):
                good_req.do_POST()

            self.assertEqual(good_req.sent_status, 200)
            # Token consumed: cannot be reused
            self.assertFalse(sched.validate_and_consume_automation_token(auto_token))

            # Turn is tainted: pending action created requiring user confirmation
            pending = good_req.sent_data.get("pending")
            self.assertIsNotNone(pending, f"Expected pending action for tainted CMD turn, got: {good_req.sent_data}")
            pending_id = pending["id"]
            self.assertIn(pending_id, server.PENDING_ACTIONS)
            pending_obj = server.PENDING_ACTIONS[pending_id]
            self.assertTrue(pending_obj["is_tainted"])

            # Conversational approval is strictly blocked for tainted turns
            conv_approve = server.chat("yes", source="pc")
            self.assertIn("desktop Allow button", conv_approve["reply"])
        finally:
            server.PENDING_ACTIONS.clear()

if __name__ == "__main__":
    unittest.main()
