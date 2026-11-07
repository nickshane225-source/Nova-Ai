"""
Unit tests for Phase 3: Devanagari tokenization and true BM25 Robertson-Spärck Jones IDF.
Zero pip dependencies - Python standard library only.
"""
import unittest
import tempfile
from pathlib import Path

import memory_engine
import skills_engine

class TestPhase3Search(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.test_db = Path(self.tmp_dir.name) / "test_brain.db"
        memory_engine.init_db(self.test_db)

    def tearDown(self):
        self.tmp_dir.cleanup()

    # --- 3A. DEVANAGARI TOKENIZER ---
    def test_devanagari_tokenization(self):
        hindi_text = "नमस्ते दुनिया यह एक सुरक्षा परीक्षण है"
        tokens = memory_engine._tokenize(hindi_text)
        self.assertIn("नमस्ते", tokens)
        self.assertIn("दुनिया", tokens)
        self.assertIn("सुरक्षा", tokens)
        self.assertIn("परीक्षण", tokens)

    def test_hindi_note_save_and_search(self):
        memory_engine.save_note("हिंदी नोट्स", "यह नोवा एआई के लिए एक विशेष हिंदी दस्तावेज है।", db_path=self.test_db)
        memory_engine.save_note("अंग्रेजी नोट", "This is an unrelated English document.", db_path=self.test_db)

        results = memory_engine.search_notes("हिंदी दस्तावेज", db_path=self.test_db)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "हिंदी नोट्स")

    # --- 3B. TRUE BM25 IDF WEIGHTING ---
    def test_rare_term_ranks_higher_than_common_term(self):
        # Doc 1 to 5 all contain 'project' (common)
        # Only Doc 1 contains 'quantum_breakthrough' (rare)
        # Doc 2 has 'project' repeated 10 times to boost its term frequency
        memory_engine.save_note("Doc 1", "This project covers a quantum_breakthrough in physics.", db_path=self.test_db)
        memory_engine.save_note("Doc 2", "project " * 10, db_path=self.test_db)
        memory_engine.save_note("Doc 3", "General project report alpha.", db_path=self.test_db)
        memory_engine.save_note("Doc 4", "General project report beta.", db_path=self.test_db)
        memory_engine.save_note("Doc 5", "General project report gamma.", db_path=self.test_db)

        # Query for both common and rare term
        results = memory_engine.search_notes("project quantum_breakthrough", db_path=self.test_db)
        self.assertGreaterEqual(len(results), 1)
        # Doc 1 must be ranked first because quantum_breakthrough has high IDF
        self.assertEqual(results[0]["title"], "Doc 1")
        self.assertGreater(results[0]["score"], results[1]["score"])

if __name__ == "__main__":
    unittest.main()
