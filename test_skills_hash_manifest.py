import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server
import skills_engine


class TestSkillsHashManifest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.tmp_path = Path(self.tmp_dir)

        self.user_skills_dir = self.tmp_path / "data" / "user_skills"
        self.user_skills_dir.mkdir(parents=True, exist_ok=True)
        (self.user_skills_dir / "developer").mkdir(parents=True, exist_ok=True)
        (self.user_skills_dir / "cyber").mkdir(parents=True, exist_ok=True)

        self.bundled_skills_dir = self.tmp_path / "skills"
        (self.bundled_skills_dir / "developer").mkdir(parents=True, exist_ok=True)
        (self.bundled_skills_dir / "cyber").mkdir(parents=True, exist_ok=True)

        # Create one bundled skill
        bundled_skill_content = "---\nname: bundled_test\ndescription: Bundled test skill\ntriggers: test\n---\nBundled body content"
        (self.bundled_skills_dir / "developer" / "bundled_test.md").write_text(bundled_skill_content, encoding="utf-8")

        self.orig_get_user = skills_engine.get_user_skills_dir
        self.orig_get_bundled = skills_engine.get_bundled_skills_dir
        skills_engine.get_user_skills_dir = lambda: self.user_skills_dir
        skills_engine.get_bundled_skills_dir = lambda: self.bundled_skills_dir

        skills_engine.invalidate_cache()

    def tearDown(self):
        skills_engine.get_user_skills_dir = self.orig_get_user
        skills_engine.get_bundled_skills_dir = self.orig_get_bundled
        skills_engine.invalidate_cache()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_bundled_skills_load_with_empty_or_missing_manifest(self):
        manifest_file = skills_engine.get_manifest_path()
        if manifest_file.exists():
            manifest_file.unlink()

        # Load skills when manifest does not exist
        skills = skills_engine.load_skills("developer")
        names = [s.name for s in skills]
        self.assertIn("bundled_test", names)

        # Create an empty manifest file
        skills_engine.atomic_write_json(manifest_file, {"skills": {}})
        skills_engine.invalidate_cache()

        skills = skills_engine.load_skills("developer")
        names = [s.name for s in skills]
        self.assertIn("bundled_test", names)

    def test_approve_restart_skill_loads(self):
        skill_name = "custom_tool"
        raw_content = "def run():\n    return 'hello world'\n"
        mode = "developer"

        # 1. Preview generation (exact bytes & sha256)
        final_content, final_bytes, expected_sha = skills_engine.prepare_skill_content_to_write(
            mode=mode, name=skill_name, content=raw_content
        )
        self.assertEqual(hashlib.sha256(final_bytes).hexdigest(), expected_sha)
        self.assertIn("name: custom_tool", final_content)

        # 2. Simulate pending action preview string
        raw_arg = f"{mode} | {skill_name} | {raw_content}"
        # Trigger create_pending_action logic
        parts = [p.strip() for p in raw_arg.split("|", 2)]
        fc, fb, p_sha = skills_engine.prepare_skill_content_to_write(parts[0], parts[1], parts[2])
        self.assertEqual(p_sha, expected_sha)
        self.assertEqual(fc, final_content)

        # 3. User approves -> install_user_skill
        dest = skills_engine.install_user_skill(
            mode=mode,
            name=skill_name,
            content=raw_content,
            trusted=True,
            source="user_ui"
        )
        self.assertTrue(dest.exists())
        self.assertEqual(dest.read_bytes(), final_bytes)

        # Verify manifest entry matches expected SHA-256
        manifest = skills_engine.load_skills_manifest()
        key = f"{mode}:{skill_name}"
        self.assertIn(key, manifest.get("skills", {}))
        self.assertEqual(manifest["skills"][key]["sha256"], expected_sha)

        # 4. Simulate restart (invalidate cache) -> skill loads
        skills_engine.invalidate_cache()
        loaded = skills_engine.load_skills(mode)
        loaded_names = [s.name for s in loaded]
        self.assertIn("custom_tool", loaded_names)

        loaded_skill = next(s for s in loaded if s.name == "custom_tool")
        self.assertTrue(loaded_skill.is_trusted)

    def test_edit_one_byte_skill_is_disabled(self):
        skill_name = "tamper_target"
        raw_content = "print('original version')"
        mode = "developer"

        dest = skills_engine.install_user_skill(
            mode=mode,
            name=skill_name,
            content=raw_content,
            trusted=False,
            source="external"
        )

        # Initially loads
        skills_engine.invalidate_cache()
        loaded = skills_engine.load_skills(mode)
        self.assertIn("tamper_target", [s.name for s in loaded])

        # Tamper: mutate exactly one byte on disk
        data = bytearray(dest.read_bytes())
        data[-1] = ord("\n") if data[-1] != ord("\n") else ord(" ")
        dest.write_bytes(bytes(data))

        # Restart / reload -> skill is refused/disabled due to hash mismatch
        skills_engine.invalidate_cache()
        loaded_after_tamper = skills_engine.load_skills(mode)
        self.assertNotIn("tamper_target", [s.name for s in loaded_after_tamper])

    def test_windows_crlf_skill_approve_restart_tamper_and_security_logging(self):
        """
        Item 1 Skills on Windows:
        - CRLF input preserved across preparation, write_bytes, and read_bytes without newline translation.
        - Approve, restart -> skill loads cleanly.
        - Mutate one byte -> skill disabled on restart/reload.
        - log_security_event exists and records tampering event.
        """
        import audit_logger
        self.assertTrue(hasattr(audit_logger, "log_security_event"))
        self.assertTrue(hasattr(audit_logger, "log_audit_event"))

        audit_file = self.tmp_path / "data" / "audit.jsonl"
        audit_logger.set_audit_file(audit_file)

        skill_name = "windows_crlf_tool"
        raw_crlf_content = "def run():\r\n    msg = 'hello windows'\r\n    return msg\r\n"
        mode = "developer"

        # 1. Prepare content with CRLF input
        final_content, final_bytes, expected_sha = skills_engine.prepare_skill_content_to_write(
            mode=mode, name=skill_name, content=raw_crlf_content
        )
        # Verify CRLF is preserved in final bytes
        self.assertIn(b"\r\n", final_bytes)
        self.assertEqual(hashlib.sha256(final_bytes).hexdigest(), expected_sha)

        # 2. Approve and install
        dest = skills_engine.install_user_skill(
            mode=mode,
            name=skill_name,
            content=raw_crlf_content,
            trusted=True,
            source="user_ui"
        )
        self.assertTrue(dest.exists())
        self.assertEqual(dest.read_bytes(), final_bytes)

        # 3. Restart (cache invalidate) -> loads cleanly
        skills_engine.invalidate_cache()
        loaded = skills_engine.load_skills(mode)
        loaded_names = [s.name for s in loaded]
        self.assertIn(skill_name, loaded_names)

        # 4. Tamper by 1 byte
        tampered_bytes = bytearray(dest.read_bytes())
        tampered_bytes[-1] = ord("\n") if tampered_bytes[-1] != ord("\n") else ord("\r")
        dest.write_bytes(bytes(tampered_bytes))

        # 5. Reload -> skill disabled and security event logged
        skills_engine.invalidate_cache()
        loaded_after_tamper = skills_engine.load_skills(mode)
        self.assertNotIn(skill_name, [s.name for s in loaded_after_tamper])

        # Verify security audit event was logged
        recent = audit_logger.get_recent_audit_events(limit=10)
        tamper_events = [e for e in recent if e.get("tool") == "SKILL_HASH_TAMPERED"]
        self.assertTrue(len(tamper_events) > 0, "Expected SKILL_HASH_TAMPERED event in audit log")
        self.assertIn(skill_name, tamper_events[0]["preview"])


if __name__ == "__main__":
    unittest.main()
