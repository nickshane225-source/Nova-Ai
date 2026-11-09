#!/usr/bin/env python3
"""
Unit and regression tests for Part C: Search Exfiltration Prevention.
Tests:
1. In sticky-tainted conversation, every SEARCH requires confirmation (<= 80 char exemption removed).
2. Tainted tests: 18-char hyphen-segmented secrets, unpadded 20-23 char tokens, and space-split secrets.
3. Untainted turns: safe queries pass, while entropy detector and tainted-file text detection act as backstops.
4. Per-conversation 5-search limit.
"""

import unittest
from unittest.mock import patch

import server


class TestSearchExfiltration(unittest.TestCase):
    def setUp(self):
        server.CONVERSATION_SEARCH_COUNTS.clear()

    def tearDown(self):
        server.CONVERSATION_SEARCH_COUNTS.clear()

    def test_tainted_search_every_query_requires_confirmation(self):
        """In sticky-tainted conversation, EVERY search requires confirmation regardless of length or shape."""
        cfg = {}

        # 1. 18-char hyphen-segmented secret
        hyphen_secret_18 = "sec-ret-12-34-56-a"
        self.assertEqual(len(hyphen_secret_18), 18)
        req, reason = server.check_tool_confirmation_required(
            cfg, "SEARCH", hyphen_secret_18, is_tainted=True, source="pc"
        )
        self.assertTrue(req)
        self.assertIn("requires user approval", reason)

        # 2. Unpadded 20-23 char tokens
        token_20 = "unpaddedtoken1234567"
        self.assertEqual(len(token_20), 20)
        req, reason = server.check_tool_confirmation_required(
            cfg, "SEARCH", token_20, is_tainted=True, source="pc"
        )
        self.assertTrue(req)

        token_23 = "unpaddedtoken1234567890"
        self.assertEqual(len(token_23), 23)
        req, reason = server.check_tool_confirmation_required(
            cfg, "SEARCH", token_23, is_tainted=True, source="pc"
        )
        self.assertTrue(req)

        # 3. Space-split secrets
        space_secret = "my secret token val 123"
        req, reason = server.check_tool_confirmation_required(
            cfg, "SEARCH", space_secret, is_tainted=True, source="pc"
        )
        self.assertTrue(req)

        # 4. Shortest possible queries (< 10 chars)
        for short_q in ("hi", "cat", "weather", "help"):
            req, reason = server.check_tool_confirmation_required(
                cfg, "SEARCH", short_q, is_tainted=True, source="pc"
            )
            self.assertTrue(req, f"Short query '{short_q}' must require confirmation in tainted turn")

    def test_untainted_search_allows_safe_queries(self):
        """In untainted PC conversation, safe queries do not require confirmation."""
        cfg = {}
        safe_queries = [
            "python list comprehension guide",
            "weather in Seattle",
            "how to parse json in python standard library",
            "documentation for http.server",
        ]
        for q in safe_queries:
            req, reason = server.check_tool_confirmation_required(
                cfg, "SEARCH", q, is_tainted=False, source="pc", conv_id="pc:safe_test"
            )
            self.assertFalse(req, f"Safe query '{q}' should not require confirmation: {reason}")

    def test_untainted_search_entropy_detector_backstop(self):
        """In untainted turns, high-entropy base64/hex token detector acts as backstop against secret exfiltration."""
        cfg = {}
        high_entropy_tokens = [
            "d41d8cd98f00b204e9800998ecf8427e",  # MD5 hex 32 chars
            "4f8b2c1e9a3d7f0b5c2e8a1d4f9b3c7e",  # 32 hex
            "a8f7c3b2e1d09a8b7c6d5e4f3a2b1c0d",  # 32 hex
            "c2VjcmV0X2FwaV9rZXlfMTIzNDU2Nzg5MA==", # base64
        ]
        for token in high_entropy_tokens:
            query = f"lookup {token} details"
            req, reason = server.check_tool_confirmation_required(
                cfg, "SEARCH", query, is_tainted=False, source="pc", conv_id="pc:entropy_test"
            )
            self.assertTrue(req, f"High-entropy token query '{query}' must trigger backstop confirmation")
            self.assertIn("base64/hex-like token", reason)

    def test_untainted_search_tainted_file_text_backstop(self):
        """In untainted turns, query referencing content from a tainted file requires confirmation."""
        cfg = {}
        with patch("server.is_text_from_tainted_file", return_value=True):
            req, reason = server.check_tool_confirmation_required(
                cfg, "SEARCH", "extracted leaked content from file", is_tainted=False, source="pc", conv_id="pc:tainted_file_test"
            )
            self.assertTrue(req)
            self.assertIn("tainted file", reason)

    def test_untainted_search_cap_after_5_queries(self):
        """Max 5 unconfirmed searches per conversation before gating kicks in."""
        cfg = {}
        conv = "pc:count_test"
        for i in range(5):
            req, reason = server.check_tool_confirmation_required(
                cfg, "SEARCH", f"safe query number {i}", is_tainted=False, source="pc", conv_id=conv
            )
            self.assertFalse(req)
            # Record count
            server.CONVERSATION_SEARCH_COUNTS[conv] = server.CONVERSATION_SEARCH_COUNTS.get(conv, 0) + 1

        # 6th query must require confirmation
        req6, reason6 = server.check_tool_confirmation_required(
            cfg, "SEARCH", "safe query number 6", is_tainted=False, source="pc", conv_id=conv
        )
        self.assertTrue(req6)
        self.assertIn("Maximum of 5 unconfirmed searches reached", reason6)


if __name__ == "__main__":
    unittest.main()
