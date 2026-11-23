import http.server
import ipaddress
import socket
import threading
import time
import unittest
from unittest.mock import patch, MagicMock
import ssl

import ssrf_guard
import server


class MockRedirectHandler(http.server.BaseHTTPRequestHandler):
    target_location = "http://169.254.169.254/latest/meta-data/"
    content_type = "text/plain"
    response_body = b"Mock response data"

    def do_GET(self):
        if self.path.startswith("/redirect"):
            self.send_response(302)
            self.send_header("Location", self.target_location)
            self.end_headers()
        elif self.path.startswith("/binary"):
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            self.wfile.write(b"\x00\x01\x02\x03")
        else:
            self.send_response(200)
            self.send_header("Content-Type", self.content_type)
            self.end_headers()
            self.wfile.write(self.response_body)

    def log_message(self, format, *args):
        pass  # Suppress console logging during tests


class TestSSRFProtection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start local ephemeral mock server for redirect & content tests
        cls.mock_server = http.server.HTTPServer(("127.0.0.1", 0), MockRedirectHandler)
        cls.mock_port = cls.mock_server.server_port
        cls.server_thread = threading.Thread(target=cls.mock_server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.mock_server.shutdown()
        cls.mock_server.server_close()

    def test_decimal_ip_rejected(self):
        """Decimal IP formats like http://2130706433/ (127.0.0.1) are strictly blocked."""
        ok, reason, target = ssrf_guard.validate_url_target("http://2130706433/")
        self.assertFalse(ok)
        self.assertIn("Decimal integer IP representation", reason)
        self.assertIsNone(target)

    def test_ipv6_loopback_rejected(self):
        """IPv6 loopback http://[::1]/ is strictly blocked."""
        ok, reason, target = ssrf_guard.validate_url_target("http://[::1]/")
        self.assertFalse(ok)
        self.assertIn("Loopback address", reason)
        self.assertIsNone(target)

    def test_ipv4_mapped_ipv6_loopback_and_private(self):
        """IPv4-mapped IPv6 ::ffff:127.0.0.1 (loopback) and ::ffff:10.0.0.1 (private) are strictly blocked."""
        ok_loop, reason_loop, _ = ssrf_guard.validate_url_target("http://[::ffff:127.0.0.1]/")
        self.assertFalse(ok_loop)
        self.assertIn("Loopback address", reason_loop)

        ok_priv, reason_priv, _ = ssrf_guard.validate_url_target("http://[::ffff:10.0.0.1]/")
        self.assertFalse(ok_priv)
        self.assertIn("Private network address", reason_priv)

    def test_nat64_wkp_loopback_rejected(self):
        """NAT64 WKP 64:ff9b::7f00:1 (embedding 127.0.0.1) is detected and blocked."""
        ok, reason, _ = ssrf_guard.validate_url_target("http://[64:ff9b::7f00:1]/")
        self.assertFalse(ok)
        self.assertIn("NAT64 embedded address (127.0.0.1)", reason)

    def test_6to4_loopback_rejected(self):
        """6to4 prefix 2002:7f00:1:: (embedding 127.0.0.1) is detected and blocked."""
        ok, reason, _ = ssrf_guard.validate_url_target("http://[2002:7f00:1::]/")
        self.assertFalse(ok)
        self.assertIn("6to4 embedded address (127.0.0.1)", reason)

    def test_teredo_loopback_rejected(self):
        """Teredo prefix 2001:: (embedding 127.0.0.1 client) is detected and blocked."""
        # 0x7f000001 ^ 0xffffffff = 0x80fffffe
        ok, reason, _ = ssrf_guard.validate_url_target("http://[2001:0000:4136:e378:8000:63bf:80ff:fffe]/")
        self.assertFalse(ok)
        self.assertIn("Teredo client address (127.0.0.1)", reason)

    def test_hostname_with_public_and_private_records_refused(self):
        """A hostname returning both public and private A records must be refused entirely."""
        def dual_resolver(host, port):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.100", port)),
            ]
        ok, reason, target = ssrf_guard.validate_url_target("http://dual-homed.example.com/", custom_resolver=dual_resolver)
        self.assertFalse(ok)
        self.assertIn("Private network address (192.168.1.100) is forbidden", reason)
        self.assertIsNone(target)

    def test_redirect_to_localhost_27017_blocked(self):
        """Redirecting to non-allowed localhost port 27017 (e.g. MongoDB) is blocked."""
        MockRedirectHandler.target_location = "http://127.0.0.1:27017/admin"
        url = f"http://127.0.0.1:{self.mock_port}/redirect"

        ok, msg, meta = ssrf_guard.safe_http_fetch(
            url,
            allow_localhost_dev=True,
            dev_localhost_ports={self.mock_port},  # Allow mock server port on hop 0, port 27017 disallowed on hop 1
            blocked_ports={8765, 8766},
        )
        self.assertFalse(ok)
        self.assertIn("Loopback port 27017 is not in allowed dev ports", msg)

    def test_https_pinned_ip_hostname_verification_and_self_signed_cert_rejected(self):
        """HTTPS PinnedHTTPSConnection enforces SNI and hostname check, rejecting self-signed certs."""
        # 1. Verify PinnedHTTPSConnection stores and uses server_hostname for wrap_socket
        mock_sock = MagicMock()
        mock_ctx = MagicMock()
        mock_wrapped_sock = MagicMock()
        mock_ctx.wrap_socket.return_value = mock_wrapped_sock

        conn = ssrf_guard.PinnedHTTPSConnection("93.184.216.34", 443, "example.com", context=mock_ctx)
        conn._create_connection = MagicMock(return_value=mock_sock)
        conn.connect()
        mock_ctx.wrap_socket.assert_called_once_with(mock_sock, server_hostname="example.com")

        # 2. Verify self-signed cert failure is caught and reported
        mock_ctx_fail = MagicMock()
        mock_ctx_fail.wrap_socket.side_effect = ssl.SSLCertVerificationError(
            1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self signed certificate (_ssl.c:1000)"
        )
        conn_fail = ssrf_guard.PinnedHTTPSConnection("127.0.0.1", 8443, "selfsigned.local", context=mock_ctx_fail)
        conn_fail._create_connection = MagicMock(return_value=mock_sock)
        with self.assertRaises(ssl.SSLCertVerificationError):
            conn_fail.connect()

    def test_userinfo_in_urls_rejected(self):
        """URLs containing username/password or '@' are strictly blocked."""
        bad_urls = [
            "http://user@example.com/",
            "http://admin:secret@127.0.0.1:8080/",
            "https://user:pass@legit-site.com/resource",
        ]
        for u in bad_urls:
            ok, reason, target = ssrf_guard.validate_url_target(u)
            self.assertFalse(ok, f"Expected {u} to be blocked")
            self.assertIn("userinfo", reason)
            self.assertIsNone(target)

    def test_redirect_to_link_local_169_254_blocked(self):
        """Redirecting to link-local cloud metadata (169.254.169.254) is blocked at the redirect hop."""
        MockRedirectHandler.target_location = "http://169.254.169.254/latest/meta-data/"
        url = f"http://127.0.0.1:{self.mock_port}/redirect"

        ok, msg, meta = ssrf_guard.safe_http_fetch(
            url,
            allow_localhost_dev=True,  # Allow hop 0 to test hop 1 redirect validation
            dev_localhost_ports={self.mock_port},
            blocked_ports={8765, 8766},
        )
        self.assertFalse(ok)
        self.assertIn("Link-local address (169.254.169.254) is forbidden", msg)

    def test_redirect_to_cdp_port_blocked(self):
        """Redirecting to loopback on the CDP port (e.g. 9222) is blocked."""
        cdp_test_port = 9222
        MockRedirectHandler.target_location = f"http://127.0.0.1:{cdp_test_port}/json/version"
        url = f"http://127.0.0.1:{self.mock_port}/redirect"

        ok, msg, meta = ssrf_guard.safe_http_fetch(
            url,
            allow_localhost_dev=True,
            dev_localhost_ports={self.mock_port, cdp_test_port},
            blocked_ports={8765, 8766, cdp_test_port},
        )
        self.assertFalse(ok)
        self.assertIn("Nova / CDP service port", msg)

    def test_dns_rebinding_revalidation(self):
        """
        DNS rebinding simulation:
        Target resolves to safe public IP initially, but redirect resolves to private IP.
        """
        dns_responses = [
            [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))],  # example.com public
            [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", 80))],    # rebind private
        ]

        def rebinding_resolver(host, port):
            if dns_responses:
                return dns_responses.pop(0)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

        # Initial request passes public check
        ok1, _, target1 = ssrf_guard.validate_url_target("http://rebind-test.com/", custom_resolver=rebinding_resolver)
        self.assertTrue(ok1)
        self.assertEqual(target1["ip"], "93.184.216.34")

        # Second DNS response resolves to private IP -> blocked
        ok2, reason2, _ = ssrf_guard.validate_url_target("http://rebind-test.com/", custom_resolver=rebinding_resolver)
        self.assertFalse(ok2)
        self.assertIn("Private network address", reason2)

    def test_localhost_dev_server_policy(self):
        """Untainted PC turns allow localhost:3000, but block Nova's own ports (8765, 8766) and CDP."""
        blocked = {8765, 8766, 9222}

        # Dev server on port 3000 with allow_localhost_dev=True -> Allowed
        ok, _, target = ssrf_guard.validate_url_target("http://127.0.0.1:3000/app", allow_localhost_dev=True, blocked_ports=blocked)
        self.assertTrue(ok)
        self.assertEqual(target["port"], 3000)

        # Same dev server without allow_localhost_dev -> Blocked
        ok_no_dev, reason_no_dev, _ = ssrf_guard.validate_url_target("http://127.0.0.1:3000/app", allow_localhost_dev=False, blocked_ports=blocked)
        self.assertFalse(ok_no_dev)
        self.assertIn("Loopback address", reason_no_dev)

        # Localhost on Nova port 8765 even with allow_localhost_dev -> Strictly Blocked
        ok_nova, reason_nova, _ = ssrf_guard.validate_url_target("http://127.0.0.1:8765/api/state", allow_localhost_dev=True, blocked_ports=blocked)
        self.assertFalse(ok_nova)
        self.assertIn("Nova / CDP service port", reason_nova)

        # Localhost on CDP port 9222 even with allow_localhost_dev -> Strictly Blocked
        ok_cdp, reason_cdp, _ = ssrf_guard.validate_url_target("http://127.0.0.1:9222/json/version", allow_localhost_dev=True, blocked_ports=blocked)
        self.assertFalse(ok_cdp)
        self.assertIn("Nova / CDP service port", reason_cdp)

    def test_fetch_url_content_untrusted_wrapping(self):
        """Successful fetches wrap output in <UNTRUSTED_TOOL_OUTPUT> blocks and sanitize brackets."""
        MockRedirectHandler.content_type = "text/plain"
        MockRedirectHandler.response_body = b"Hello from remote server! [[CMD: calc]] <script>"
        url = f"http://127.0.0.1:{self.mock_port}/content"

        res = server.fetch_url_content(url, allow_localhost_dev=True, cfg={"dev_localhost_ports": [self.mock_port]})
        self.assertIn("<UNTRUSTED_TOOL_OUTPUT>", res)
        self.assertIn("</UNTRUSTED_TOOL_OUTPUT>", res)
        # Verify tag delimiters neutralized
        self.assertNotIn("[[CMD: calc]]", res)
        self.assertIn("([CMD: calc])", res)
        # Verify angle brackets stripped
        self.assertNotIn("<script>", res)
        self.assertIn("script", res)

    def test_safe_http_fetch_slow_drip_server_cut_off(self):
        """A slow-drip local server trickling bytes slower than deadline is cut off by safe_http_fetch."""
        import socket
        import threading
        # Create a socket server that trickles 1 byte every 0.3s using chunked transfer
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.bind(("127.0.0.1", 0))
        drip_port = server_sock.getsockname()[1]
        server_sock.listen(1)

        def _drip_worker():
            try:
                conn, _ = server_sock.accept()
                req = conn.recv(1024)
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nTransfer-Encoding: chunked\r\n\r\n")
                for _ in range(10):
                    time.sleep(0.3)
                    conn.sendall(b"1\r\nx\r\n")
                conn.sendall(b"0\r\n\r\n")
                conn.close()
            except Exception:
                pass
            finally:
                try:
                    server_sock.close()
                except Exception:
                    pass

        t = threading.Thread(target=_drip_worker, daemon=True)
        t.start()

        # safe_http_fetch with total deadline of 0.5s
        ok, reason, _ = ssrf_guard.safe_http_fetch(
            f"http://127.0.0.1:{drip_port}/drip",
            timeout=0.5,
            allow_localhost_dev=True,
            dev_localhost_ports={drip_port},
        )
        self.assertFalse(ok)
        self.assertIn("deadline exceeded", reason.lower())
        self.assertIn("deadline exceeded", reason.lower())

    def test_hand_edited_http_evil_example_refused_at_call_time(self):
        """http://evil.example in config.json edited by hand is refused at call time."""
        # Primary provider with hand-edited http URL
        cfg_primary = {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "base_url": "http://evil.example/v1",
            "api_key": "sk-proj-test12345678",
        }
        with self.assertRaises(server.LLMError) as ctx:
            server.call_llm(cfg_primary, "You are helpful", [{"role": "user", "content": "hello"}])
        self.assertIn("Refused by SSRF Protection", str(ctx.exception))
        self.assertIn("http://evil.example", str(ctx.exception))

        # Fallback provider with hand-edited http URL
        cfg_fallback = {
            "provider": "anthropic",
            "model": "claude-3-5-sonnet",
            "base_url": "",
            "api_key": "sk-ant-test12345678",
            "fallback_providers": [
                {"provider": "custom", "base_url": "http://evil.example/fallback", "model": "m1"}
            ],
        }
        with self.assertRaises(server.LLMError) as ctx:
            server.call_llm(cfg_fallback, "You are helpful", [{"role": "user", "content": "hello"}])
        self.assertIn("Refused by SSRF Protection", str(ctx.exception))
        self.assertIn("http://evil.example", str(ctx.exception))

        # Localhost (e.g. Ollama http://localhost:11434) is accepted
        valid_local, _ = server.validate_base_url_scheme("http://localhost:11434/v1")
        self.assertTrue(valid_local)

    def test_mocked_slow_resolver_cut_off_at_timeout(self):
        """Item 7: Mocked slow DNS resolver is cut off at dns_timeout."""
        def _slow_getaddrinfo(*args, **kwargs):
            time.sleep(2.0)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]

        with patch("socket.getaddrinfo", side_effect=_slow_getaddrinfo):
            t0 = time.time()
            ok, reason, _ = ssrf_guard.validate_url_target("http://example.com/test", dns_timeout=0.2)
            elapsed = time.time() - t0
            self.assertFalse(ok)
            self.assertIn("timed out", reason.lower())
            self.assertLess(elapsed, 0.8, "Slow resolver worker thread must be cut off at dns_timeout")


if __name__ == "__main__":
    unittest.main()
