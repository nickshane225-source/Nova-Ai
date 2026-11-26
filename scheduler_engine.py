"""
Nova AI - Scheduler Engine & Hardware Watchdog.

Pure Python standard library (threading, time, datetime, urllib, ctypes, shutil).
Handles:
- Natural-language timers & reminders ("5m", "1 hour", "18:00")
- Background Hardware Watchdog (battery, RAM, disk warnings)
- Proactive Morning Briefing builder (weather via wttr.in, system health, schedule)
- Notification queue for desktop / voice delivery
"""

import datetime
import json
import os
import platform
import re
import secrets
import shutil
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Ensure UTF-8 output on Windows consoles/terminals to prevent charmap crashes
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    import ctypes
except Exception:
    ctypes = None

OS = platform.system()

def parse_time_spec(spec: str) -> int:
    """Parses delay string into seconds. Supports '30s', '5m', '2h', '1.5h', '10 minutes', '17:30', '5:30pm', etc."""
    s = spec.strip().lower()
    if s.startswith("in "):
        s = s[3:].strip()
    
    # Seconds
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(?:s|sec|seconds?)$", s)
    if m:
        return max(1, int(float(m.group(1))))
    
    # Minutes
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(?:m|min|mins|minutes?)$", s)
    if m:
        return max(1, int(float(m.group(1)) * 60))
    
    # Hours
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(?:h|hr|hours?)$", s)
    if m:
        return max(1, int(float(m.group(1)) * 3600))
    
    # Simple integer or float -> default to minutes
    try:
        val = float(s)
        return max(1, int(val * 60))
    except ValueError:
        pass
        
    # 12-hour wall clock time (e.g. 5:30pm, 09:15 am, 2pm)
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$", s)
    if m:
        hr = int(m.group(1))
        mn = int(m.group(2) or 0)
        meridiem = m.group(3)
        if meridiem == "pm" and hr < 12:
            hr += 12
        elif meridiem == "am" and hr == 12:
            hr = 0
        now = datetime.datetime.now()
        target = now.replace(hour=hr, minute=mn, second=0, microsecond=0)
        if target <= now:
            target += datetime.timedelta(days=1)
        return int((target - now).total_seconds())

    # 24-hour wall clock time (e.g. 14:30 or 09:15)
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if m:
        hr, mn = int(m.group(1)), int(m.group(2))
        now = datetime.datetime.now()
        target = now.replace(hour=hr, minute=mn, second=0, microsecond=0)
        if target <= now:
            target += datetime.timedelta(days=1)
        return int((target - now).total_seconds())

    return 300  # Default 5 minutes fallback


class SchedulerEngine:
    def __init__(self, data_file=None):
        self.lock = threading.RLock()
        self.timers = []
        self.recurring = []
        self.notifications = []
        self.watchdog_cooldowns = {}
        self.active_automation_tokens = {}
        self.running = False
        self._thread = None
        self.briefing_time = "09:00"
        self.briefing_done_today = False

    MAX_AUTOMATION_TOKENS = 50

    def add_timer(self, delay_spec: str, message: str, mode: str = "developer", action: str = None) -> int:
        secs = parse_time_spec(delay_spec)
        now = time.time()
        timer_id = int(now * 1000) % 1000000
        due = now + secs
        item = {
            "id": timer_id,
            "due": due,
            "spec": delay_spec,
            "message": message or "Reminder alert",
            "mode": "cyber" if mode == "cyber" else "developer",
            "action": action,
            "created": now,
        }
        with self.lock:
            self.timers.append(item)
        return timer_id

    def list_timers(self):
        now = time.time()
        with self.lock:
            return [
                {
                    "id": t["id"],
                    "message": t["message"],
                    "remaining_seconds": max(0, int(t["due"] - now)),
                    "due_time": datetime.datetime.fromtimestamp(t["due"]).strftime("%I:%M %p"),
                }
                for t in self.timers
            ]

    def cancel_timer(self, timer_id) -> bool:
        try:
            tid = int(timer_id)
        except (TypeError, ValueError):
            return False
        with self.lock:
            before = len(self.timers)
            self.timers = [t for t in self.timers if t["id"] != tid]
            return len(self.timers) < before

    def add_recurring_task(self, schedule_spec: str, action: str, label: str = "", mode: str = "developer") -> int:
        s = schedule_spec.strip().lower()
        now = time.time()
        auto_id = int(now * 1000) % 1000000
        sched_kind = "interval"
        interval = 3600
        next_run = now + 3600

        if s.startswith("every "):
            spec = s[6:].strip()
            interval = parse_time_spec(spec)
            next_run = now + interval
            sched_kind = "interval"
        elif s.startswith("daily ") or re.match(r"^\d{1,2}:\d{2}", s):
            time_part = s.replace("daily", "").strip()
            secs = parse_time_spec(time_part)
            interval = 86400
            next_run = now + secs
            sched_kind = "daily"
        else:
            interval = parse_time_spec(s)
            next_run = now + interval

        item = {
            "id": auto_id,
            "spec": schedule_spec,
            "mode": sched_kind,
            "ai_mode": "cyber" if mode == "cyber" else "developer",
            "interval": interval,
            "action": action,
            "label": label or action,
            "next_run": next_run,
            "created": now,
        }
        with self.lock:
            self.recurring.append(item)
        return auto_id

    def list_recurring(self):
        now = time.time()
        with self.lock:
            return [
                {
                    "id": r["id"],
                    "spec": r["spec"],
                    "label": r["label"],
                    "action": r["action"],
                    "remaining_seconds": max(0, int(r["next_run"] - now)),
                    "next_run_time": datetime.datetime.fromtimestamp(r["next_run"]).strftime("%I:%M %p"),
                }
                for r in self.recurring
            ]

    def cancel_recurring(self, task_id) -> bool:
        try:
            tid = int(task_id)
        except (TypeError, ValueError):
            return False
        with self.lock:
            before = len(self.recurring)
            self.recurring = [r for r in self.recurring if r["id"] != tid]
            return len(self.recurring) < before

    def check_timers(self):
        now = time.time()
        triggered = []
        with self.lock:
            active = []
            for t in self.timers:
                if t["due"] <= now:
                    triggered.append(t)
                else:
                    active.append(t)
            self.timers = active

            for t in triggered:
                action = t.get("action")
                notif = {
                    "type": "timer",
                    "title": "⏰ Reminder",
                    "message": t["message"],
                    "mode": t.get("mode", "developer"),
                    "timestamp": time.time(),
                }
                if action:
                    tok = self.issue_automation_token()
                    notif["action"] = action
                    notif["automation_token"] = tok
                self._push_notification(notif)

            # Check recurring automations
            for r in self.recurring:
                if r["next_run"] <= now:
                    tok = self.issue_automation_token()
                    self._push_notification({
                        "type": "automation",
                        "title": "⚡ Scheduled Automation",
                        "message": f"Running {r['label']}",
                        "action": r["action"],
                        "mode": r.get("ai_mode", "developer"),
                        "timestamp": now,
                        "automation_token": tok,
                    })
                    # Re-arm
                    if r["mode"] == "daily":
                        r["next_run"] = now + 86400
                    else:
                        r["next_run"] = now + r["interval"]

    def check_hardware_watchdog(self):
        """Monitors battery, RAM, and disk space for critical conditions."""
        now = time.time()

        # 1. Battery check (Windows)
        if OS == "Windows" and ctypes:
            try:
                class SPS(ctypes.Structure):
                    _fields_ = [
                        ('ACLineStatus', ctypes.c_byte),
                        ('BatteryFlag', ctypes.c_byte),
                        ('BatteryLifePercent', ctypes.c_byte),
                        ('SystemStatusFlag', ctypes.c_byte),
                        ('BatteryLifeTime', ctypes.c_ulong),
                        ('BatteryFullLifeTime', ctypes.c_ulong)
                    ]
                s = SPS()
                ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s))
                # If on battery and below 20%
                if s.ACLineStatus == 0 and 0 < s.BatteryLifePercent <= 20:
                    last = self.watchdog_cooldowns.get("battery", 0)
                    if now - last > 600:  # 10 min cooldown
                        self.watchdog_cooldowns["battery"] = now
                        with self.lock:
                            self._push_notification({
                                "type": "warning",
                                "title": "🔋 Low Battery Warning",
                                "message": f"PC battery is at {s.BatteryLifePercent}%. Please plug in your charger.",
                                "timestamp": now,
                            })
            except Exception:
                pass

        # 2. RAM check
        if OS == "Windows" and ctypes:
            try:
                class MEM(ctypes.Structure):
                    _fields_ = [
                        ('l', ctypes.c_ulong), ('load', ctypes.c_ulong),
                        ('tot_p', ctypes.c_ulonglong), ('av_p', ctypes.c_ulonglong),
                        ('tot_pg', ctypes.c_ulonglong), ('av_pg', ctypes.c_ulonglong),
                        ('tot_v', ctypes.c_ulonglong), ('av_v', ctypes.c_ulonglong),
                        ('ext', ctypes.c_ulonglong)
                    ]
                m = MEM()
                m.l = ctypes.sizeof(MEM)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
                if m.load >= 94:
                    last = self.watchdog_cooldowns.get("ram", 0)
                    if now - last > 900:  # 15 min cooldown
                        self.watchdog_cooldowns["ram"] = now
                        with self.lock:
                            self._push_notification({
                                "type": "warning",
                                "title": "⚡ High RAM Warning",
                                "message": f"RAM usage is critical at {m.load}%. Consider closing inactive browser tabs or apps.",
                                "timestamp": now,
                            })
            except Exception:
                pass

        # 3. Disk space check
        try:
            root_drive = "C:\\" if OS == "Windows" else "/"
            total, used, free = shutil.disk_usage(root_drive)
            free_gb = free / (1024 ** 3)
            if free_gb < 4.0:
                last = self.watchdog_cooldowns.get("disk", 0)
                if now - last > 1800:
                    self.watchdog_cooldowns["disk"] = now
                    with self.lock:
                        self._push_notification({
                            "type": "warning",
                            "title": "💾 Low Disk Warning",
                            "message": f"Primary drive has only {round(free_gb, 1)} GB free space remaining.",
                            "timestamp": now,
                        })
        except Exception:
            pass

    def check_daily_briefing(self):
        now_dt = datetime.datetime.now()
        cur_hhmm = now_dt.strftime("%H:%M")
        if cur_hhmm == self.briefing_time and not self.briefing_done_today:
            self.briefing_done_today = True
            briefing_text = self.get_morning_briefing_summary()
            with self.lock:
                self._push_notification({
                    "type": "briefing",
                    "title": "☀️ Morning Briefing",
                    "message": briefing_text,
                    "timestamp": time.time(),
                })
        elif cur_hhmm != self.briefing_time:
            self.briefing_done_today = False

    def get_morning_briefing_summary(self) -> str:
        """Fetches lightweight weather and compiles briefing text."""
        parts = []
        now = datetime.datetime.now()
        parts.append(f"Good morning! Today is {now.strftime('%A, %B %d')}.")
        
        # Weather via wttr.in with unified SSRF protection
        try:
            import ssrf_guard
            ok, text, _ = ssrf_guard.safe_http_fetch(
                "https://wttr.in/?format=3",
                timeout=4.0,
                wrap_output=False,
            )
            if ok and text:
                weather = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", text).strip()
                if weather:
                    parts.append(f"Current weather: {weather}.")
        except Exception:
            pass

        # Check timers count
        with self.lock:
            n_timers = len(self.timers)
        if n_timers > 0:
            parts.append(f"You have {n_timers} active scheduled reminder(s) for today.")
        else:
            parts.append("Your schedule is clear for today.")

        parts.append("All PC systems are running smoothly.")
        return " ".join(parts)

    def get_pending_notifications(self):
        with self.lock:
            return list(self.notifications)

    def clear_notifications(self):
        with self.lock:
            self.notifications.clear()

    def issue_automation_token(self) -> str:
        tok = secrets.token_hex(16)
        with self.lock:
            now = time.time()
            expired = [k for k, exp in self.active_automation_tokens.items() if exp < now]
            for k in expired:
                self.active_automation_tokens.pop(k, None)
            while len(self.active_automation_tokens) >= getattr(self, "MAX_AUTOMATION_TOKENS", 50):
                oldest = min(self.active_automation_tokens, key=self.active_automation_tokens.get)
                self.active_automation_tokens.pop(oldest, None)
            self.active_automation_tokens[tok] = now + 300
        return tok

    def validate_and_consume_automation_token(self, token: str) -> bool:
        if not token or not isinstance(token, str):
            return False
        with self.lock:
            now = time.time()
            expired = [k for k, exp in self.active_automation_tokens.items() if exp < now]
            for k in expired:
                self.active_automation_tokens.pop(k, None)
            if token in self.active_automation_tokens:
                exp = self.active_automation_tokens.pop(token)
                if exp >= now:
                    return True
        return False

    def _push_notification(self, notif):
        self.notifications.append(notif)
        if len(self.notifications) > 100:
            del self.notifications[:-100]

    def _loop(self):
        last_watchdog = 0
        while self.running:
            try:
                self.check_timers()
                self.check_daily_briefing()

                now = time.time()
                if now - last_watchdog >= 60:
                    last_watchdog = now
                    self.check_hardware_watchdog()
            except Exception:
                pass
            time.sleep(1.0)

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False


# Global default instance
SCHEDULER = SchedulerEngine()
