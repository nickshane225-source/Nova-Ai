import json
import threading
import unittest
import urllib.request
from unittest import mock

import plan_mode
import server


class TestPlanJsonAndGatedRuntime(unittest.TestCase):
    def setUp(self):
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()
        with server.ACTIVE_PLANS_LOCK:
            server.ACTIVE_PLANS.clear()

    def tearDown(self):
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()
        with server.ACTIVE_PLANS_LOCK:
            server.ACTIVE_PLANS.clear()

    def test_plan_remains_json_serializable_before_during_and_after_batch(self):
        plan = {
            "plan_id": "plan-json-1",
            "title": "JSON Serializable Plan",
            "steps": ["[[LIST_FILES: .]]", "[[CMD: echo hi]]"],
            "active_seconds": 12.5,
        }
        # Before execution
        json.dumps(plan)

        seen_during = []
        def runner(step, idx, all_steps, completed, results):
            # Must be strictly JSON-serializable during execution too (no lambdas!)
            serialized = json.dumps(plan)
            seen_during.append(serialized)
            self.assertNotIn("get_active_seconds", plan)
            return "ok"

        res = plan_mode.execute_plan_batch(plan, cfg={}, runner=runner)
        self.assertTrue(res["ok"])
        self.assertEqual(len(seen_during), 2)
        # After execution
        json.dumps(plan)
        json.dumps(res)

    def test_approved_gated_step_runtime_counted_in_active_seconds(self):
        srv = server.SilentThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            action_id = "gated-runtime-act-1"
            plan_state = {
                "plan_id": "plan-gated-rt-1",
                "title": "Gated Runtime Plan",
                "all_steps": ["[[CMD: echo slow]]", "[[LIST_FILES: .]]"],
                "completed": [],
                "paused_step_idx": 0,
                "paused_step": "[[CMD: echo slow]]",
                "remaining_steps": ["[[CMD: echo slow]]", "[[LIST_FILES: .]]"],
                "results": [],
                "source": "pc",
                "mode": "developer",
                "is_tainted": False,
                "conv_id": "pc:developer",
                "active_seconds": 50.0,
                "started_at": 1000.0,
            }
            with server.PENDING_LOCK:
                server.PENDING_ACTIONS[action_id] = {
                    "id": action_id,
                    "name": "CMD",
                    "arg": "echo slow",
                    "prompt": "Run echo slow",
                    "source": "pc",
                    "mode": "developer",
                    "conv_id": "pc:developer",
                    "is_tainted": False,
                    "guardian": "SAFE",
                    "created_at": 1995.0,
                    "expires_at": 2500.0,
                    "plan_state": plan_state,
                }

            captured_active = []
            def fake_resume(p_state, last_result=None, cfg=None, **kw):
                captured_active.append(p_state.get("active_seconds"))
                return {"ok": True, "completed": 2, "message": "Done"}

            # Simulate gated step taking 25.0 seconds
            clock = [2000.0]
            def fake_time():
                return clock[0]

            def fake_run_skill(*args, **kwargs):
                clock[0] += 25.0
                return "slow output"

            headers = {
                "Content-Type": "application/json",
                "Cookie": f"nova_session={server.SESSION_TOKEN}",
                "X-Nova-Token": server.API_SESSION_TOKEN,
                "Origin": f"http://127.0.0.1:{port}",
            }
            with mock.patch("server.time.time", side_effect=fake_time), \
                 mock.patch("server.run_skill", side_effect=fake_run_skill), \
                 mock.patch("server.resume_plan_execution", side_effect=fake_resume):
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/confirm",
                    data=json.dumps({"id": action_id, "approve": True}).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    self.assertEqual(resp.status, 200)

            self.assertEqual(len(captured_active), 1)
            self.assertAlmostEqual(captured_active[0], 75.0, places=2)
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
