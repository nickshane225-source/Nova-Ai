"""
Unit tests for Workspace Path Boundary security enforcement.
"""
import unittest
import os
import sys
import platform
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server

class TestWorkspaceBoundary(unittest.TestCase):

    def setUp(self):
        self.workspace = server.WORKSPACE.resolve()
        self.test_sub_dir = self.workspace / "_boundary_test_dir"
        self.test_sub_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.test_sub_dir.exists():
            import shutil
            shutil.rmtree(self.test_sub_dir, ignore_errors=True)

    def test_absolute_path_outside_rejected(self):
        outside_path = r"C:\Windows\System32\cmd.exe" if platform.system() == "Windows" else "/bin/bash"
        with self.assertRaises(PermissionError):
            server.resolve_workspace_path(outside_path)

        # WRITE_FILE tool returns clear error without touching file
        res = server.run_skill({}, "WRITE_FILE", f"{outside_path} | malicious payload")
        self.assertEqual(res, "Path is outside the Nova workspace.")

        # READ_FILE tool returns clear error
        res_read = server.run_skill({}, "READ_FILE", outside_path)
        self.assertEqual(res_read, "Path is outside the Nova workspace.")

    def test_dot_dot_escape_rejected(self):
        escape_path = "../../forbidden_escape.txt"
        with self.assertRaises(PermissionError):
            server.resolve_workspace_path(escape_path)

        res = server.run_skill({}, "WRITE_FILE", f"{escape_path} | escape attempt")
        self.assertEqual(res, "Path is outside the Nova workspace.")

        res_edit = server.run_skill({}, "EDIT_FILE", f"{escape_path} | old | new")
        self.assertEqual(res_edit, "Path is outside the Nova workspace.")

    def test_normal_relative_path_allowed(self):
        rel_file = "_boundary_test_dir/valid_file.txt"
        resolved = server.resolve_workspace_path(rel_file)
        self.assertTrue(resolved.is_relative_to(self.workspace))

        res = server.run_skill({}, "WRITE_FILE", f"{rel_file} | safe hello world")
        self.assertIn("Created file", res)
        self.assertTrue(resolved.exists())
        self.assertEqual(resolved.read_text(encoding="utf-8"), "safe hello world")

        # EDIT_FILE works
        edit_res = server.run_skill({}, "EDIT_FILE", f"{rel_file} | safe hello world | updated safe text")
        self.assertIn("Successfully edited", edit_res)
        self.assertEqual(resolved.read_text(encoding="utf-8"), "updated safe text")

        # READ_FILE works
        read_res = server.run_skill({}, "READ_FILE", rel_file)
        self.assertIn("updated safe text", read_res)

    def test_symlink_pointing_outside_rejected(self):
        # Create a temp file outside workspace
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"secret external data")
            tmp_path = Path(tmp.name).resolve()

        symlink_path = self.test_sub_dir / "symlink_to_external.txt"
        try:
            try:
                symlink_path.symlink_to(tmp_path)
            except (OSError, NotImplementedError) as e:
                raise unittest.SkipTest(f"Symlinks not supported or permitted on this environment: {e}")

            # Verify resolve_workspace_path detects the symlink escape
            with self.assertRaises(PermissionError):
                server.resolve_workspace_path(f"_boundary_test_dir/{symlink_path.name}")

            res = server.run_skill({}, "READ_FILE", f"_boundary_test_dir/{symlink_path.name}")
            self.assertEqual(res, "Path is outside the Nova workspace.")
        finally:
            if symlink_path.is_symlink() or symlink_path.exists():
                try:
                    symlink_path.unlink()
                except Exception:
                    pass
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def test_override_and_system_folder_protection(self):
        # Even with allow_outside_workspace=True, system folders are strictly rejected
        cfg_override = {"allow_outside_workspace": True}
        system_path = r"C:\Windows\System32\drivers\etc\hosts" if platform.system() == "Windows" else "/etc/passwd"
        
        with self.assertRaises(PermissionError):
            server.resolve_workspace_path(system_path, cfg=cfg_override)

        res = server.run_skill(cfg_override, "WRITE_FILE", f"{system_path} | blocked write")
        self.assertEqual(res, "Path is outside the Nova workspace.")

if __name__ == "__main__":
    unittest.main()
