#!/usr/bin/env python3
"""
Unit tests for Batch 6 (HIGH-08, MED-08): Provider Accounting and Diagnostics.
Zero third-party pip dependencies - Python standard library only.
"""
import unittest
from unittest.mock import MagicMock, patch

import diagnostics
import server
import usage_tracker


class TestBatch6ProviderAccounting(unittest.TestCase):
    def test_call_llm_fallback_logs_actual_answered_provider_and_model(self):
        """
        When primary provider fails and fallback provider answers,
        record_usage must log the provider and model that actually answered,
        not the failed primary.
        """
        cfg = {
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-primary-openai",
            "fallback_providers": ["anthropic"],
            "anthropic_api_key": "sk-fallback-anthropic",
            "anthropic_model": "claude-3-5-sonnet-20241022",
        }

        def mock_call_single(call_cfg, system, messages):
            prov = call_cfg.get("provider")
            if prov == "openai":
                raise server.LLMError("Primary OpenAI endpoint timeout 504")
            elif prov == "anthropic":
                return "Fallback response from Claude"
            raise server.LLMError(f"Unexpected provider: {prov}")

        with patch("server._call_single_llm", side_effect=mock_call_single):
            with patch("usage_tracker.record_usage") as mock_record:
                reply = server.call_llm_with_fallback(cfg, "system prompt", [{"role": "user", "content": "hi"}])
                self.assertEqual(reply, "Fallback response from Claude")
                mock_record.assert_called_once()
                kw = mock_record.call_args.kwargs
                # Must log the actual answered fallback provider and model
                self.assertEqual(kw.get("provider"), "anthropic")
                self.assertEqual(kw.get("model"), "claude-3-5-sonnet-20241022")
                self.assertNotEqual(kw.get("provider"), "openai")
                self.assertNotEqual(kw.get("model"), "gpt-4o")

    def test_call_llm_vision_budget_check_and_token_usage_accounting(self):
        """
        call_llm_vision must check the budget cap before calling,
        block when exhausted, and record token usage upon success.
        """
        cfg = {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-vision-test",
            "monthly_budget_usd": 10.0,
        }

        # 1. Budget exhausted blocks vision call before network request
        with patch("usage_tracker.check_budget_status", return_value={"exhausted": True, "spent_usd": 12.50, "cap_usd": 10.0}):
            with patch("server.http_post") as mock_http:
                with self.assertRaises(server.LLMError) as ctx:
                    server.call_llm_vision(cfg, "Analyze screen", "base64dummyimage")
                self.assertIn("Monthly budget limit reached", str(ctx.exception))
                mock_http.assert_not_called()

        # 2. Budget OK permits call and records usage
        mock_response = {
            "choices": [{"message": {"content": "Found 3 windows and 1 terminal open"}}]
        }
        with patch("usage_tracker.check_budget_status", return_value={"exhausted": False, "spent_usd": 2.50, "cap_usd": 10.0}):
            with patch("server.http_post", return_value=mock_response):
                with patch("usage_tracker.record_usage") as mock_record:
                    res = server.call_llm_vision(cfg, "Analyze screen", "base64dummyimage")
                    self.assertEqual(res, "Found 3 windows and 1 terminal open")
                    mock_record.assert_called_once()
                    kw = mock_record.call_args.kwargs
                    self.assertEqual(kw.get("provider"), "openai")
                    self.assertEqual(kw.get("model"), "gpt-4o-mini")
                    self.assertGreater(kw.get("input_tokens", 0), 1000)
                    self.assertGreater(kw.get("output_tokens", 0), 0)

    def test_diagnostics_check_llm_providers_real_labels_never_gemini_by_default(self):
        """
        diagnostics._check_llm_providers must label each configured API key
        by its real provider, never 'Google Gemini' by default.
        """
        # OpenAI config
        cfg_openai = {"provider": "openai", "api_key": "sk-real-openai", "model": "gpt-4o"}
        res_openai = diagnostics._check_llm_providers(cfg=cfg_openai)
        names_openai = [r["name"] for r in res_openai if r.get("status") == "ok"]
        self.assertIn("OpenAI", names_openai)
        self.assertNotIn("Google Gemini", names_openai)

        # Anthropic config
        cfg_anthropic = {"provider": "anthropic", "api_key": "sk-real-ant", "model": "claude-3-5-sonnet"}
        res_anthropic = diagnostics._check_llm_providers(cfg=cfg_anthropic)
        names_anthropic = [r["name"] for r in res_anthropic if r.get("status") == "ok"]
        self.assertIn("Anthropic Claude", names_anthropic)
        self.assertNotIn("Google Gemini", names_anthropic)

        # Gemini config
        cfg_gemini = {"provider": "gemini", "api_key": "AIzaSy-gemini-key", "model": "gemini-2.5-flash"}
        res_gemini = diagnostics._check_llm_providers(cfg=cfg_gemini)
        names_gemini = [r["name"] for r in res_gemini if r.get("status") == "ok"]
        self.assertIn("Google Gemini", names_gemini)


if __name__ == "__main__":
    unittest.main()
