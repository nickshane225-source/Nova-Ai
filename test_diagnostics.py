#!/usr/bin/env python3
"""
Unit tests for Nova AI Diagnostics Doctor (diagnostics.py)
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import diagnostics


class TestDiagnostics(unittest.TestCase):
    def test_check_python_environment(self):
        res = diagnostics.check_python_environment()
        self.assertEqual(res["category"], "Environment")
        self.assertIn(res["status"], ["ok", "error"])

    def test_check_disk_and_storage(self):
        res = diagnostics.check_disk_and_storage()
        self.assertIsInstance(res, list)
        self.assertGreaterEqual(len(res), 2)
        names = [r["name"] for r in res]
        self.assertIn("Data Directory Writable", names)
        self.assertIn("Workspace Directory Writable", names)

    def test_check_database_integrity(self):
        res = diagnostics.check_database_integrity()
        self.assertEqual(res["category"], "Database")
        self.assertIn(res["status"], ["ok", "warning", "error"])

    def test_check_llm_providers(self):
        # Without any keys
        res_empty = diagnostics.check_llm_providers(cfg={})
        self.assertIsInstance(res_empty, list)
        self.assertTrue(any(r["status"] == "warning" for r in res_empty))

        # With gemini key
        res_gemini = diagnostics.check_llm_providers(cfg={"gemini_api_key": "test_key"})
        self.assertTrue(any(r["name"] == "Google Gemini" and r["status"] == "ok" for r in res_gemini))

    def test_check_llm_providers_real_provider_labels_never_gemini_by_default(self):
        # 1. OpenAI configured API key must be labeled OpenAI, not Google Gemini
        cfg_openai = {"provider": "openai", "api_key": "sk-openai-test-key", "model": "gpt-4o"}
        res_openai = diagnostics.check_llm_providers(cfg=cfg_openai)
        names_openai = [r["name"] for r in res_openai if r.get("status") == "ok"]
        self.assertIn("OpenAI", names_openai)
        self.assertNotIn("Google Gemini", names_openai)

        # 2. Anthropic configured API key must be labeled Anthropic Claude, not Google Gemini
        cfg_anthropic = {"provider": "anthropic", "api_key": "sk-ant-test-key", "model": "claude-3-5-sonnet"}
        res_anthropic = diagnostics.check_llm_providers(cfg=cfg_anthropic)
        names_anthropic = [r["name"] for r in res_anthropic if r.get("status") == "ok"]
        self.assertIn("Anthropic Claude", names_anthropic)
        self.assertNotIn("Google Gemini", names_anthropic)

        # 3. Google Gemini configured API key
        cfg_gemini = {"provider": "gemini", "api_key": "AIzaSy-test-key", "model": "gemini-2.5-flash"}
        res_gem = diagnostics.check_llm_providers(cfg=cfg_gemini)
        names_gem = [r["name"] for r in res_gem if r.get("status") == "ok"]
        self.assertIn("Google Gemini", names_gem)

        # 4. Alias _check_llm_providers works identically
        res_alias = diagnostics._check_llm_providers(cfg=cfg_openai)
        self.assertEqual([r["name"] for r in res_alias], [r["name"] for r in res_openai])

    def test_run_diagnostics(self):
        diag = diagnostics.run_diagnostics(cfg={"gemini_api_key": "dummy"})
        self.assertIn("overall_status", diag)
        self.assertIn(diag["overall_status"], ["healthy", "degraded", "unhealthy"])
        self.assertIn("summary", diag)
        self.assertIn("checks", diag)
        self.assertGreater(len(diag["checks"]), 4)


if __name__ == "__main__":
    unittest.main()
