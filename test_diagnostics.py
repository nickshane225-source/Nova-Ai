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

    def test_run_diagnostics(self):
        diag = diagnostics.run_diagnostics(cfg={"gemini_api_key": "dummy"})
        self.assertIn("overall_status", diag)
        self.assertIn(diag["overall_status"], ["healthy", "degraded", "unhealthy"])
        self.assertIn("summary", diag)
        self.assertIn("checks", diag)
        self.assertGreater(len(diag["checks"]), 4)


if __name__ == "__main__":
    unittest.main()
