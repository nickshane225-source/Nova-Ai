import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import skills_engine


class TestFrozenModeUserSkills(unittest.TestCase):
    def setUp(self):
        self.orig_frozen = getattr(sys, "frozen", False)
        self.orig_meipass = getattr(sys, "_MEIPASS", None)
        self.orig_executable = sys.executable

        self.temp_dir = tempfile.mkdtemp(prefix="nova_frozen_skills_test_")
        self.temp_path = Path(self.temp_dir)
        self.exe_dir = self.temp_path / "bin"
        self.exe_dir.mkdir(parents=True, exist_ok=True)
        self.fake_exe = self.exe_dir / "nova.exe"
        self.fake_exe.touch()

    def tearDown(self):
        if self.orig_frozen:
            sys.frozen = self.orig_frozen
        elif hasattr(sys, "frozen"):
            del sys.frozen

        if self.orig_meipass is not None:
            sys._MEIPASS = self.orig_meipass
        elif hasattr(sys, "_MEIPASS"):
            del sys._MEIPASS

        sys.executable = self.orig_executable
        skills_engine.invalidate_cache()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_frozen_mode_bundled_and_user_skills_persistence(self):
        # 1. Setup initial frozen session with MEIPASS #1
        meipass_1 = self.temp_path / "meipass_1"
        bundled_skills_1 = meipass_1 / "skills" / "developer"
        bundled_skills_1.mkdir(parents=True, exist_ok=True)
        (bundled_skills_1 / "bundled_review.md").write_text(
            "---\nname: bundled_review\ndescription: Bundled code review procedure\ntriggers: review, pr\n---\nReview diff.",
            encoding="utf-8"
        )

        sys.frozen = True
        sys._MEIPASS = str(meipass_1)
        sys.executable = str(self.fake_exe)
        skills_engine.invalidate_cache()

        skills = skills_engine.load_skills("developer")
        names = [s.name for s in skills]
        self.assertIn("bundled_review", names)
        self.assertNotIn("custom_deploy", names)

        # 2. Install a user skill into writable storage
        installed_path = skills_engine.install_user_skill(
            mode="developer",
            name="custom_deploy",
            content="Deploy containers using kubectl.",
            description="Kubernetes deployment procedure",
            triggers=["deploy", "k8s"]
        )

        # Ensure it went into data/user_skills next to exe
        expected_dir = self.exe_dir / "data" / "user_skills" / "developer"
        self.assertTrue(installed_path.exists())
        self.assertEqual(installed_path.parent.resolve(), expected_dir.resolve())

        # Verify both bundled and user skills are loaded
        skills_after_install = skills_engine.load_skills("developer")
        names_after = [s.name for s in skills_after_install]
        self.assertIn("bundled_review", names_after)
        self.assertIn("custom_deploy", names_after)

        # 3. Simulate "restart" by creating a fresh MEIPASS #2 (MEIPASS #1 is discarded)
        shutil.rmtree(meipass_1, ignore_errors=True)
        meipass_2 = self.temp_path / "meipass_2"
        bundled_skills_2 = meipass_2 / "skills" / "developer"
        bundled_skills_2.mkdir(parents=True, exist_ok=True)
        (bundled_skills_2 / "bundled_review.md").write_text(
            "---\nname: bundled_review\ndescription: Bundled code review procedure\ntriggers: review, pr\n---\nReview diff.",
            encoding="utf-8"
        )

        sys._MEIPASS = str(meipass_2)
        skills_engine.invalidate_cache()

        # Load skills after "restart": custom_deploy must still be present!
        skills_after_restart = skills_engine.load_skills("developer")
        names_restart = [s.name for s in skills_after_restart]
        self.assertIn("bundled_review", names_restart, "Bundled skills should load from new _MEIPASS")
        self.assertIn("custom_deploy", names_restart, "User installed skill must persist across restarts")

        # Test trigger matching with persisted user skill
        selected = skills_engine.select_skills("developer", "deploy to k8s cluster")
        self.assertTrue(any(s.name == "custom_deploy" for s in selected))


if __name__ == "__main__":
    unittest.main()
