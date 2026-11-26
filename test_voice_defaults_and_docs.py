import unittest
from pathlib import Path

import server


class TestVoiceDefaultsAndDocs(unittest.TestCase):
    def test_wake_word_default_off(self):
        self.assertIs(server.DEFAULT_CONFIG.get("wake_word_enabled"), False)

    def test_docs_disclose_cloud_speech_and_wake_word(self):
        root = Path(__file__).resolve().parent
        readme = (root / "README.md").read_text(encoding="utf-8")
        sec_notes = (root / "docs" / "SECURITY_NOTES.md").read_text(encoding="utf-8")

        self.assertNotIn("Zero Telemetry:", readme)
        self.assertIn("cloud speech", readme.lower())
        self.assertIn("audio leaves", readme.lower())
        self.assertIn("opt-in", readme.lower())
        self.assertIn("push-to-talk", readme.lower())

        self.assertIn("cloud speech", sec_notes.lower())
        self.assertIn("audio leaves", sec_notes.lower())
        self.assertIn("listens continuously", sec_notes.lower())
        self.assertIn("push-to-talk", sec_notes.lower())


if __name__ == "__main__":
    unittest.main()
