"""
Unit tests for Smart Home / Local Network IoT skill in server.py
"""
import unittest
import server

class TestSmartHome(unittest.TestCase):
    def test_smart_home_empty_arg(self):
        res = server.run_skill({}, "SMART_HOME", "")
        self.assertIn("Refused", res)

    def test_smart_home_invalid_url_graceful_fail(self):
        # Local non-existing endpoint should fail gracefully without crashing
        res = server.run_skill({}, "SMART_HOME", "http://127.0.0.1:59999/api/test | POST | {}")
        self.assertIn("Smart Home request failed", res)

if __name__ == "__main__":
    unittest.main()
