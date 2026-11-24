#!/usr/bin/env python3
"""
Unit tests for Nova AI Usage & Budget Tracker (usage_tracker.py)
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import usage_tracker


class TestUsageTracker(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.usage_file = Path(self.test_dir) / "test_usage.jsonl"
        usage_tracker.set_usage_file(self.usage_file)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_cost_calculation(self):
        # Gemini 2.5 flash: $0.15/1M in, $0.60/1M out
        cost = usage_tracker.calculate_cost("gemini-2.5-flash", 1_000_000, 1_000_000)
        self.assertAlmostEqual(cost, 0.75, places=4)

        # Ollama is free ($0.00)
        ollama_cost = usage_tracker.calculate_cost("ollama/llama3", 500_000, 500_000)
        self.assertEqual(ollama_cost, 0.0)

    def test_record_and_summary(self):
        usage_tracker.record_usage(
            provider="google",
            model="gemini-2.5-flash",
            input_tokens=1000,
            output_tokens=500,
            source="web",
            duration_sec=0.45,
        )
        usage_tracker.record_usage(
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            input_tokens=2000,
            output_tokens=1000,
            source="telegram",
            duration_sec=1.2,
        )

        self.assertTrue(self.usage_file.exists())
        summary = usage_tracker.get_usage_summary()

        self.assertEqual(summary["total_requests"], 2)
        self.assertEqual(summary["total_input_tokens"], 3000)
        self.assertEqual(summary["total_output_tokens"], 1500)
        self.assertEqual(summary["total_tokens"], 4500)
        self.assertIn("google", summary["by_provider"])
        self.assertIn("anthropic", summary["by_provider"])
        self.assertGreater(summary["total_cost_usd"], 0.0)

    def test_budget_status(self):
        # Record small usage
        usage_tracker.record_usage("google", "gemini-2.5-flash", 1000, 500)
        status_unlimited = usage_tracker.check_budget_status(None)
        self.assertFalse(status_unlimited["budget_active"])
        self.assertFalse(status_unlimited["exhausted"])

        # Cap at $10.00
        status_ok = usage_tracker.check_budget_status(10.00)
        self.assertTrue(status_ok["budget_active"])
        self.assertFalse(status_ok["exhausted"])

        # Cap at $0.0000001 (artificially exhausted)
        status_exhausted = usage_tracker.check_budget_status(0.0000001)
        self.assertTrue(status_exhausted["exhausted"])


    def test_record_usage_robust_types(self):
        # Should handle None, strings, or invalid numbers without crashing
        res = usage_tracker.record_usage(
            provider="google",
            model="gemini-2.5-flash",
            input_tokens=None,
            output_tokens="invalid",
        )
        self.assertEqual(res["input_tokens"], 0)
        self.assertEqual(res["output_tokens"], 0)
        self.assertEqual(res["total_tokens"], 0)

        cost = usage_tracker.calculate_cost("gemini-2.5-flash", None, "bad")
        self.assertEqual(cost, 0.0)


    def test_HIGH_08_fallback_provider_logged_in_usage_ledger(self):
        """HIGH-08: When failover occurs, usage tracker records the actual fallback provider and model."""
        from unittest.mock import patch
        import server
        cfg = {
            "provider": "anthropic",
            "model": "claude-3-5-sonnet-latest",
            "base_url": "",
            "api_key": "sk-ant-test",
            "gemini_api_key": "AIzaTestKey",
            "fallback_providers": ["gemini"],
        }

        with patch("server._call_single_llm") as mock_call, \
             patch("usage_tracker.record_usage") as mock_record:
            mock_call.side_effect = [server.LLMError("Primary failed"), "Hello from Gemini"]
            res = server.call_llm_with_fallback(cfg, "system", [{"role": "user", "content": "hi"}])
            self.assertEqual(res, "Hello from Gemini")
            self.assertTrue(mock_record.called)
            args, kwargs = mock_record.call_args
            prov = kwargs.get("provider") or (args[0] if len(args) > 0 else "")
            self.assertEqual(prov, "gemini")


if __name__ == "__main__":
    unittest.main()
