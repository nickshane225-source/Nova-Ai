import io
import json
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

import server


class TestListModelsAnd404Handling(unittest.TestCase):
    """
    Tests for:
    1. list_provider_models helper for Gemini, OpenAI, Anthropic, Ollama.
    2. Strict 404 check: only HTTP 404 produces model not found / invalid_model category.
    3. UI verification of the 'List models' button in Settings.
    """

    def test_list_provider_models_requires_key_when_empty(self):
        with patch.object(server, "get_config", return_value={"provider": "gemini", "api_key": ""}):
            res = server.list_provider_models(provider="gemini", api_key="")
            self.assertFalse(res["ok"])
            self.assertIn("No API key configured", res["error"])

    def test_list_provider_models_gemini_strips_prefix(self):
        fake_key = "AQ." + "FakeKeyForListingModels0123456789"
        mock_resp_data = {
            "models": [
                {"name": "models/gemini-2.5-flash", "displayName": "Gemini 2.5 Flash"},
                {"name": "models/gemini-2.5-pro", "displayName": "Gemini 2.5 Pro"},
            ]
        }
        mock_cm = MagicMock()
        mock_cm.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
        mock_cm.__enter__.return_value = mock_cm

        with patch("urllib.request.urlopen", return_value=mock_cm):
            res = server.list_provider_models(provider="gemini-native", api_key=fake_key)
            self.assertTrue(res["ok"])
            self.assertEqual(res["models"], ["gemini-2.5-flash", "gemini-2.5-pro"])
            self.assertEqual(res["count"], 2)

    def test_list_provider_models_openai(self):
        fake_key = "sk-" + "fakeOpenAiKeyForTestingModels12345"
        mock_resp_data = {
            "data": [
                {"id": "gpt-4o"},
                {"id": "gpt-4o-mini"},
            ]
        }
        mock_cm = MagicMock()
        mock_cm.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
        mock_cm.__enter__.return_value = mock_cm

        with patch("urllib.request.urlopen", return_value=mock_cm):
            res = server.list_provider_models(provider="openai", api_key=fake_key, base_url="https://api.openai.com/v1")
            self.assertTrue(res["ok"])
            self.assertEqual(res["models"], ["gpt-4o", "gpt-4o-mini"])

    def test_list_provider_models_anthropic(self):
        fake_key = "sk-ant-" + "fakeClaudeKeyForTestingModels12345"
        mock_resp_data = {
            "data": [
                {"id": "claude-3-5-sonnet-20241022"},
                {"id": "claude-3-5-haiku-20241022"},
            ]
        }
        mock_cm = MagicMock()
        mock_cm.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
        mock_cm.__enter__.return_value = mock_cm

        with patch("urllib.request.urlopen", return_value=mock_cm):
            res = server.list_provider_models(provider="anthropic", api_key=fake_key)
            self.assertTrue(res["ok"])
            self.assertEqual(res["models"], ["claude-3-5-haiku-20241022", "claude-3-5-sonnet-20241022"])

    def test_list_provider_models_http_error_handled(self):
        fake_key = "sk-" + "fakeKeyForHttpError0123456789"
        err = urllib.error.HTTPError(
            url="https://api.openai.com/v1/models",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=io.BytesIO(b'{"error": {"message": "Invalid API key provided"}}'),
        )
        with patch("urllib.request.urlopen", side_effect=err):
            res = server.list_provider_models(provider="openai", api_key=fake_key)
            self.assertFalse(res["ok"])
            self.assertEqual(res["status_code"], 401)
            self.assertIn("401", res["error"])

    def test_model_not_found_only_emitted_on_404(self):
        # 404 explicitly returns invalid_model
        m404 = server.map_llm_error_status(404, "Not Found", model="gpt-missing")
        self.assertEqual(m404["category"], "invalid_model")
        self.assertEqual(m404["status_code"], 404)
        self.assertIn("not found on this provider", m404["message"])

        # 400 with 'not_found' in body does NOT produce invalid_model
        m400 = server.map_llm_error_status(400, "error: resource not_found in request", model="gpt-test")
        self.assertNotEqual(m400["category"], "invalid_model")
        self.assertEqual(m400["category"], "bad_request")
        self.assertNotIn("not found on this provider", m400["message"])

        # 500 with 'not found' does NOT produce invalid_model
        m500 = server.map_llm_error_status(500, "internal error: model not found upstream", model="gpt-test")
        self.assertNotEqual(m500["category"], "invalid_model")
        self.assertEqual(m500["category"], "provider_outage")

    def test_settings_ui_has_list_models_button(self):
        with open("web/app.js", "r", encoding="utf-8") as f:
            app_js = f.read()
        self.assertIn('id="btnListModels"', app_js)
        self.assertIn("List models", app_js)
        self.assertIn('list="modelList"', app_js)
        self.assertIn("/api/config/models", app_js)


if __name__ == "__main__":
    unittest.main()
