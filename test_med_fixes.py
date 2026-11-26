"""
test_med_fixes.py - Verify MED-06 (GitHub zip extraction hardening),
MED-03 (/api/chat/stream SSE / CORS), and MED-04 (secret masking fallback).
"""

import unittest
import io
import zipfile
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import server
from integrations.github_connector import safe_extract_zip


class TestMedFixes(unittest.TestCase):

    # ------------------------------------------------------------------------
    # MED-06: GitHub Zip Extraction Hardening
    # ------------------------------------------------------------------------

    def test_01_zip_traversal_refused(self):
        """Relative path traversal (../) entries in zip archives must be refused."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../../escape.txt", "malicious traversal content")
        buf.seek(0)

        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError) as ctx:
                safe_extract_zip(buf, Path(td))
            self.assertIn("traversal", str(ctx.exception).lower())

    def test_02_zip_absolute_path_refused(self):
        """Absolute path entries in zip archives must be refused."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("/etc/passwd", "root:x:0:0:")
        buf.seek(0)

        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError) as ctx:
                safe_extract_zip(buf, Path(td))
            self.assertIn("absolute path", str(ctx.exception).lower())

    def test_03_zip_drive_letter_refused(self):
        """Windows drive letter entries (e.g. C:\...) in zip archives must be refused."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("C:\\Windows\\System32\\calc.exe", "fake")
        buf.seek(0)

        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError) as ctx:
                safe_extract_zip(buf, Path(td))
            self.assertIn("drive letter", str(ctx.exception).lower())

    def test_04_zip_symlink_refused(self):
        """Symlink entries in zip archives must be refused."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zi = zipfile.ZipInfo("symlink_entry")
            zi.create_system = 3  # Unix
            zi.external_attr = 0o120777 << 16  # S_IFLNK
            zf.writestr(zi, "/target/path")
        buf.seek(0)

        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError) as ctx:
                safe_extract_zip(buf, Path(td))
            self.assertIn("symlink", str(ctx.exception).lower())

    def test_05_zip_case_collision_duplicate_refused(self):
        """Duplicate entries differing only in case must be refused to prevent collision overwrites."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("README.md", "first version")
            zf.writestr("readme.MD", "second version")
        buf.seek(0)

        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError) as ctx:
                safe_extract_zip(buf, Path(td))
            self.assertIn("case-collision", str(ctx.exception).lower())

    def test_06_zip_reserved_windows_name_refused(self):
        """Windows reserved device names (CON, PRN, AUX, NUL, COM1-9, LPT1-9) must be refused."""
        for res_name in ("con.txt", "PRN.dat", "aux.c", "COM1", "sub/NUL.txt"):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr(res_name, "reserved content")
            buf.seek(0)

            with tempfile.TemporaryDirectory() as td:
                with self.assertRaises(ValueError) as ctx:
                    safe_extract_zip(buf, Path(td))
                self.assertIn("reserved windows device name", str(ctx.exception).lower())

    def test_07_zip_bomb_protections(self):
        """Zip bombs must be rejected by file count, total uncompressed size, and compression ratio."""
        # 1. File count cap
        buf_count = io.BytesIO()
        with zipfile.ZipFile(buf_count, "w") as zf:
            for i in range(10):
                zf.writestr(f"file_{i}.txt", "data")
        buf_count.seek(0)
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError) as ctx:
                safe_extract_zip(buf_count, Path(td), max_files=5)
            self.assertIn("entry count", str(ctx.exception).lower())

        # 2. Total size cap
        buf_size = io.BytesIO()
        with zipfile.ZipFile(buf_size, "w") as zf:
            zf.writestr("big.bin", b"X" * 2000)
        buf_size.seek(0)
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError) as ctx:
                safe_extract_zip(buf_size, Path(td), max_total_size=1000)
            self.assertIn("total uncompressed size", str(ctx.exception).lower())

        # 3. Compression ratio cap
        buf_ratio = io.BytesIO()
        with zipfile.ZipFile(buf_ratio, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("zeros.bin", b"\x00" * 50000)  # highly compressible zeros
        buf_ratio.seek(0)
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError) as ctx:
                safe_extract_zip(buf_ratio, Path(td), max_ratio=5.0)
            self.assertIn("compression ratio", str(ctx.exception).lower())

    def test_08_legitimate_zip_extracts_cleanly(self):
        """Legitimate repository archives extract cleanly."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("repo-main/README.md", "# Welcome")
            zf.writestr("repo-main/src/index.js", "console.log('hi');")
        buf.seek(0)

        with tempfile.TemporaryDirectory() as td:
            extracted = safe_extract_zip(buf, Path(td))
            self.assertEqual(len(extracted), 2)
            self.assertTrue((Path(td) / "README.md").is_file())
            self.assertTrue((Path(td) / "src" / "index.js").is_file())

    # ------------------------------------------------------------------------
    # MED-03: /api/chat/stream SSE / CORS
    # ------------------------------------------------------------------------

    def test_09_stream_cors_header_no_wildcard(self):
        """Stream endpoint must not send Access-Control-Allow-Origin: * header."""
        server_code = Path("server.py").read_text(encoding="utf-8")
        self.assertNotIn('send_header("Access-Control-Allow-Origin", "*")', server_code)

    # ------------------------------------------------------------------------
    # MED-04: Secret Masking Fallback
    # ------------------------------------------------------------------------

    def test_10_mask_secrets_fallback_to_get_config(self):
        """mask_secrets(text) without passing cfg must fallback to get_config() and mask live keys."""
        test_key = "sk-live-test-secret-12345678"
        mock_cfg = {"api_key": test_key}

        with patch("server.get_config", return_value=mock_cfg):
            raw_text = f"The client initialized with {test_key} and Authorization: Bearer {test_key}"
            # Call WITHOUT passing cfg parameter
            masked = server.mask_secrets(raw_text)
            self.assertNotIn(test_key, masked)
            self.assertIn("[REDACTED:key]", masked)

    def test_11_zip_trailing_dot_space_and_ntfs_streams_refused(self):
        """Trailing dot/space names, ':' streams, and '::$DATA' must be rejected."""
        bad_names = [
            "repo-main/file.txt.",
            "repo-main/file.txt ",
            "repo-main/dir. /ok.txt",
            "repo-main/file.txt:hidden",
            "repo-main/file.txt::$DATA",
        ]
        for bad in bad_names:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr(bad, b"payload")
            buf.seek(0)
            with tempfile.TemporaryDirectory() as td:
                with self.assertRaises(ValueError, msg=f"Must reject {bad}"):
                    safe_extract_zip(buf, Path(td))

    def test_12_zip_extracted_files_marked_tainted(self):
        """Every file extracted by safe_extract_zip must be marked tainted via mark_file_tainted."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("repo-main/README.md", b"# Hello")
            zf.writestr("repo-main/src/app.py", b"print('hi')")
        buf.seek(0)
        with tempfile.TemporaryDirectory() as td:
            extracted = safe_extract_zip(buf, Path(td))
            self.assertEqual(len(extracted), 2)
            for fpath in extracted:
                is_tainted, _ = server.is_file_tainted_provenance(str(fpath))
                self.assertTrue(is_tainted, f"Extracted file {fpath} must be marked tainted")


if __name__ == "__main__":
    unittest.main()
