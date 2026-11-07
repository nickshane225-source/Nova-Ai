"""
Unit tests for Task 2: Multi-Model Fallback Router (server.py).
Zero third-party pip dependencies - Python standard library only.
"""
import unittest
from unittest.mock import patch, MagicMock

import server


class TestModelFallbackRouter(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(server.DEFAULT_CONFIG)
        self.cfg["provider"] = "openai"
        self.cfg["base_url"] = "https://generativelanguage.googleapis.com/v1beta/openai/"
        self.cfg["model"] = "gemini-3.5-flash-lite"
        self.cfg["api_key"] = "test-gemini-key"
        self.cfg["anthropic_api_key"] = "test-anthropic-key"
        self.cfg["fallback_providers"] = ["anthropic", "ollama"]

    def test_fallback_triggers_when_primary_fails(self):
        # Primary call fails with 429 rate limit or timeout
        def mock_call_llm(cfg, system, messages):
            if "generativelanguage" in cfg.get("base_url", "") or cfg.get("model") == "gemini-3.5-flash-lite":
                raise server.LLMError("API error 429: Resource has been exhausted (e.g. check quota).")
            if cfg.get("provider") == "anthropic":
                return "Hello from Anthropic fallback!"
            return "Fallback generic"

        with patch("server._call_single_llm", side_effect=mock_call_llm):
            reply = server.call_llm_with_fallback(self.cfg, "You are a helpful assistant", [{"role": "user", "content": "hi"}])
            self.assertEqual(reply, "Hello from Anthropic fallback!")

    def test_fallback_cycles_to_next_if_secondary_fails(self):
        def mock_call_llm(cfg, system, messages):
            if "generativelanguage" in cfg.get("base_url", ""):
                raise server.LLMError("API error 429: Quota exceeded")
            if cfg.get("provider") == "anthropic":
                raise server.LLMError("Could not reach the AI provider: timed out")
            if "11434" in cfg.get("base_url", "") or cfg.get("provider") == "ollama":
                return "Hello from Ollama local fallback!"
            return "Final fallback"

        with patch("server._call_single_llm", side_effect=mock_call_llm):
            reply = server.call_llm_with_fallback(self.cfg, "System prompt", [{"role": "user", "content": "test"}])
            self.assertEqual(reply, "Hello from Ollama local fallback!")

    def test_primary_succeeds_without_fallback(self):
        with patch("server._call_single_llm", return_value="Normal primary response"):
            reply = server.call_llm_with_fallback(self.cfg, "System", [{"role": "user", "content": "test"}])
            self.assertEqual(reply, "Normal primary response")


if __name__ == "__main__":
    unittest.main()
