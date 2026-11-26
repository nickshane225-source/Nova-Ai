import unittest
import server


class TestTokenEntropy(unittest.TestCase):
    def test_has_base64_hex_token_negatives(self):
        """Natural identifiers and project paths must not be flagged as tokens."""
        negatives = [
            "get_user_authentication_token_v2",
            "workspace/project-2024/report-final",
            "internationalization-and-localization-2024",
            "get_user_authentication_token",
            "internationalization-and-localization",
            "cat /path/to/workspace/project-2024/report-final.txt",
            "def get_user_authentication_token_v2(arg):",
        ]
        for s in negatives:
            self.assertFalse(
                server.has_base64_hex_token(s),
                f"Negative example '{s}' should NOT match token detector"
            )

    def test_has_base64_hex_token_positives(self):
        """Real base64, hex tokens, and random high-entropy tokens must be flagged."""
        positives = [
            # Base64 with padding
            "ZXhhbXBsZXNlY3JldGtleTEyMzQ=",
            # 32-character hex string
            "0123456789abcdef0123456789abcdef",
            "4a5b6c7d8e9f0123456789abcdef0123",
            # Random 40-character mixed-case string
            "aB9xK2mP8qRtL5vW3yZaB7cDeF0gHiJ1kLmN4oPq",
            # Embedded in command/context
            "Authorization: Bearer ZXhhbXBsZXNlY3JldGtleTEyMzQ=",
            "SECRET=0123456789abcdef0123456789abcdef",
            "key = 'aB9xK2mP8qRtL5vW3yZaB7cDeF0gHiJ1kLmN4oPq'",
        ]
        for s in positives:
            self.assertTrue(
                server.has_base64_hex_token(s),
                f"Positive example '{s}' MUST match token detector"
            )


if __name__ == "__main__":
    unittest.main()
