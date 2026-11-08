"""
Regression tests for Batch 5c Item 6:
- Provider label matching: mistral-nemo-3b and phi3-mini must NOT match OpenAI
- Exact or prefix-based matching for OpenAI models (gpt-*, o1, o3-mini)
- Failed fallback attempts record token usage when the provider returns usage metadata.
"""
import unittest
from unittest.mock import MagicMock, patch

import diagnostics
import server
import usage_tracker


class TestBatch5cProviderLabelsAndFallbackUsage(unittest.TestCase):
    def test_provider_labels_mistral_and_phi_must_not_match_openai(self):
        """mistral-nemo-3b and phi3-mini must never be mislabeled as OpenAI."""
        test_cfgs_not_openai = [
            {"model": "mistral-nemo-3b"},
            {"model": "phi3-mini"},
            {"provider": "openai", "model": "mistral-nemo-3b"},
            {"provider": "openai", "model": "phi3-mini"},
            {"provider": "custom", "model": "mistral-nemo-3b"},
            {"provider": "custom", "model": "phi3-mini"},
            {"model": "llama-3-8b"},
        ]

        for cfg in test_cfgs_not_openai:
            label = diagnostics._detect_provider_from_cfg(cfg)
            self.assertNotEqual(
                label,
                "OpenAI",
                f"Model '{cfg.get('model')}' with provider '{cfg.get('provider')}' must NOT match OpenAI",
            )

        # Verified OpenAI models MUST match OpenAI
        test_cfgs_openai = [
            {"provider": "openai", "model": "gpt-4o"},
            {"provider": "openai", "model": "gpt-4o-mini"},
            {"provider": "openai", "model": "o3-mini"},
            {"provider": "openai", "model": "o1-preview"},
            {"base_url": "https://api.openai.com/v1"},
        ]
        for cfg in test_cfgs_openai:
            label = diagnostics._detect_provider_from_cfg(cfg)
            self.assertEqual(
                label,
                "OpenAI",
                f"Model '{cfg.get('model')}' with base '{cfg.get('base_url')}' MUST match OpenAI",
            )

    def test_record_token_usage_for_failed_fallback_attempts_with_usage(self):
        """When a fallback provider fails but returns usage info, token usage is recorded."""
        cfg = {
            "provider": "anthropic",
            "model": "claude-3-5-sonnet",
            "api_key": "sk-mock-key",
            "fallback_providers": ["gemini"],
            "gemini_api_key": "mock-gemini-key",
        }

        # Primary raises error with no usage
        primary_err = server.LLMError("Anthropic endpoint down 503")

        # Fallback raises error WITH usage metadata
        fallback_err = server.LLMError("Gemini rate limit 429")
        fallback_err.usage = {"prompt_tokens": 150, "completion_tokens": 25}

        recorded_events = []

        def mock_record_usage(provider, model, input_tokens, output_tokens, duration_sec=0.0):
            recorded_events.append({
                "provider": provider,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            })

        def mock_single_llm(call_cfg, system, messages):
            if call_cfg.get("provider") == "anthropic":
                raise primary_err
            else:
                raise fallback_err

        with patch("server._call_single_llm", side_effect=mock_single_llm):
            with patch("usage_tracker.record_usage", side_effect=mock_record_usage):
                with self.assertRaises(server.LLMError):
                    server.call_llm_with_fallback(cfg, "system", [{"role": "user", "content": "hi"}])

        self.assertEqual(len(recorded_events), 1)
        self.assertEqual(recorded_events[0]["provider"], "gemini")
        self.assertEqual(recorded_events[0]["input_tokens"], 150)
        self.assertEqual(recorded_events[0]["output_tokens"], 25)


if __name__ == "__main__":
    unittest.main()
