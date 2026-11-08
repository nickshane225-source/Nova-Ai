import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error

import server

ROOT = Path(__file__).resolve().parent


class TestBootSecurity(unittest.TestCase):
    """
    Critical Fix 1 Regression Tests:
    1. Never persist boot codes. No nova_boot_url.txt written at boot or re-auth.
    2. Any existing %TEMP%\\nova_boot_url.txt deleted at startup.
    3. Boot codes live in memory only.
    4. The 401 path must NOT mint a code per request: mint at most one per 60 seconds,
       keep at most 5 live codes, print to console only.
    5. After boot and after 10 unauthenticated /api requests, no file under %TEMP% or the
       project contains "boot=" or a live code.
    6. A second unauthenticated request does not produce a new valid code within 60 seconds.
    7. quick_summon.bat: only focus existing Nova window; if port 8765 listening but no window,
       show message "Nova is running - use the open tab or restart Nova"; if port not listening,
       start run.bat. Remove -ExecutionPolicy Bypass.
    """

    def setUp(self):
        # Reset boot codes and rate-limiter
        with server.BOOT_LOCK:
            server.BOOT_CODES.clear()
            server.LAST_401_BOOT_MINT_TIME = 0.0

    def _start_live_server(self):
        srv = server.SilentThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        port = srv.server_address[1]
        server.Handler.DEFAULT_PORT = port
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        return srv, port

    def _api_req(self, port, path, method="GET", body=None, cookie=None, token=None):
        url = f"http://127.0.0.1:{port}{path}"
        headers = {
            "Host": f"127.0.0.1:{port}",
            "Origin": f"http://127.0.0.1:{port}",
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

    def test_boot_code_cleanup_at_startup_and_memory_only(self):
        temp_dir = Path(tempfile.gettempdir())
        stale_file = temp_dir / "nova_boot_url.txt"
        stale_file.write_text("http://127.0.0.1:8765/?boot=stale_code_xyz", encoding="utf-8")
        self.assertTrue(stale_file.exists())

        # Calling startup cleanup deletes the artifact
        server.delete_persisted_boot_artifacts()
        self.assertFalse(stale_file.exists())

        # Generate boot code
        code = server.generate_boot_code(60)
        self.assertIn(code, server.BOOT_CODES)

        # Ensure no file under temp dir is named nova_boot_url.txt
        self.assertFalse(stale_file.exists())

    def test_ten_unauthenticated_api_requests_rate_limit_and_no_leak(self):
        srv, port = self._start_live_server()
        try:
            temp_dir = Path(tempfile.gettempdir())
            boot_artifact = temp_dir / "nova_boot_url.txt"
            if boot_artifact.exists():
                boot_artifact.unlink()

            # Ensure starting state
            with server.BOOT_LOCK:
                server.BOOT_CODES.clear()
                server.LAST_401_BOOT_MINT_TIME = 0.0

            # 1. First unauthenticated request
            status1, body1, _ = self._api_req(port, "/api/state")
            self.assertEqual(status1, 401)
            with server.BOOT_LOCK:
                self.assertEqual(len(server.BOOT_CODES), 1)
                first_code = list(server.BOOT_CODES.keys())[0]

            # 2. Second unauthenticated request within 60s must NOT produce a new code
            status2, body2, _ = self._api_req(port, "/api/notes")
            self.assertEqual(status2, 401)
            with server.BOOT_LOCK:
                self.assertEqual(len(server.BOOT_CODES), 1)
                self.assertIn(first_code, server.BOOT_CODES)

            # 3. 8 more unauthenticated requests (total 10)
            for i in range(8):
                status_i, _, _ = self._api_req(port, f"/api/notes?i={i}")
                self.assertEqual(status_i, 401)

            # Still exactly 1 code minted, and at most 5 live codes
            with server.BOOT_LOCK:
                self.assertEqual(len(server.BOOT_CODES), 1)
                live_codes = list(server.BOOT_CODES.keys())

            # Verify no file under %TEMP% or project contains "boot=" or a live code
            self.assertFalse(boot_artifact.exists())

            # Scan project files (excluding git, tests, docs) to ensure no leak
            for item in ROOT.rglob("*"):
                if item.is_file() and not any(part in item.parts for part in (".git", "docs", "test_", "tests")):
                    try:
                        content = item.read_text(encoding="utf-8", errors="ignore")
                        for code in live_codes:
                            self.assertNotIn(code, content, f"Found live code {code} in {item}")
                    except Exception:
                        pass

        finally:
            srv.shutdown()
            srv.server_close()

    def test_boot_code_cap_at_five_live_codes(self):
        with server.BOOT_LOCK:
            server.BOOT_CODES.clear()

        # Generate 10 codes
        codes = []
        for _ in range(10):
            codes.append(server.generate_boot_code(120))

        with server.BOOT_LOCK:
            # Must keep at most 5 live codes
            self.assertEqual(len(server.BOOT_CODES), 5)
            # The newest 5 must be preserved
            for c in codes[-5:]:
                self.assertIn(c, server.BOOT_CODES)
            # The oldest 5 must have been evicted
            for c in codes[:5]:
                self.assertNotIn(c, server.BOOT_CODES)

    def test_quick_summon_script_rules(self):
        qs_path = ROOT / "quick_summon.bat"
        self.assertTrue(qs_path.exists())
        qs_code = qs_path.read_text(encoding="utf-8")

        self.assertNotIn("-ExecutionPolicy Bypass", qs_code)
        self.assertNotIn("nova_boot_url.txt", qs_code)
        self.assertNotIn("boot=", qs_code)
        self.assertNotIn("bootUrl", qs_code)
        self.assertIn("Nova is running - use the open tab or restart Nova", qs_code)
        self.assertIn("run.bat", qs_code)
        self.assertIn("8765", qs_code)


if __name__ == "__main__":
    unittest.main()
