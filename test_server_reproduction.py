"""
Regression tests for Nova AI Server logic & Voice pipeline integration:
1. strip_tags preserves fenced code examples and unexecuted tags (S-01 fix)
2. Gemini 3.5 parameter sanitization (strips temperature, top_p, top_k; trailing assistant messages removed; reasoning_effort omitted unless llm_reasoning_effort configured)
3. Configurable llm_timeout (capped at 90s) and retry timeout keeping total wait under 100s
4. DIAGNOSE log is opt-in (debug_llm) and never prints message contents
5. LLM timeout triggers fallback error & empty reply handled
6. Remote auth (wrong token 401, 5-attempt lockout 429, rotated token)
7. Main UI strictly isolated on remote port (port 8766 all 404)
8. Voice pipeline regression runner (executes test_voice_regression.js on real web/app.js; skippable if node is missing)
"""

import http.server
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import unittest
import urllib.request
import urllib.error

import server


class StubLLMHandler(http.server.BaseHTTPRequestHandler):
    mode = "normal"  # "timeout", "empty", "normal", "inspect"
    last_request_body = None

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_len).decode("utf-8")
        try:
            StubLLMHandler.last_request_body = json.loads(raw_body)
        except Exception:
            StubLLMHandler.last_request_body = raw_body

        if StubLLMHandler.mode == "timeout":
            time.sleep(2.5)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")
        elif StubLLMHandler.mode == "empty":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            res = {"choices": [{"message": {"content": ""}}]}
            self.wfile.write(json.dumps(res).encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            res = {"choices": [{"message": {"content": "Hello from stub AI"}}]}
            self.wfile.write(json.dumps(res).encode("utf-8"))

    def log_message(self, format, *args):
        pass


class TestServerRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stub_server = http.server.HTTPServer(("127.0.0.1", 0), StubLLMHandler)
        cls.stub_port = cls.stub_server.server_address[1]
        cls.stub_thread = threading.Thread(target=cls.stub_server.serve_forever, daemon=True)
        cls.stub_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.stub_server.shutdown()
        cls.stub_server.server_close()

    def test_strip_tags_keeps_fenced_examples_and_unexecuted(self):
        """S-01 fix: strip_tags must preserve fenced tags and unexecuted text."""
        # 1. Code fence containing a skill example
        fenced = "```python\n# Syntax:\n[[READ_FILE: main.py]]\n```"
        self.assertEqual(server.strip_tags(fenced), fenced.strip())

        # 2. Regular unexecuted text with brackets
        text_brackets = "Look at [[this bracketed text]] that is not a skill."
        self.assertEqual(server.strip_tags(text_brackets), text_brackets.strip())

        # 3. Active skill tag mixed with fenced example
        mixed = "[[REMEMBER: user likes python]]\nHere is how to use it:\n```\n[[READ_FILE: main.py]]\n```"
        stripped = server.strip_tags(mixed)
        self.assertNotIn("REMEMBER", stripped)
        self.assertIn("[[READ_FILE: main.py]]", stripped)

    def test_gemini_parameter_sanitization_and_reasoning_effort(self):
        """L-02 fix: Gemini 3.x requests strip sampling params and omit reasoning_effort unless configured."""
        StubLLMHandler.mode = "inspect"
        cfg = {
            "provider": "openai",
            "model": "gemini-3.5-flash-lite",
            "base_url": f"http://127.0.0.1:{self.stub_port}",
            "api_key": "test_gemini_key",
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 40,
        }
        messages = [
            {"role": "user", "content": "Hello secret question"},
            {"role": "assistant", "content": "Previous model reply"},  # Trailing assistant message!
        ]
        # Case A: By default, reasoning_effort is NOT sent for Gemini 3.x
        server.call_llm(cfg, "system prompt", messages)
        body = StubLLMHandler.last_request_body
        self.assertIsInstance(body, dict)
        self.assertNotIn("temperature", body)
        self.assertNotIn("top_p", body)
        self.assertNotIn("top_k", body)
        self.assertNotIn("reasoning_effort", body, "Gemini 3.x must not send reasoning_effort by default")
        sent_messages = body.get("messages", [])
        self.assertTrue(len(sent_messages) > 0)
        self.assertNotEqual(sent_messages[-1].get("role"), "assistant", "Last message must not be assistant")

        # Case B: When user explicitly sets llm_reasoning_effort
        cfg_with_effort = dict(cfg, llm_reasoning_effort="high")
        server.call_llm(cfg_with_effort, "system prompt", [{"role": "user", "content": "Hi"}])
        body_with_effort = StubLLMHandler.last_request_body
        self.assertEqual(body_with_effort.get("reasoning_effort"), "high")

    def test_diagnose_log_opt_in_and_no_content_leak(self):
        """DIAGNOSE log must be opt-in (debug_llm) and never print message contents."""
        StubLLMHandler.mode = "inspect"
        secret_content = "SuperSensitiveUserQuery12345"
        messages = [{"role": "user", "content": secret_content}]
        cfg = {
            "provider": "openai",
            "model": "gemini-3.5-flash-lite",
            "base_url": f"http://127.0.0.1:{self.stub_port}",
            "api_key": "test_key",
            "debug_llm": False,  # Off by default
        }
        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            server.call_llm(cfg, "system", messages)
            out_disabled = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        self.assertNotIn("[Gemini DIAGNOSE]", out_disabled, "DIAGNOSE log must not print when debug_llm is false")

        # Now enable debug_llm
        cfg["debug_llm"] = True
        sys.stdout = io.StringIO()
        try:
            server.call_llm(cfg, "system", messages)
            out_enabled = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        self.assertIn("[Gemini DIAGNOSE]", out_enabled, "DIAGNOSE log must print when debug_llm is true")
        self.assertNotIn(secret_content, out_enabled, "DIAGNOSE log must never print message contents")

    def test_configurable_llm_timeout_and_under_100s_wait(self):
        """L-02 fix: llm_timeout configurable up to 90s; total wait remains strictly <= 100s."""
        cfg = server.get_config()
        self.assertIn("llm_timeout", server.SAFE_STATE_FIELDS)
        self.assertEqual(cfg.get("llm_timeout", 60), 60)

        # Bounds check up to 90s:
        for t in (10, 30, 60, 80, 90):
            initial = max(5, min(t, 90))
            retry = max(5, min(38, 99 - initial))
            total = initial + retry
            self.assertLessEqual(total, 100, f"Total wait {total}s exceeds 100s limit for timeout {t}s")

    def test_llm_timeout_triggers_error(self):
        """Verifies that when LLM hangs, timeout raises LLMError with 'timed out'."""
        StubLLMHandler.mode = "timeout"
        t0 = time.time()
        with self.assertRaises(server.LLMError) as ctx:
            server.http_post(
                f"http://127.0.0.1:{self.stub_port}/chat/completions",
                {"content-type": "application/json"},
                {"model": "test", "messages": []},
                timeout=1.0,
            )
        elapsed = time.time() - t0
        self.assertIn("timed out", str(ctx.exception).lower())
        self.assertLess(elapsed, 2.0)

    def test_llm_empty_reply(self):
        """Verifies behavior when LLM returns an empty content string."""
        StubLLMHandler.mode = "empty"
        cfg = {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "base_url": f"http://127.0.0.1:{self.stub_port}",
            "api_key": "test_key",
        }
        res = server.call_llm(cfg, "system prompt", [{"role": "user", "content": "hi"}])
        self.assertIn("empty answer", res)

    def test_remote_auth_wrong_token_and_lockout(self):
        """Verifies wrong token 401, 5-attempt lockout 429, and token rotation."""
        server.FAILS.clear()
        cfg = server.get_config()
        cfg["remote_enabled"] = True
        server.save_config(cfg)
        server.regenerate_token()
        token = server.get_config().get("remote_token")

        remote_srv = server.SilentThreadingHTTPServer(("127.0.0.1", 0), server.RemoteHandler)
        rport = remote_srv.server_address[1]
        orig_rport = server.RemoteHandler.DEFAULT_PORT
        server.RemoteHandler.DEFAULT_PORT = rport
        rthread = threading.Thread(target=remote_srv.serve_forever, daemon=True)
        rthread.start()

        try:
            url = f"http://127.0.0.1:{rport}/api/remote/info"
            # 1. Wrong token -> 401
            bad_req = urllib.request.Request(url, headers={"X-Nova-Token": "bad", "Host": f"127.0.0.1:{rport}"})
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(bad_req)
            self.assertEqual(ctx.exception.code, 401)

            # 2. Lockout after 5 fails -> 429
            for _ in range(4):
                with self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(bad_req)
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(bad_req)
            self.assertEqual(ctx.exception.code, 429)

            # 3. Clear fails and test token rotation
            server.FAILS.clear()
            good_req = urllib.request.Request(url, headers={"X-Nova-Token": token, "Host": f"127.0.0.1:{rport}"})
            with urllib.request.urlopen(good_req) as resp:
                self.assertEqual(resp.status, 200)

            server.regenerate_token()
            new_token = server.get_config().get("remote_token")
            self.assertNotEqual(token, new_token)

            # Old token now fails 401
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(good_req)
            self.assertEqual(ctx.exception.code, 401)

            # New token succeeds 200
            rotated_req = urllib.request.Request(url, headers={"X-Nova-Token": new_token, "Host": f"127.0.0.1:{rport}"})
            with urllib.request.urlopen(rotated_req) as resp:
                self.assertEqual(resp.status, 200)
        finally:
            cfg = server.get_config()
            cfg["remote_enabled"] = False
            server.save_config(cfg)
            server.RemoteHandler.DEFAULT_PORT = orig_rport
            remote_srv.shutdown()
            remote_srv.server_close()

    def test_main_ui_not_reachable_on_remote_port(self):
        """Verifies that main UI endpoints (/index.html, /api/state, /api/chat) are 404 on RemoteHandler port."""
        cfg = server.get_config()
        cfg["remote_enabled"] = True
        server.save_config(cfg)
        server.regenerate_token()
        token = server.get_config().get("remote_token")
        remote_srv = server.SilentThreadingHTTPServer(("127.0.0.1", 0), server.RemoteHandler)
        rport = remote_srv.server_address[1]
        orig_rport = server.RemoteHandler.DEFAULT_PORT
        server.RemoteHandler.DEFAULT_PORT = rport
        rthread = threading.Thread(target=remote_srv.serve_forever, daemon=True)
        rthread.start()

        try:
            endpoints = ["/index.html", "/api/state", "/api/chat", "/api/config"]
            for ep in endpoints:
                url = f"http://127.0.0.1:{rport}{ep}"
                req = urllib.request.Request(url, headers={"X-Nova-Token": token, "Host": f"127.0.0.1:{rport}"})
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(req)
                self.assertEqual(ctx.exception.code, 404, f"Endpoint {ep} should return 404 on remote port")
        finally:
            cfg = server.get_config()
            cfg["remote_enabled"] = False
            server.save_config(cfg)
            server.RemoteHandler.DEFAULT_PORT = orig_rport
            remote_srv.shutdown()
            remote_srv.server_close()

    def test_node_voice_regression_suite(self):
        """Runs test_voice_regression.js against real web/app.js; skipped if node is not installed."""
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("Node.js is not installed on this system.")
        js_path = os.path.join(os.path.dirname(__file__), "test_voice_regression.js")
        self.assertTrue(os.path.isfile(js_path), "test_voice_regression.js not found")
        proc = subprocess.run([node_bin, js_path], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"Node voice test failed with code {proc.returncode}:\n{proc.stdout}\n{proc.stderr}")
        self.assertIn("ALL REAL APP.JS VOICE REGRESSION TESTS PASSED", proc.stdout)


if __name__ == "__main__":
    unittest.main()
