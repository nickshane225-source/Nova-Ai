import unittest
import diagnostics


class TestProviderRegex(unittest.TestCase):
    def test_openai_model_boundary_matching(self):
        """
        Verify provider detection matches OpenAI for gpt-4o, gpt-4o-mini, gpt-4.1, o3-mini,
        and does NOT match OpenAI for mistral-nemo-3b, phi3-mini, llama3-8b.
        """
        openai_models = [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4.1",
            "gpt-4.1-mini",
            "o3-mini",
            "o1",
            "o1-mini",
            "o1-preview",
            "gpt-4",
            "gpt-3.5-turbo",
            "chatgpt-4o-latest",
        ]

        for model in openai_models:
            # 1. With provider explicitly set or inferred
            cfg = {"provider": "openai", "model": model}
            provider_label = diagnostics._detect_provider_from_cfg(cfg)
            self.assertEqual(
                provider_label,
                "OpenAI",
                f"Model '{model}' with provider 'openai' must be detected as 'OpenAI', got '{provider_label}'"
            )

            # 2. Inferred from model alone without custom base_url
            cfg_inferred = {"model": model}
            inferred_label = diagnostics._detect_provider_from_cfg(cfg_inferred)
            self.assertEqual(
                inferred_label,
                "OpenAI",
                f"Model '{model}' alone must be detected as 'OpenAI', got '{inferred_label}'"
            )

        non_openai_models = [
            "mistral-nemo-3b",
            "phi3-mini",
            "llama3-8b",
            "llama-3-8b",
            "mistral-7b-instruct",
            "claude-3-5-sonnet-20241022",
            "gemini-1.5-pro",
        ]

        for model in non_openai_models:
            # Under empty or default cfg, non-OpenAI models must never be detected as OpenAI
            cfg = {"model": model}
            provider_label = diagnostics._detect_provider_from_cfg(cfg)
            self.assertNotEqual(
                provider_label,
                "OpenAI",
                f"Model '{model}' must NOT be detected as 'OpenAI', got '{provider_label}'"
            )

            # Even if configured with provider: openai (e.g. via local compatible gateway)
            cfg_custom = {"provider": "openai", "model": model, "base_url": "http://localhost:1234/v1"}
            custom_label = diagnostics._detect_provider_from_cfg(cfg_custom)
            self.assertNotEqual(
                custom_label,
                "OpenAI",
                f"Local model '{model}' on custom server must NOT be detected as 'OpenAI'"
            )


if __name__ == "__main__":
    unittest.main()
