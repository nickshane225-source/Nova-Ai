"""
Regression tests for Batch 7 (CRIT-04, CRIT-05, HIGH-11):
- Python 3.10 minimum version requirement across README.md, run.bat, and server.py startup check
- PyInstaller flags and hidden imports in build_exe.bat
- sys._MEIPASS-aware resource path resolution in skills_engine and integrations
- quick_summon.bat uses port 8765 and boot URL; installer_wizard does not reference obsolete speech_engine.py.
"""
import inspect
import re
import sys
import unittest
from pathlib import Path

import installer_wizard
import integrations
import integrations.github_connector
import server
import skills_engine


ROOT = Path(__file__).resolve().parent


class TestBatch7PackagingAndLaunchers(unittest.TestCase):
    def test_CRIT_04_python_310_minimum_requirement(self):
        """Python 3.10+ requirement must be enforced in README.md, run.bat, and server.py startup check."""
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Python 3.10+", readme)
        self.assertNotIn("Python 3.8+", readme)

        run_bat = (ROOT / "run.bat").read_text(encoding="utf-8")
        self.assertIn("Python 3.10+", run_bat)
        self.assertIn("sys.version_info >= (3, 10)", run_bat)

        server_code = (ROOT / "server.py").read_text(encoding="utf-8")
        self.assertIn("sys.version_info < (3, 10)", server_code)
        self.assertIn("Nova AI requires Python 3.10 or higher", server_code)

    def test_CRIT_05_build_exe_hidden_imports_and_skills_data(self):
        """build_exe.bat must bundle skills directory and include all required hidden imports."""
        build_bat = (ROOT / "build_exe.bat").read_text(encoding="utf-8")

        self.assertIn('--add-data "skills;skills"', build_bat)
        self.assertIn('--add-data "web;web"', build_bat)

        required_hidden_imports = [
            "skills_engine",
            "audit_logger",
            "guardian_agent",
            "plan_mode",
            "telegram_gateway",
            "discord_gateway",
            "usage_tracker",
            "diagnostics",
            "integrations.github_connector",
        ]
        for imp in required_hidden_imports:
            self.assertIn(f'--hidden-import "{imp}"', build_bat, f"Missing hidden import: {imp}")

    def test_CRIT_05_meipass_aware_resource_paths(self):
        """skills_engine and integrations must check sys._MEIPASS when running frozen in PyInstaller."""
        se_code = (ROOT / "skills_engine.py").read_text(encoding="utf-8")
        self.assertIn("_MEIPASS", se_code)

        int_code = (ROOT / "integrations" / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("_MEIPASS", int_code)

        gh_code = (ROOT / "integrations" / "github_connector.py").read_text(encoding="utf-8")
        self.assertIn("_MEIPASS", gh_code)

    def test_HIGH_11_quick_summon_port_8765_and_secure_fallback(self):
        """quick_summon.bat must check for port 8765, never persist boot codes, avoid ExecutionPolicy Bypass, and fallback to run.bat."""
        qs_code = (ROOT / "quick_summon.bat").read_text(encoding="utf-8")
        self.assertIn("8765", qs_code)
        self.assertNotIn("-ExecutionPolicy Bypass", qs_code)
        self.assertNotIn("nova_boot_url.txt", qs_code)
        self.assertNotIn("bootUrl", qs_code)
        self.assertIn("Nova is running - use the open tab or restart Nova", qs_code)
        self.assertIn("run.bat", qs_code)

    def test_HIGH_11_installer_wizard_no_speech_engine(self):
        """installer_wizard.py must verify install health and have no references to obsolete speech_engine.py."""
        iw_code = (ROOT / "installer_wizard.py").read_text(encoding="utf-8")
        self.assertNotIn("import speech_engine", iw_code)
        self.assertNotIn("speech_engine.py", iw_code.replace("Obsolete speech_engine.py has been removed", ""))
        self.assertTrue(hasattr(installer_wizard, "verify_installation_health"))


if __name__ == "__main__":
    unittest.main()
