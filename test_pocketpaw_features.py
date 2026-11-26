#!/usr/bin/env python3
"""
Unit tests for PocketPaw-inspired features in Nova AI:
- Usage & Cost Tracker & /api/metrics/usage
- System Doctor & /api/health & /api/diagnostics
- Budget cap enforcement in LLM router
- Discord Gateway integration
"""

import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import diagnostics
import discord_gateway
import server
import usage_tracker


class TestPocketPawFeatures(unittest.TestCase):
    def test_metrics_usage_endpoint(self):
        # Mock request to /api/metrics/usage
        handler = server.Handler.__new__(server.Handler)
        handler.path = "/api/metrics/usage"
        handler.headers = {"Host": "127.0.0.1:8765", "Cookie": f"nova_session={server.SESSION_TOKEN}", "X-Nova-Token": server.API_SESSION_TOKEN}
        handler.server = MagicMock()
        handler.server.server_address = ("127.0.0.1", 8765)
        
        sent_code = None
        sent_body = None
        
        def mock_send(code, body):
            nonlocal sent_code, sent_body
            sent_code = code
            sent_body = body

        handler._send = mock_send
        handler.do_GET()

        self.assertEqual(sent_code, 200)
        self.assertIn("summary", sent_body)
        self.assertIn("budget", sent_body)

    def test_health_and_diagnostics_endpoint(self):
        handler = server.Handler.__new__(server.Handler)
        handler.path = "/api/health"
        handler.headers = {"Host": "127.0.0.1:8765", "Cookie": f"nova_session={server.SESSION_TOKEN}", "X-Nova-Token": server.API_SESSION_TOKEN}
        handler.server = MagicMock()
        handler.server.server_address = ("127.0.0.1", 8765)

        sent_code = None
        sent_body = None

        def mock_send(code, body):
            nonlocal sent_code, sent_body
            sent_code = code
            sent_body = body

        handler._send = mock_send
        handler.do_GET()

        self.assertEqual(sent_code, 200)
        self.assertIn("overall_status", sent_body)
        self.assertIn("checks", sent_body)
        self.assertIn("summary", sent_body)

    def test_budget_cap_enforcement_in_call_llm(self):
        # Configure budget that is already exhausted
        cfg = dict(server.DEFAULT_CONFIG)
        cfg["monthly_budget_usd"] = 0.000001
        
        # Record usage to exceed cap
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            temp_path = tf.name
        try:
            usage_tracker.set_usage_file(temp_path)
            usage_tracker.record_usage("openai", "gpt-4o", 100_000, 50_000)

            with self.assertRaises(server.LLMError) as ctx:
                server.call_llm_with_fallback(cfg, "You are a test helper", [{"role": "user", "content": "hello"}])
            self.assertIn("Monthly budget limit reached", str(ctx.exception))
        finally:
            import os
            try:
                os.remove(temp_path)
            except Exception:
                pass

    def test_discord_daemon_lifecycle(self):
        cfg = {
            "discord_enabled": True,
            "discord_bot_token": "mock_token",
            "discord_channel_ids": ["123456"],
            "discord_allowed_user_ids": ["987654"],
        }
        with patch.object(discord_gateway.DiscordGateway, "start") as mock_start:
            gw = discord_gateway.start_discord_daemon(cfg)
            self.assertIsNotNone(gw)
            mock_start.assert_called_once()
            discord_gateway.stop_discord_gateway()


if __name__ == "__main__":
    unittest.main()
