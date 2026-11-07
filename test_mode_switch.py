import unittest
from unittest.mock import patch
from server import (
    Handler,
    chat,
    HISTORIES,
    build_system,
    get_config,
    get_characters,
    LOCK
)


class Test2In1ModeSwitch(unittest.TestCase):
    def setUp(self):
        with LOCK:
            HISTORIES["developer"].clear()
            HISTORIES["cyber"].clear()

    def tearDown(self):
        with LOCK:
            HISTORIES["developer"].clear()
            HISTORIES["cyber"].clear()

    def test_mode_histories_are_isolated(self):
        """Verify chat history in Developer and Cyber modes never mix via server.chat."""
        with patch("server.call_llm", side_effect=["Hello from Dev", "Buffer overflow analysis"]):
            chat("Hello Developer", mode="developer")
            chat("Audit this buffer overflow", mode="cyber")

        self.assertEqual(len(HISTORIES["developer"]), 2)
        self.assertEqual(len(HISTORIES["cyber"]), 2)
        self.assertEqual(HISTORIES["developer"][0]["content"], "Hello Developer")
        self.assertEqual(HISTORIES["developer"][1]["content"], "Hello from Dev")
        self.assertEqual(HISTORIES["cyber"][0]["content"], "Audit this buffer overflow")
        self.assertEqual(HISTORIES["cyber"][1]["content"], "Buffer overflow analysis")

    def test_developer_system_prompt(self):
        """Verify developer mode system prompt keeps existing persona."""
        cfg = get_config()
        chars = get_characters()
        char = chars[0]
        prompt = build_system(cfg, char, mode="developer")
        self.assertIn("You are an advanced voice-first AI character", prompt)
        self.assertNotIn("You are Nova Cyber", prompt)

    def test_cyber_system_prompt(self):
        """Verify cyber mode system prompt has required cybersecurity persona."""
        cfg = get_config()
        chars = get_characters()
        char = chars[0]
        prompt = build_system(cfg, char, mode="cyber")
        self.assertIn("You are Nova Cyber, a cybersecurity intelligence assistant.", prompt)
        self.assertIn("threat intelligence, vulnerability analysis, secure coding", prompt)
        self.assertIn("Only support authorized, legal, and educational use.", prompt)

    def test_reset_isolation(self):
        """Verify resetting one mode via /api/reset does not wipe the other."""
        with patch("server.call_llm", side_effect=["Dev reply", "Cyber reply"]):
            chat("Dev msg", mode="developer")
            chat("Cyber msg", mode="cyber")

        class MockResetHandler(Handler):
            def __init__(self, mode):
                self.path = "/api/reset"
                self.headers = {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"}
                self.command = "POST"
                self.requestline = "POST /api/reset HTTP/1.1"
                self._test_body = {"mode": mode}
                self.status = None
                self.data = None
            def _body(self):
                return self._test_body
            def _send(self, status, data, ctype="application/json"):
                self.status = status
                self.data = data

        # Clear only developer via real route handler
        h = MockResetHandler("developer")
        h.do_POST()
        self.assertEqual(h.status, 200)

        self.assertEqual(len(HISTORIES["developer"]), 0)
        self.assertEqual(len(HISTORIES["cyber"]), 2)
        self.assertEqual(HISTORIES["cyber"][0]["content"], "Cyber msg")

    def test_toolsets_partitioned_between_modes(self):
        """Verify leisure media tools are present in Developer Mode and excluded from Cyber Mode."""
        cfg = get_config()
        chars = get_characters()
        char = chars[0]

        dev_prompt = build_system(cfg, char, mode="developer")
        cyber_prompt = build_system(cfg, char, mode="cyber")

        # Developer prompt has entertainment/browsing tags
        self.assertIn("[[PLAY:", dev_prompt)
        self.assertIn("[[BROWSER_YOUTUBE:", dev_prompt)

        # Cyber prompt has cybersecurity toolset and excludes leisure media
        self.assertIn("CYBERSECURITY INTELLIGENCE & CODING AGENT", cyber_prompt)
        self.assertNotIn("[[PLAY:", cyber_prompt)
        self.assertNotIn("[[BROWSER_YOUTUBE:", cyber_prompt)
        self.assertNotIn("[[BROWSER_WHATSAPP:", cyber_prompt)

    def test_architecture_trigger_disambiguation(self):
        """Verify 'architecture' routes specifically to architecture-design skill."""
        import skills_engine
        selected = skills_engine.select_skills("developer", "Can you help me design the system architecture?", limit=2)
        self.assertTrue(len(selected) > 0)
        self.assertEqual(selected[0].name, "architecture-design")


if __name__ == "__main__":
    unittest.main()
