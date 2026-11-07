"""
Test suite for Nova Browser core functionality.
"""
import unittest
import os
import sys
from pathlib import Path

# Ensure nova_browser module can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nova_browser

class TestNovaBrowser(unittest.TestCase):

    def test_find_browser_executable(self):
        exe = nova_browser.get_browser_executable()
        self.assertIsNotNone(exe, "Should locate Chrome or Edge executable on Windows")
        self.assertTrue(os.path.exists(exe), f"Found executable does not exist: {exe}")

    def test_normalize_domain_or_url(self):
        self.assertEqual(nova_browser.extract_domain("https://www.youtube.com/watch?v=123"), "youtube.com")
        self.assertEqual(nova_browser.extract_domain("http://web.whatsapp.com"), "whatsapp.com")
        self.assertEqual(nova_browser.extract_domain("https://web.telegram.org/a/"), "telegram.org")

    def test_tab_matching(self):
        sample_tabs = [
            {"id": "1", "url": "https://www.youtube.com/watch?v=abc", "title": "YouTube Video"},
            {"id": "2", "url": "https://web.whatsapp.com/", "title": "WhatsApp"},
            {"id": "3", "url": "https://www.google.com/search?q=ai", "title": "Google Search"}
        ]
        
        # Exact/domain matches
        tab1 = nova_browser.find_tab_in_list(sample_tabs, "https://youtube.com")
        self.assertIsNotNone(tab1)
        self.assertEqual(tab1["id"], "1")

        tab2 = nova_browser.find_tab_in_list(sample_tabs, "whatsapp")
        self.assertIsNotNone(tab2)
        self.assertEqual(tab2["id"], "2")

        tab_none = nova_browser.find_tab_in_list(sample_tabs, "github.com")
        self.assertIsNone(tab_none)

    def test_profile_path_setup(self):
        profile_path = nova_browser.get_profile_dir()
        self.assertTrue(str(profile_path).endswith("nova_browser_profile"))

    def test_server_browser_skills_routing(self):
        import server
        # Test BROWSER_TABS skill returns a string
        res = server.run_skill({}, "BROWSER_TABS", "")
        self.assertIsInstance(res, str)

        # Test BROWSER_YOUTUBE parameter parsing
        res_yt = server.run_skill({}, "BROWSER_YOUTUBE", "play lofi hip hop")
        self.assertIsInstance(res_yt, str)

        # Test BROWSER_YOUTUBE with pipe and Bengali
        res_yt_pipe = server.run_skill({}, "BROWSER_YOUTUBE", "play | বাংলা গান")
        self.assertIsInstance(res_yt_pipe, str)

        # Test PLAY skill with song
        res_play = server.run_skill({}, "PLAY", "believer")
        self.assertIsInstance(res_play, str)

        # Test OPEN_APP with youtube
        res_app_yt = server.run_skill({}, "OPEN_APP", "youtube")
        self.assertIsInstance(res_app_yt, str)

        # Test BROWSER_WHATSAPP parameter parsing
        res_wa = server.run_skill({}, "BROWSER_WHATSAPP", "")
        self.assertIn("WhatsApp Web", res_wa)

        # Test BROWSER_TELEGRAM parameter parsing
        res_tg = server.run_skill({}, "BROWSER_TELEGRAM", "")
        self.assertIn("Telegram Web", res_tg)

    def test_normalize_target_url(self):
        # Local file
        file_uri = nova_browser.normalize_target_url("web/index.html")
        self.assertTrue(file_uri.startswith("file:///"), f"Expected file URI, got: {file_uri}")
        self.assertTrue("index.html" in file_uri)

        # Standard website
        site_uri = nova_browser.normalize_target_url("prothomalo.com")
        self.assertEqual(site_uri, "https://prothomalo.com")

        # Search query (newspaper / research topic)
        search_uri = nova_browser.normalize_target_url("latest news today")
        self.assertTrue(search_uri.startswith("https://www.google.com/search?q="))

    def test_open_file_and_research_skills(self):
        import server
        # Test OPEN_FILE routes to Nova Browser
        res_file = server.run_skill({}, "OPEN_FILE", "web/index.html")
        self.assertIsInstance(res_file, str)

        # Test VIEW_FILE
        res_view = server.run_skill({}, "VIEW_FILE", "web/index.html")
        self.assertIsInstance(res_view, str)

        # Test BROWSER_RESEARCH
        res_res = server.run_skill({}, "BROWSER_RESEARCH", "")
        self.assertIsInstance(res_res, str)

    def test_missing_browser_binary_handling(self):
        from unittest.mock import patch
        with patch("nova_browser.is_cdp_available", return_value=False):
            with patch("nova_browser.get_browser_executable", side_effect=FileNotFoundError("Mocked binary missing")):
                res = nova_browser.launch_browser("about:blank")
                self.assertIsInstance(res, dict)
                self.assertFalse(res.get("ok"))
                self.assertEqual(res.get("error"), "Chrome or Edge executable not found")

if __name__ == "__main__":
    unittest.main()
