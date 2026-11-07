"""
Unit tests for scheduler_engine.py
"""
import unittest
import time
from pathlib import Path
import scheduler_engine

class TestSchedulerEngine(unittest.TestCase):
    def test_parse_delay_seconds(self):
        self.assertEqual(scheduler_engine.parse_time_spec("30s"), 30)
        self.assertEqual(scheduler_engine.parse_time_spec("5m"), 300)
        self.assertEqual(scheduler_engine.parse_time_spec("2h"), 7200)
        self.assertEqual(scheduler_engine.parse_time_spec("10 minutes"), 600)
        self.assertEqual(scheduler_engine.parse_time_spec("1 hour"), 3600)

    def test_create_and_trigger_timer(self):
        scheduler = scheduler_engine.SchedulerEngine()
        timer_id = scheduler.add_timer("1s", "Quick test timer")
        self.assertIsNotNone(timer_id)
        
        # Wait 1.3 seconds
        time.sleep(1.3)
        scheduler.check_timers()
        
        notifs = scheduler.get_pending_notifications()
        self.assertTrue(len(notifs) >= 1)
        self.assertIn("Quick test timer", notifs[0]["message"])

    def test_recurring_automation(self):
        scheduler = scheduler_engine.SchedulerEngine()
        auto_id = scheduler.add_recurring_task("every 1s", "SYSTEM: stats", "System Check")
        self.assertIsNotNone(auto_id)
        recs = scheduler.list_recurring()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["label"], "System Check")

        # Wait and check trigger
        time.sleep(1.2)
        scheduler.check_timers()
        notifs = scheduler.get_pending_notifications()
        self.assertTrue(any("System Check" in n.get("message", "") for n in notifs))

        # Cancel
        scheduler.cancel_recurring(auto_id)
        self.assertEqual(len(scheduler.list_recurring()), 0)

if __name__ == "__main__":
    unittest.main()
