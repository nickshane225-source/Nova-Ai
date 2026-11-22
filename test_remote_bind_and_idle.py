import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import server


SAMPLE_IPCONFIG = """
Windows IP Configuration

Ethernet adapter vEthernet (WSL (Hyper-V firewall)):
   IPv4 Address. . . . . . . . . . . : 172.25.160.1

Ethernet adapter VirtualBox Host-Only Network:
   IPv4 Address. . . . . . . . . . . : 192.168.56.1

Ethernet adapter DockerNAT:
   IPv4 Address. . . . . . . . . . . : 10.0.75.1

Unknown adapter Tailscale VPN:
   IPv4 Address. . . . . . . . . . . : 100.64.12.34

Wireless LAN adapter Wi-Fi:
   IPv4 Address. . . . . . . . . . . : 192.168.1.42
"""


class TestRemoteBindAndIdle(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.orig_cfg_file = server.CONFIG_FILE
        server.CONFIG_FILE = Path(self.tmpdir.name) / "config.json"
        cfg = dict(server.DEFAULT_CONFIG)
        cfg["remote_port"] = 0
        cfg["remote_bind_ip"] = "127.0.0.1"
        cfg["remote_enabled"] = False
        cfg["remote_idle_timeout_minutes"] = 30
        server.save_config(cfg)
        server.stop_remote()
        with server.FAILS_LOCK:
            server.FAILS.clear()
        with server.PAIRED_DEVICES_LOCK:
            server.PAIRED_DEVICES.clear()

    def tearDown(self):
        server.stop_remote()
        server.CONFIG_FILE = self.orig_cfg_file
        with server.FAILS_LOCK:
            server.FAILS.clear()
        with server.PAIRED_DEVICES_LOCK:
            server.PAIRED_DEVICES.clear()
        self.tmpdir.cleanup()

    def test_rfc1918_and_virtual_adapter_filtering(self):
        self.assertTrue(server.is_rfc1918_ip("10.0.0.5"))
        self.assertTrue(server.is_rfc1918_ip("172.16.0.1"))
        self.assertTrue(server.is_rfc1918_ip("192.168.1.42"))
        for bad in ("0.0.0.0", "8.8.8.8", "172.32.0.1", "169.254.1.1", "100.64.0.1", "127.0.0.1", "::"):
            self.assertFalse(server.is_rfc1918_ip(bad), f"Must reject {bad}")

        ips = server.parse_windows_physical_lan_ips(SAMPLE_IPCONFIG)
        self.assertEqual(ips, ["192.168.1.42"])

    def test_refuse_non_private_bind_ip(self):
        cfg = server.get_config()
        for bad_ip in ("0.0.0.0", "8.8.8.8", "100.64.1.2"):
            cfg["remote_bind_ip"] = bad_ip
            server.save_config(cfg)
            server.start_remote()
            self.assertIsNone(server.REMOTE.get("srv"))
            self.assertIn("Refused non-private", server.REMOTE.get("error", ""))

    def test_unauthenticated_pings_do_not_extend_last_seen_and_auth_does(self):
        cfg = server.get_config()
        cfg["remote_enabled"] = True
        cfg["remote_bind_ip"] = "127.0.0.1"
        cfg["remote_port"] = 0
        cfg["remote_token"] = "valid-remote-tok-12345"
        server.save_config(cfg)
        server.start_remote()
        srv = server.REMOTE["srv"]
        self.assertIsNotNone(srv)
        port = srv.server_address[1]

        old_ts = time.time() - 1200.0  # 20 minutes ago
        server.REMOTE["last_seen"] = old_ts

        # 1. Unauthenticated static GET / must NOT extend last_seen
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as r:
            self.assertEqual(r.status, 200)
        self.assertEqual(server.REMOTE["last_seen"], old_ts)

        # 2. Unauthenticated /api/remote/info (401) must NOT extend last_seen
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/remote/info", timeout=5)
        self.assertEqual(ctx.exception.code, 401)
        self.assertEqual(server.REMOTE["last_seen"], old_ts)

        # 3. Authenticated /api/remote/info MUST update last_seen
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/remote/info",
            headers={"X-Nova-Token": "valid-remote-tok-12345"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            self.assertEqual(r.status, 200)
        self.assertGreater(server.REMOTE["last_seen"], old_ts + 1000.0)

        # 4. Idle disable triggers when last_seen is older than timeout
        server.REMOTE["last_seen"] = time.time() - (31 * 60)
        self.assertTrue(server.check_remote_idle())
        self.assertIsNone(server.REMOTE.get("srv"))

    def test_repeated_enable_disable_no_duplicate_monitor_threads(self):
        for _ in range(4):
            server.set_remote(True)
            mon_threads = [t for t in threading.enumerate() if t.name == "nova-remote-idle-monitor" and t.is_alive()]
            self.assertEqual(len(mon_threads), 1, f"Expected exactly 1 monitor thread, got {len(mon_threads)}")
            server.set_remote(False)
            mon_threads_after = [t for t in threading.enumerate() if t.name == "nova-remote-idle-monitor" and t.is_alive()]
            self.assertEqual(len(mon_threads_after), 0, f"Expected 0 monitor threads after stop, got {len(mon_threads_after)}")


if __name__ == "__main__":
    unittest.main()
