"""
Unit tests for self-healing code execution and surgical edit skills in server.py
"""
import unittest
import tempfile
import os
from pathlib import Path
import server

class TestAgentHealing(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.workspace_orig = server.WORKSPACE
        server.WORKSPACE = Path(self.test_dir.name)

    def tearDown(self):
        server.WORKSPACE = self.workspace_orig
        self.test_dir.cleanup()

    def test_skill_write_and_edit_file(self):
        # 1. Write file
        res = server.run_skill({}, "WRITE_FILE", "math_test.py | def add(a, b):\n    return a - b\n")
        self.assertIn("Created file", res)

        # 2. Verify file content
        read_res = server.run_skill({}, "READ_FILE", "math_test.py")
        self.assertIn("return a - b", read_res)

        # 3. Surgical EDIT_FILE
        edit_res = server.run_skill({}, "EDIT_FILE", "math_test.py | return a - b | return a + b")
        self.assertIn("Successfully edited", edit_res)

        # 4. Verify updated content
        read_res2 = server.run_skill({}, "READ_FILE", "math_test.py")
        self.assertIn("return a + b", read_res2)
        self.assertNotIn("return a - b", read_res2)

    def test_create_project_scaffold(self):
        res = server.run_skill({}, "CREATE_PROJECT", "html-app | my-site")
        self.assertIn("Created project", res)
        self.assertTrue((server.WORKSPACE / "my-site" / "index.html").exists())
        self.assertTrue((server.WORKSPACE / "my-site" / "style.css").exists())

    def test_extract_tags_nested_brackets(self):
        raw = "Check this: [[WRITE_FILE: test.py | matrix = [[1, 2], [3, 4]]\nprint(matrix)]] and [[SCREENSHOT]]"
        tags = server.extract_tags(raw)
        self.assertEqual(len(tags), 2)
        self.assertEqual(tags[0][0], "WRITE_FILE")
        self.assertIn("[[1, 2], [3, 4]]", tags[0][1])
        self.assertEqual(tags[1][0], "SCREENSHOT")
        
        stripped = server.strip_tags(raw)
        self.assertEqual(stripped, "Check this:  and")

    def test_write_file_escaped_newlines(self):
        res = server.run_skill({}, "WRITE_FILE", "unescape_test.py | # Module\\nprint('hello')\\n")
        self.assertIn("Created file", res)
        read_res = server.run_skill({}, "READ_FILE", "unescape_test.py")
        self.assertIn("print('hello')", read_res)
        self.assertEqual(len(read_res.splitlines()), 3)  # header + 2 lines

    def test_remind_single_argument_parsing(self):
        res = server.run_skill({}, "REMIND", "Call Mom")
        self.assertIn("Call Mom", res)
        self.assertIn("5m", res)

if __name__ == "__main__":
    unittest.main()
