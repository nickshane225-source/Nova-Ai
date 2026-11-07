"""
Unit tests for Task 6: Extensible Plugin & Connector Engine (integrations/).
Zero third-party pip dependencies - Python standard library only.
"""
import json
import unittest
from unittest.mock import MagicMock, patch

import integrations
from integrations.github_connector import GitHubConnector


class TestIntegrations(unittest.TestCase):
    def test_load_integrations_discovers_github(self):
        plugins = integrations.load_integrations()
        self.assertIn("github", plugins)
        self.assertIsInstance(plugins["github"], GitHubConnector)

    def test_github_connector_fetch_issues(self):
        connector = GitHubConnector()
        fake_api_response = json.dumps([
            {"number": 42, "title": "Implement fallback router", "state": "open"},
            {"number": 43, "title": "Add Telegram gateway", "state": "closed"}
        ]).encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_api_response
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = connector.run({}, "pocketpaw/pocketpaw | issues")
            self.assertIn("Issue #42", res)
            self.assertIn("Implement fallback router", res)

    def test_github_connector_invalid_args(self):
        connector = GitHubConnector()
        res = connector.run({}, "")
        self.assertIn("Usage:", res)

    def test_run_skill_github_integration(self):
        import server
        connector = GitHubConnector()
        with patch.object(connector, "run", return_value="Mocked GitHub output: 2 issues"):
            with patch.dict(integrations.REGISTRY, {"github": connector}):
                res = server.run_skill({}, "GITHUB", "pocketpaw/pocketpaw | issues")
                self.assertIn("Mocked GitHub output", res)


    def test_github_connector_tree(self):
        connector = GitHubConnector()
        mock_resp_info = MagicMock()
        mock_resp_info.read.return_value = json.dumps({"default_branch": "main"}).encode("utf-8")
        mock_resp_info.__enter__.return_value = mock_resp_info
        
        mock_resp_tree = MagicMock()
        mock_resp_tree.read.return_value = json.dumps({
            "tree": [
                {"path": "README.md", "type": "blob"},
                {"path": "src", "type": "tree"},
                {"path": "src/main.py", "type": "blob"},
            ]
        }).encode("utf-8")
        mock_resp_tree.__enter__.return_value = mock_resp_tree

        with patch("urllib.request.urlopen", side_effect=[mock_resp_info, mock_resp_tree]):
            res = connector.run({}, "pocketpaw/pocketpaw | tree")
            self.assertIn("File Tree for pocketpaw/pocketpaw", res)
            self.assertIn("README.md", res)
            self.assertIn("src/main.py", res)

    def test_github_connector_file_content(self):
        import base64
        connector = GitHubConnector()
        encoded = base64.b64encode(b"hello world from github").decode("ascii")
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"content": encoded, "encoding": "base64"}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = connector.run({}, "pocketpaw/pocketpaw | file:README.md")
            self.assertIn("hello world from github", res)

    def test_github_connector_security_traversal_blocked(self):
        connector = GitHubConnector()
        # Traversal check
        self.assertIn("Path traversal", connector.run({}, "../pocketpaw | info"))
        self.assertIn("Path traversal", connector.run({}, "pocketpaw/.. | info"))
        # Reserved device names
        self.assertIn("reserved device name", connector.run({}, "CON/repo | info"))
        self.assertIn("reserved device name", connector.run({}, "owner/NUL | info"))
        # Invalid format / characters
        self.assertIn("Invalid repository format", connector.run({}, "pocketpaw//repo | info"))
        self.assertIn("Invalid characters", connector.run({}, "pocket paw/repo | info"))

    def test_github_connector_empty_file_path(self):
        connector = GitHubConnector()
        res = connector.run({}, "pocketpaw/pocketpaw | file:")
        self.assertIn("Please specify a valid file path", res)


if __name__ == "__main__":
    unittest.main()
