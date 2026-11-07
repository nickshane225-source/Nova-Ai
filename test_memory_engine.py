"""
Unit tests for memory_engine.py (SQLite Second Brain & Semantic Search).
"""
import unittest
import tempfile
import os
from pathlib import Path
import memory_engine

class TestMemoryEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        memory_engine.init_db(self.db_path)

    def tearDown(self):
        if self.db_path.exists():
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_save_and_retrieve_note(self):
        note_id = memory_engine.save_note(
            "Project Architecture",
            "Nova AI uses pure python standard library and CDP protocol.",
            category="work",
            db_path=self.db_path
        )
        self.assertIsInstance(note_id, int)
        note = memory_engine.get_note("Project Architecture", db_path=self.db_path)
        self.assertIsNotNone(note)
        self.assertEqual(note["title"], "Project Architecture")
        self.assertIn("CDP protocol", note["content"])

    def test_semantic_search_notes(self):
        memory_engine.save_note("Database Choices", "We chose SQLite because it needs no installation.", category="tech", db_path=self.db_path)
        memory_engine.save_note("Frontend Styling", "We use CSS variables for theme switching.", category="design", db_path=self.db_path)
        memory_engine.save_note("Voice Engine", "Web Speech API is used for browser voice recognition.", category="voice", db_path=self.db_path)

        results = memory_engine.search_notes("sqlite database", db_path=self.db_path)
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]["title"], "Database Choices")

    def test_delete_note(self):
        memory_engine.save_note("Temporary", "To be deleted", category="temp", db_path=self.db_path)
        ok = memory_engine.delete_note("Temporary", db_path=self.db_path)
        self.assertTrue(ok)
        note = memory_engine.get_note("Temporary", db_path=self.db_path)
        self.assertIsNone(note)

if __name__ == "__main__":
    unittest.main()
