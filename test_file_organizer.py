"""
Unit tests for Smart Downloads & Folder Auto-Organizer skill in server.py
"""
import unittest
import tempfile
import shutil
from pathlib import Path
import server

class TestFileOrganizer(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.test_dir.name)
        # Create test files
        (self.folder / "document.pdf").write_text("dummy doc")
        (self.folder / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (self.folder / "script.py").write_text("print('test')")
        (self.folder / "archive.zip").write_bytes(b"PK\x03\x04")
        (self.folder / "song.mp3").write_bytes(b"ID3")

    def tearDown(self):
        self.test_dir.cleanup()

    def test_organize_custom_folder(self):
        res = server.run_skill({}, "ORGANIZE", str(self.folder))
        self.assertIn("Organized", res)
        self.assertTrue((self.folder / "Documents" / "document.pdf").exists())
        self.assertTrue((self.folder / "Images" / "photo.png").exists())
        self.assertTrue((self.folder / "Code" / "script.py").exists())
        self.assertTrue((self.folder / "Archives" / "archive.zip").exists())
        self.assertTrue((self.folder / "Media" / "song.mp3").exists())

    def test_organize_already_clean_folder(self):
        # Organize once
        server.run_skill({}, "ORGANIZE", str(self.folder))
        # Organize second time
        res2 = server.run_skill({}, "ORGANIZE", str(self.folder))
        self.assertIn("already well organized", res2)

if __name__ == "__main__":
    unittest.main()
