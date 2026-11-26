"""
test_remote_security.py - Verify Remote :8766 security enhancements:
1. Bind only to private-LAN interface (or configured/loopback), never 0.0.0.0
2. In-UI warning that connection is unencrypted HTTP on LAN
3. Idle auto-disable (default 30 mins, configurable)
4. SECURITY_NOTES.md residual risk documentation
"""

import unittest
import time
from unittest.mock import patch, MagicMock
from pathlib import Path

import server


class TestRemoteSecurity(unittest.TestCase):

    def setUp(self):
        self.orig_cfg = server.get_config()
        server.stop_remote()

    def tearDown(self):
        server.stop_remote()
        server.save_config(self.orig_cfg)

    def test_01_remote_binds_to_private_interface_not_all(self):
        """Remote server must bind to private LAN interface (or loopback), never 0.0.0.0."""
        with patch("server.SilentThreadingHTTPServer") as mock_srv_cls, \
             patch("server.lan_ips", return_value=["192.168.1.150"]):
            mock_inst = MagicMock()
            mock_srv_cls.return_value = mock_inst

            server.save_config({"remote_enabled": True, "remote_port": 8766})
            server.start_remote()

            self.assertTrue(mock_srv_cls.called)
            bind_addr, port = mock_srv_cls.call_args[0][0]
            self.assertNotEqual(bind_addr, "0.0.0.0", "Remote must not bind to 0.0.0.0")
            self.assertEqual(bind_addr, "192.168.1.150")
            self.assertEqual(port, 8766)

    def test_02_remote_idle_auto_disable(self):
        """Remote must automatically disable after configured idle minutes."""
        mock_srv = MagicMock()
        server.REMOTE["srv"] = mock_srv
        server.REMOTE["started_at"] = time.time() - 2000.0
        server.REMOTE["last_seen"] = time.time() - 1900.0  # ~31 minutes ago

        server.save_config({"remote_enabled": True, "remote_idle_timeout_minutes": 30})

        with patch("server.set_remote") as mock_set_remote:
            disabled = server.check_remote_idle()
            self.assertTrue(disabled)
            mock_set_remote.assert_called_once_with(False)

    def test_03_remote_active_prevents_idle_timeout(self):
        """Recent activity resets the timer and prevents idle shutdown."""
        mock_srv = MagicMock()
        server.REMOTE["srv"] = mock_srv
        server.REMOTE["started_at"] = time.time() - 2000.0
        server.REMOTE["last_seen"] = time.time() - 60.0  # 1 minute ago

        server.save_config({"remote_enabled": True, "remote_idle_timeout_minutes": 30})

        with patch("server.set_remote") as mock_set_remote:
            disabled = server.check_remote_idle()
            self.assertFalse(disabled)
            mock_set_remote.assert_not_called()

    def test_04_remote_state_reports_unencrypted_and_timeout(self):
        """remote_state() reports is_unencrypted and idle_timeout_minutes for UI consumption."""
        server.save_config({
            "remote_enabled": True,
            "remote_idle_timeout_minutes": 45,
            "remote_cert": "",
            "remote_key": "",
        })
        st = server.remote_state(reveal=False)
        self.assertTrue(st["is_unencrypted"])
        self.assertEqual(st["idle_timeout_minutes"], 45.0)

    def test_05_security_notes_updated(self):
        """SECURITY_NOTES.md includes Remote plain HTTP on LAN and Nova Browser redirects residual risks."""
        sec_notes = Path("docs/SECURITY_NOTES.md").read_text(encoding="utf-8")
        self.assertIn("Remote Over Plain HTTP on LAN", sec_notes)
        self.assertIn("Nova Browser follows redirects to local services; keep personal logins out of its profile", sec_notes)


if __name__ == "__main__":
    unittest.main()
