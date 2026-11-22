import unittest

import guardian_agent


class TestMed13GuardianRails(unittest.TestCase):
    def test_destructive_commands_must_stay_dangerous(self):
        dangerous_cmds = [
            "format c:",
            "Format-Volume -DriveLetter C",
            "Clear-Disk -Number 0 -RemoveData",
            "diskpart",
            "Remove-Item -Recurse -Force $HOME",
            "vssadmin delete shadows /all /quiet",
            r"reg delete HKCU\Software /f",
        ]
        for cmd in dangerous_cmds:
            is_dang, reason = guardian_agent._is_local_rail_dangerous(cmd)
            self.assertTrue(is_dang, f"Expected DANGEROUS for command: {cmd}")
            verdict, _ = guardian_agent.review_command_safety({}, "POWERSHELL", cmd)
            self.assertEqual(verdict, guardian_agent.VERDICT_DANGEROUS, f"review_action must return DANGEROUS for: {cmd}")

    def test_format_table_not_flagged_by_local_destructive_rail(self):
        is_dang, reason = guardian_agent._is_local_rail_dangerous("Get-Process | Format-Table -AutoSize")
        self.assertFalse(is_dang, f"Format-Table must not be flagged as destructive by local rail (got: {reason})")


if __name__ == "__main__":
    unittest.main()
