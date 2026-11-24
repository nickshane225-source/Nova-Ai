import unittest
from unittest.mock import MagicMock
import pathlib
import time
import tempfile
import threading
from pathlib import Path

import telegram_gateway
import discord_gateway
import server
import memory_engine


class TestHigh05AndHigh09(unittest.TestCase):
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
        self.orig_db_path = memory_engine.DEFAULT_DB
        self.orig_default_port = server.Handler.DEFAULT_PORT

        server.ROOT = self.tmp_path
        server.DATA = self.fake_data
        server.WORKSPACE = self.fake_ws
        server.CONFIG_FILE = self.fake_data / "config.json"
        server.MEMORY_FILE = self.fake_data / "memory.json"
        memory_engine.DEFAULT_DB = self.fake_data / "nova_brain.db"

        cfg = dict(server.DEFAULT_CONFIG)
        cfg["allow_outside_workspace"] = False
        cfg["discord_enabled"] = False
        cfg["telegram_bot_token"] = ""
        server.save_config(cfg)
        server.PENDING_ACTIONS.clear()

    def tearDown(self):
        server.PENDING_ACTIONS.clear()
        server.ROOT = self.orig_root
        server.DATA = self.orig_data
        server.WORKSPACE = self.orig_ws
        server.CONFIG_FILE = self.orig_config_file
        server.MEMORY_FILE = self.orig_memory_file
        memory_engine.DEFAULT_DB = self.orig_db_path
        server.Handler.DEFAULT_PORT = self.orig_default_port
        self.tmp_dir.cleanup()

    def _start_live_server(self):
        srv = server.SilentThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        port = srv.server_address[1]
        server.Handler.DEFAULT_PORT = port
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        return srv, port

    def test_high05_no_duplicate_warning_in_gateways(self):
        tg = telegram_gateway.TelegramGateway(cfg={"telegram_bot_token": "fake", "telegram_allowed_user_ids": ["123"]})
        tg.send_message = MagicMock()
        pending = {
            "id": "pend123",
            "prompt": "Run this command",
            "command": "calc.exe \u200B",  # Zero-width space
        }
        tg.send_approval_announcement(12345, pending)
        tg.send_message.assert_called_once()
        msg = tg.send_message.call_args[0][1]
        self.assertIn("SECURITY WARNING", msg)
        self.assertNotIn("Warning: Command contains hidden or invisible characters.", msg)

        dg = discord_gateway.DiscordGateway(bot_token="fake", channel_ids=["chan1"])
        dg.send_message = MagicMock()
        dg.send_approval_announcement("chan1", pending)
        dg.send_message.assert_called_once()
        d_msg = dg.send_message.call_args[0][1]
        self.assertIn("SECURITY WARNING", d_msg)
        self.assertNotIn("Warning: Command contains hidden or invisible characters.", d_msg)

    def test_high05_powershell_write_cmdlets_and_multiline_run_code(self):
        paths = server.detect_written_files_from_command("Set-Content -Path test_set.py -Value 'test'")
        self.assertIn("test_set.py", paths)

        paths = server.detect_written_files_from_command("Add-Content -Path test_add.txt -Value 'more'")
        self.assertIn("test_add.txt", paths)

        paths = server.detect_written_files_from_command("'data' | Out-File -FilePath test_out.py")
        self.assertIn("test_out.py", paths)

        paths = server.detect_written_files_from_command("Copy-Item source.py -Destination copy_dest.py")
        self.assertIn("copy_dest.py", paths)

        paths = server.detect_written_files_from_command("Move-Item source.py -Destination move_dest.py")
        self.assertIn("move_dest.py", paths)

        paths = server.detect_written_files_from_command("New-Item -ItemType File -Path new_item.py")
        self.assertIn("new_item.py", paths)

        paths = server.detect_written_files_from_command("Get-Process | Tee-Object -FilePath tee_file.txt")
        self.assertIn("tee_file.txt", paths)

        multiline_code = (
            "import os\n"
            "print('Starting execution')\n"
            "with open('multiline_output.py', 'w') as f:\n"
            "    f.write('payload')\n"
        )
        paths = server.detect_written_files_from_command(multiline_code)
        self.assertIn("multiline_output.py", paths)

    def test_high09_playwright_confirm_modal_approve_deny_and_double_click(self):
        """
        HIGH-09 Playwright verification:
        Tests that confirmation modal enforces exactly ONE /api/confirm request on
        single Approve, single Deny, and rapid double click.
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
                    self.skipTest("No browser available for Playwright")

                try:
                    page = browser.new_page()
                    confirm_requests = []

                    def _on_request(req):
                        if "/api/confirm" in req.url and req.method == "POST":
                            confirm_requests.append(req.post_data_json)

                    page.on("request", _on_request)
                    page.goto(boot_url, wait_until="domcontentloaded")
                    page.wait_for_selector("#confirmModal", state="attached", timeout=10000)

                    # 1. Test single Approve
                    action_id_app = "test_single_approve"
                    with server.PENDING_LOCK:
                        server.PENDING_ACTIONS[action_id_app] = {
                            "id": action_id_app, "name": "CMD", "arg": "echo app",
                            "prompt": "Approve test", "preview": "echo app",
                            "source": "pc", "is_tainted": False,
                            "expires_at": time.time() + 120, "created_at": time.time(),
                        }
                    page.evaluate(f"showConfirmModal({{id: '{action_id_app}', action: 'CMD', prompt: 'Approve test', preview: 'echo app'}});")
                    page.wait_for_selector("#confirmModal:not(.hidden)", timeout=5000)
                    page.click("#confirmAllowBtn")
                    page.wait_for_function("() => document.querySelector('#confirmModal').classList.contains('hidden')", timeout=5000)
                    self.assertEqual(len(confirm_requests), 1)
                    self.assertTrue(confirm_requests[0].get("approve"))
                    self.assertEqual(confirm_requests[0].get("id"), action_id_app)

                    # 2. Test single Deny
                    confirm_requests.clear()
                    action_id_deny = "test_single_deny"
                    with server.PENDING_LOCK:
                        server.PENDING_ACTIONS[action_id_deny] = {
                            "id": action_id_deny, "name": "CMD", "arg": "echo deny",
                            "prompt": "Deny test", "preview": "echo deny",
                            "source": "pc", "is_tainted": False,
                            "expires_at": time.time() + 120, "created_at": time.time(),
                        }
                    page.evaluate(f"showConfirmModal({{id: '{action_id_deny}', action: 'CMD', prompt: 'Deny test', preview: 'echo deny'}});")
                    page.wait_for_selector("#confirmModal:not(.hidden)", timeout=5000)
                    page.click("#confirmDenyBtn")
                    page.wait_for_function("() => document.querySelector('#confirmModal').classList.contains('hidden')", timeout=5000)
                    self.assertEqual(len(confirm_requests), 1)
                    self.assertFalse(confirm_requests[0].get("approve"))
                    self.assertEqual(confirm_requests[0].get("id"), action_id_deny)

                    # 3. Test rapid double click on Approve
                    confirm_requests.clear()
                    action_id_double = "test_double_click"
                    with server.PENDING_LOCK:
                        server.PENDING_ACTIONS[action_id_double] = {
                            "id": action_id_double, "name": "CMD", "arg": "echo double",
                            "prompt": "Test double click", "preview": "echo double",
                            "source": "pc", "is_tainted": False,
                            "expires_at": time.time() + 120, "created_at": time.time(),
                        }
                    page.evaluate(f"showConfirmModal({{id: '{action_id_double}', action: 'CMD', prompt: 'Double click test', preview: 'echo double'}});")
                    page.wait_for_selector("#confirmModal:not(.hidden)", timeout=5000)
                    page.evaluate("""() => {
                        const btn = document.querySelector('#confirmAllowBtn');
                        btn.click();
                        btn.click();
                    }""")
                    page.wait_for_function("() => document.querySelector('#confirmModal').classList.contains('hidden')", timeout=5000)
                    self.assertEqual(len(confirm_requests), 1, "Rapid double-click must produce exactly ONE /api/confirm request")
                    self.assertTrue(confirm_requests[0].get("approve"))
                finally:
                    browser.close()
        finally:
            srv.shutdown()
            srv.server_close()

    def test_high09_playwright_second_brain_tainted_badge(self):
        """
        HIGH-09 Playwright verification:
        Saves a tainted note into Second Brain, opens the panel, and verifies that
        the [untrusted source] badge is rendered visibly in the DOM.
        """
        memory_engine.init_db(memory_engine.DEFAULT_DB)
        memory_engine.save_note(
            title="Untrusted Web Research",
            content="Extracted suspicious prompt payload",
            category="Research",
            tainted=1,
            db_path=memory_engine.DEFAULT_DB
        )

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
                    self.skipTest("No browser available for Playwright")

                try:
                    page = browser.new_page()
                    page.goto(boot_url, wait_until="domcontentloaded")
                    page.wait_for_selector("#panel", state="attached", timeout=10000)

                    # Trigger Second Brain panel
                    page.evaluate("openPanel('brain');")
                    badge = page.wait_for_selector("text=[untrusted source]", timeout=5000)
                    self.assertIsNotNone(badge)
                    self.assertTrue(badge.is_visible(), "Tainted badge [untrusted source] must be visibly rendered in Second Brain panel")
                finally:
                    browser.close()
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
