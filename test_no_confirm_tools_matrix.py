"""
test_no_confirm_tools_matrix.py - Comprehensive test matrix verifying tool confirmation gating.

Generates a test matrix across:
Every tool in NO_CONFIRM_TOOLS + NETWORK_CAPABLE_TOOLS
x {clean, tainted}
x {pc, telegram, discord, scheduler}

Ensures:
- Every network-capable tool requires confirmation when tainted (fail-closed).
- Every network-capable tool requires confirmation in non-PC channels (fail-closed).
"""

import unittest
import server


class TestNoConfirmToolsMatrix(unittest.TestCase):
    def setUp(self):
        self.cfg = {"confirm_destructive": True}

    def test_matrix_network_tools_require_confirmation_when_tainted(self):
        """Matrix test: EVERY network-capable tool MUST require confirmation when tainted across all channels."""
        all_tools = sorted(list(server.NO_CONFIRM_TOOLS | server.NETWORK_CAPABLE_TOOLS))
        channels = ["pc", "telegram", "discord", "scheduler"]

        for tool in all_tools:
            is_net = (tool in server.NETWORK_CAPABLE_TOOLS)
            for channel in channels:
                # 1. Tainted state
                req_tainted, reason_tainted = server.check_tool_confirmation_required(
                    self.cfg,
                    tool,
                    arg="sample_arg",
                    is_tainted=True,
                    source=channel,
                )
                if is_net:
                    self.assertTrue(
                        req_tainted,
                        f"SECURITY VIOLATION: Network-capable tool '{tool}' auto-ran in tainted turn on channel '{channel}'! Reason: {reason_tainted}"
                    )

                # 2. Clean state in remote / non-PC channels
                if channel != "pc":
                    req_remote, reason_remote = server.check_tool_confirmation_required(
                        self.cfg,
                        tool,
                        arg="sample_arg",
                        is_tainted=False,
                        source=channel,
                    )
                    if is_net:
                        self.assertTrue(
                            req_remote,
                            f"SECURITY VIOLATION: Network-capable tool '{tool}' auto-ran on non-PC channel '{channel}'! Reason: {reason_remote}"
                        )

    def test_clean_pc_safe_tools_can_autorun(self):
        """Verifies that non-network read-only workspace tools auto-run on untainted PC."""
        safe_pc_tools = ["LIST_FILES", "ACTIVE_WINDOW", "GET_WINDOW"]
        for tool in safe_pc_tools:
            req, _ = server.check_tool_confirmation_required(
                self.cfg,
                tool,
                arg="test.txt",
                is_tainted=False,
                source="pc",
            )
            self.assertFalse(req, f"Expected safe PC tool '{tool}' to auto-run in clean state")

    def test_read_page_page_content_browser_page_fetch_gated_when_tainted(self):
        """Explicit assertion that READ_PAGE, PAGE_CONTENT, BROWSER_PAGE, and FETCH* require confirmation when tainted."""
        target_tools = ["READ_PAGE", "PAGE_CONTENT", "BROWSER_PAGE", "FETCH", "FETCH_URL", "READ_URL"]
        for tool in target_tools:
            req, msg = server.check_tool_confirmation_required(
                self.cfg,
                tool,
                arg="http://example.com",
                is_tainted=True,
                source="pc",
            )
            self.assertTrue(req, f"Tool '{tool}' must require confirmation when tainted")
            self.assertIn("requires user approval", msg)


if __name__ == "__main__":
    unittest.main()
