"""
Regression tests for Batch 5c Item 7:
- /api/state is_tainted is keyed by conversation ID (source + jid, source + mode, or pc:{mode})
- When a scheduler conversation is tainted, PC conversation state remains clean (is_tainted: False)
- Querying state with conv_id or source+jid returns the accurate per-conversation taint state.
"""
import http.client
import json
import threading
import time
import unittest

import server


class TestBatch5cStateTaintScoping(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = 8798
        server.SESSION_TOKEN = "mock-session-token-batch5c"
        server.API_SESSION_TOKEN = "mock-api-token-batch5c"
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", cls.port), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        server.CONVERSATION_TAINT.clear()

    def tearDown(self):
        server.CONVERSATION_TAINT.clear()

    def _api_get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {
            "Cookie": f"nova_session={server.SESSION_TOKEN}",
            "X-Nova-Token": server.API_SESSION_TOKEN,
            "Host": f"127.0.0.1:{self.port}",
        }
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8"))
        conn.close()
        return resp.status, data

    def test_scheduler_conversation_tainted_pc_conversation_clean(self):
        """When a scheduler job is tainted, PC state is clean and scheduler query is tainted."""
        sched_conv = "scheduler:cron_morning_news"
        server.CONVERSATION_TAINT[sched_conv] = True
        server.CONVERSATION_TAINT["pc:developer"] = False

        # 1. PC default /api/state is clean
        status_pc, data_pc = self._api_get("/api/state")
        self.assertEqual(status_pc, 200)
        self.assertFalse(data_pc.get("is_tainted"), "PC conversation must be clean when scheduler is tainted")
        self.assertEqual(data_pc.get("conv_id"), "pc:developer")

        # 2. PC explicit mode query is clean
        status_dev, data_dev = self._api_get("/api/state?mode=developer")
        self.assertEqual(status_dev, 200)
        self.assertFalse(data_dev.get("is_tainted"))

        # 3. Scheduler query via conv_id is tainted
        status_sched, data_sched = self._api_get(f"/api/state?conv_id={sched_conv}")
        self.assertEqual(status_sched, 200)
        self.assertTrue(data_sched.get("is_tainted"), "Scheduler state must report is_tainted=True")
        self.assertEqual(data_sched.get("conv_id"), sched_conv)

        # 4. Scheduler query via source + jid is tainted
        status_src, data_src = self._api_get("/api/state?source=scheduler&jid=cron_morning_news")
        self.assertEqual(status_src, 200)
        self.assertTrue(data_src.get("is_tainted"), "Scheduler state via source+jid must report is_tainted=True")
        self.assertEqual(data_src.get("conv_id"), sched_conv)


if __name__ == "__main__":
    unittest.main()
