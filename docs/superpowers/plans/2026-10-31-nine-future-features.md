# Nova AI - 9 Future Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 9 advanced desktop capabilities into Nova AI without external pip packages: Voice Wake-Word, Mini Floating HUD mode, OS-level Mouse/Keyboard automation, Active Window Awareness, Smart File Organizer, Voice Barge-in, Smart Home Webhooks, Recurring Background Automations, and Voice Customization Tuning.

**Architecture:** Pure Python standard library on backend (`server.py`, `scheduler_engine.py`) using Windows `ctypes` (`user32.dll`, `kernel32.dll`), `urllib`, and standard modules. Frontend enhancements in `web/app.js` and `web/index.html` using HTML5 Web Speech, Web Audio, and responsive CSS.

**Tech Stack:** Python 3 (standard library: `ctypes`, `urllib`, `sqlite3`, `threading`, `shutil`), Web Speech API, HTML5 Canvas, Tailwind CSS.

---

## Global Constraints
1. **Zero External PIP Dependencies**: Must run out-of-the-box on standard Python 3.8+ on Windows.
2. **Backward Compatibility**: Preserve all existing skills (`OPEN_APP`, `VOLUME`, `BROWSER_*`, etc.) and ensure all 20 existing unit tests continue to pass.
3. **Multilingual Support**: All voice summaries, text descriptions, and skills must maintain user language awareness.
4. **Resilient Thread Safety**: All background timers and automation loops must be protected by threading locks and clean exception handling.

---

## Tasks

### Task 1: OS-Level Mouse & Keyboard Automation
**Files:**
- Modify: `server.py`
- Test: `test_os_automation.py`

- [x] **Step 1: Write unit tests in `test_os_automation.py`**
  - Test argument parsing and safety boundaries for `MOUSE_MOVE`, `MOUSE_CLICK`, `TYPE_KEYS`, and `HOTKEY`.
- [x] **Step 2: Implement Win32 Mouse & Keyboard Skills in `server.py`**
  - Implement `skill_mouse_move(coords)`, `skill_mouse_click(args)`, `skill_type_keys(text)`, and `skill_hotkey(keys)` using `ctypes.windll.user32`.
  - Add safety bounds checking (screen resolution clamps).
- [x] **Step 3: Register skills in `SKILL_DOC` and `run_skill()`**
  - Connect tags `[[MOUSE_MOVE]]`, `[[MOUSE_CLICK]]`, `[[TYPE_KEYS]]`, `[[HOTKEY]]`.
- [x] **Step 4: Run unit tests and verify**

---

### Task 2: Active Window Context Awareness ("Look What I'm Doing")
**Files:**
- Modify: `server.py`
- Modify: `test_os_automation.py`

- [x] **Step 1: Implement `get_active_window_info()` in `server.py`**
  - Query `GetForegroundWindow()`, `GetWindowTextW()`, and `GetWindowThreadProcessId()`.
- [x] **Step 2: Add `[[ACTIVE_WINDOW]]` skill and inject into `build_system()`**
  - Add current foreground app and window title to Nova's awareness prompt so Nova knows what the user is working on.
- [x] **Step 3: Test active window detection**

---

### Task 3: Smart Downloads & Workspace File Auto-Organizer
**Files:**
- Modify: `server.py`
- Test: `test_file_organizer.py`

- [x] **Step 1: Write test suite for directory organizing in `test_file_organizer.py`**
  - Create a temp folder with dummy `.txt`, `.png`, `.py`, `.zip` files and verify sorting.
- [x] **Step 2: Implement `skill_organize_folder(path)` in `server.py`**
  - Categorize files into Documents, Images, Code, Installers & Archives, Media.
  - Skip hidden files, system files, and destination category folders.
- [x] **Step 3: Register `[[ORGANIZE: path]]` skill in `server.py`**
- [x] **Step 4: Run unit tests and verify**

---

### Task 4: Recurring Background Automations (Cron & Recurring Watchers)
**Files:**
- Modify: `scheduler_engine.py`
- Modify: `server.py`
- Test: `test_scheduler.py`

- [x] **Step 1: Extend `SchedulerEngine` with recurring tasks**
  - Implement `add_recurring_task(spec, action_tag, label)`, `list_recurring()`, and `cancel_recurring(task_id)`.
  - Update background thread loop in `check_timers()` to re-arm recurring tasks.
- [x] **Step 2: Add API routes and skill tags in `server.py`**
  - Register `[[SCHEDULE_AUTO: daily 09:00 | skill_command]]` and `[[SCHEDULE_AUTO: every 1h | skill_command]]`.
  - Expose `/api/automations` endpoints.
- [x] **Step 3: Update `test_scheduler.py` and run tests**

---

### Task 5: Smart Home & Local Network IoT Webhooks
**Files:**
- Modify: `server.py`
- Test: `test_smart_home.py`

- [x] **Step 1: Write unit tests in `test_smart_home.py`**
  - Test request dispatching, method parsing, and error formatting.
- [x] **Step 2: Implement `skill_smart_home(arg)` in `server.py`**
  - Support `[[SMART_HOME: url | POST/GET | json_body]]` and `[[WEBHOOK: url | payload]]`.
- [x] **Step 3: Register skill in `SKILL_DOC` and `run_skill()`**
- [x] **Step 4: Verify test execution**

---

### Task 6: Voice Customization & Pitch/Rate Tuning
**Files:**
- Modify: `server.py`
- Modify: `web/index.html`
- Modify: `web/app.js`

- [x] **Step 1: Add voice configuration options in `server.py` (`DEFAULT_CONFIG`)**
  - `voice_pitch` (0.8 - 1.4), `voice_rate` (0.8 - 1.4), `voice_volume` (0.1 - 1.0).
- [x] **Step 2: Update Character / Settings panel in `web/index.html` and `web/app.js`**
  - Add pitch, rate, and volume sliders with real-time test preview.
- [x] **Step 3: Connect settings to Web Speech API `SpeechSynthesisUtterance`**

---

### Task 7: "Hey Nova" Voice Wake-Word Detection
**Files:**
- Modify: `web/app.js`
- Modify: `web/index.html`

- [x] **Step 1: Implement Wake-Word matcher in `web/app.js`**
  - Continuously check speech recognition interim/final transcripts for trigger words: "hey nova", "nova", "hey jarvis", "jarvis".
  - Trigger activation chime (`playChime('activate')`) and activate listening mode automatically.
- [x] **Step 2: Add Wake-Word toggle in Settings**

---

### Task 8: Natural Voice "Barge-In" (Instant Speech Interruption)
**Files:**
- Modify: `web/app.js`

- [x] **Step 1: Implement instant speech cancellation on voice input**
  - When `rec.onspeechstart` or `rec.onresult` detects user speech while Nova is speaking (`mode === 'speaking'`), immediately execute `window.speechSynthesis.cancel()` and transition mode to `'listening'`.
- [x] **Step 2: Add Barge-In toggle in Settings**

---

### Task 9: Mini Floating Desktop HUD / Widget Mode
**Files:**
- Modify: `web/index.html`
- Modify: `web/app.js`

- [x] **Step 1: Add Mini HUD toggle button in UI header (`web/index.html`)**
- [x] **Step 2: Implement Mini HUD CSS layout and state toggle in `web/app.js`**
  - Condenses the full dashboard into a sleek 240x240 floating compact orb or Picture-in-Picture window displaying particle core, status, and voice controls.
- [x] **Step 3: Test toggling between full dashboard and mini HUD**

---

### Task 10: Full Regression Testing & Documentation
**Files:**
- Modify: `README.md`
- Run all test suites

- [x] **Step 1: Run all test suites (`python -m unittest discover`)**
- [x] **Step 2: Update `README.md` with full documentation for the 9 new features**
