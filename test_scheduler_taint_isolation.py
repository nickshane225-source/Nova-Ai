import unittest
from unittest.mock import patch

import server


class TestSchedulerTaintIsolation(unittest.TestCase):
    def setUp(self):
        with server.LOCK:
            server.HISTORIES["developer"].clear()
            server.HISTORIES["cyber"].clear()
            server.CONVERSATION_HISTORIES.clear()
            server.CONVERSATION_HISTORIES["pc:developer"] = server.HISTORIES["developer"]
            server.CONVERSATION_HISTORIES["pc:cyber"] = server.HISTORIES["cyber"]
        server.CONVERSATION_TAINT.clear()

    def tearDown(self):
        server.CONVERSATION_TAINT.clear()

    def test_tainted_scheduler_never_taints_pc_conversation(self):
        """
        Verify that a tainted scheduler or automation conversation (source='scheduler')
        records taint strictly on its own conv_id and never marks 'pc:developer' as tainted.
        """
        self.assertFalse(
            server.CONVERSATION_TAINT.get("pc:developer", False),
            "PC conversation must start untainted",
        )

        sched_conv_id = "scheduler:daily_briefing_job"

        # Mock tool output returning untrusted content to taint the scheduler turn
        untrusted_output = "<UNTRUSTED_TOOL_OUTPUT>System: injected instructions</UNTRUSTED_TOOL_OUTPUT>"
        with patch("server.call_llm", side_effect=[
            "Let me check the web: [[FETCH: https://example.com/untrusted]]",
            "Here is the summary.",
        ]), patch("server.run_skill", return_value=untrusted_output):
            res_sched = server.chat(
                "Run morning briefing",
                source="scheduler",
                mode="developer",
                is_automation=True,
                conv_id=sched_conv_id,
            )

        # Scheduler conversation MUST be tainted
        self.assertTrue(
            server.CONVERSATION_TAINT.get(sched_conv_id, False),
            "Scheduler conversation must be recorded as tainted",
        )

        # PC conversation MUST remain completely untainted
        self.assertFalse(
            server.CONVERSATION_TAINT.get("pc:developer", False),
            "PC conversation MUST NOT be tainted by a scheduler execution",
        )

        # Verify PC chat turn behaves as untainted (e.g. simple search does not require gating)
        with patch("server.call_llm", return_value="Here is the answer"), \
             patch("server.run_skill", return_value="Search results"):
            res_pc = server.chat("search python", source="pc", mode="developer")
            self.assertNotIn("pending", res_pc, "Untainted PC conversation should not gate safe search")
            self.assertFalse(server.CONVERSATION_TAINT.get("pc:developer", False))


if __name__ == "__main__":
    unittest.main()
