# Nova AI All-7-Categories Upgrade Implementation Plan

> **For Agent:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform Nova AI into an all-around desktop companion by implementing all 7 upgrade categories: Multimodal Screen Vision, Audio & Hands-free Chimes, Global Hotkey / Quick Spotlight, Autonomous Self-Healing Coding Agent, Interactive Browser DOM Automation, Local SQLite Second Brain Memory, and Proactive Daily Briefing with Hardware Watchdog.

**Architecture:** Pure standard-library Python architecture on the backend (`server.py`, `nova_browser.py`, `memory_engine.py`, `scheduler_engine.py`) using native Windows APIs (`ctypes`, `subprocess`), SQLite (`sqlite3` with full-text search), CDP protocol for browser interaction, and Web Audio API + Web Speech on the frontend (`web/app.js`, `web/index.html`, `web/style.css`).

**Tech Stack:** Python 3 (standard library: `sqlite3`, `ctypes`, `urllib`, `json`, `threading`, `socket`, `time`, `base64`), Chrome DevTools Protocol (CDP), HTML5, CSS3, JavaScript (Web Audio API, Web Speech API, Canvas).

---

### Global Constraints & Standards
1. **Zero External PIP Dependencies Required**: Everything runs out-of-the-box with standard Python 3.8+ on Windows/macOS/Linux. Optional enhancements degrade gracefully if not installed.
2. **Preserve Compatibility**: Keep all existing skills (`OPEN_APP`, `VOLUME`, `BROWSER_OPEN`, etc.) functioning without regressions.
3. **Multilingual Consistency**: Ensure new skills and voice summaries honor the user's active spoken language.
4. **Resilient Error Handling**: Long-running threads (watchdog, scheduler) must be isolated with try/except guards and clean shutdown hooks.

---

## Phased Implementation Tasks

### Task 1: Multimodal Desktop Screen Vision Engine
**Files:**
- Modify: `server.py`
- Modify: `web/app.js`
- Modify: `web/index.html`

- [x] **Step 1: Implement Multimodal LLM Vision Dispatcher in `server.py`**
  - Add `call_llm_vision(cfg, system, prompt, base64_image)` supporting:
    - Gemini (`generativelanguage.googleapis.com` OpenAI-compatible image_url / inlineData)
    - Anthropic (`image` block with base64 PNG)
    - OpenAI-compatible (`gpt-4o`, `gpt-4o-mini` with `image_url` data URL)
    - Ollama (`images: [base64_string]`)
- [x] **Step 2: Add `SCREEN_ANALYZE` and `VISION` Skills**
  - Capture desktop screenshot into memory (or read `Pictures/NovaScreenshots`), downscale/encode to base64 PNG, and feed to vision LLM.
  - Tag: `[[VISION: question]]` or `[[SCREEN_ANALYZE: question]]`.
- [x] **Step 3: Add "See Screen" Camera/Eye Button in Web UI**
  - Add an eye icon button in the bottom input bar to let the user attach a live desktop screenshot with one click or ask: *"What is on my screen right now?"*.

---

### Task 2: Web Audio Synthesizer, Sound Effects & Hands-Free Audio HUD
**Files:**
- Modify: `web/app.js`
- Modify: `web/style.css`

- [x] **Step 1: Implement Pure Web Audio Sound Generator in `web/app.js`**
  - Use HTML5 `AudioContext` with zero audio file assets:
    - `playChime('activate')` (futuristic dual-tone ascending beep when listening starts)
    - `playChime('success')` (pleasant harmonious chime when a skill succeeds)
    - `playChime('alert')` (subtle attention pulse for watchdog alerts)
    - `playChime('thinking')` (soft futuristic low-frequency cybernetic hum)
- [x] **Step 2: Add Audio Sound Toggle in Settings**
  - Checkbox in Settings: *"Enable sci-fi sound effects"* (enabled by default).
- [x] **Step 3: Continuous Standby Listening Mode**
  - Add a toggle for continuous hands-free dialogue: after Nova finishes speaking, automatically resume listening after a 1.2-second pause if continuous mode is on.

---

### Task 3: Global Hotkey & Quick Summon Spotlight Palette
**Files:**
- Modify: `web/index.html`
- Modify: `web/app.js`
- Modify: `web/style.css`
- Create: `quick_summon.bat`

- [x] **Step 1: In-Browser Spotlight Command Palette (`Ctrl+Space` / `Win+K`)**
  - Pressing `Ctrl+Space` or `Escape` opens an overlay with an instant command launcher:
    - Fuzzy quick-actions (Open Browser, Capture Screen, System Stats, Run Code).
    - Instant voice or text input with live autocomplete.
- [x] **Step 2: Windows Quick-Summon Desktop Helper (`quick_summon.bat`)**
  - Lightweight script to focus/bring Nova AI browser window to front instantly from any desktop workspace.

---

### Task 4: Autonomous Coding Agent Self-Healing Loop & Surgical File Editing
**Files:**
- Modify: `server.py`
- Test: `test_agent_healing.py`

- [x] **Step 1: Implement `EDIT_FILE` Surgical Search & Replace Skill**
  - Syntax: `[[EDIT_FILE: path | search_pattern | replacement]]`
  - Replaces specific snippets without rewriting hundreds of lines.
- [x] **Step 2: Implement `CREATE_PROJECT` Scaffolding Skill**
  - Syntax: `[[CREATE_PROJECT: html-app | react-vite | python-cli | name]]`
  - Instantly scaffolds template files into `workspace/<name>`.
- [x] **Step 3: Implement Autonomous Multi-Turn Error Correction (Self-Healing Loop)**
  - When `RUN_CODE` returns non-zero exit code or `Traceback (most recent call last):`:
    - Automatically create an internal reflection prompt: *"The execution failed with: <error>. Inspect the file, edit or fix it, and test again."*
    - Allow up to 3 automatic iterations before reporting final status.
    - Provide complete live activity logging in the top agent badge (`RETRYING (1/3)`, `FIXING CODE`).

---

### Task 5: Interactive Nova Browser DOM Automation (Click, Type, Scroll, Capture)
**Files:**
- Modify: `nova_browser.py`
- Modify: `server.py`
- Test: `test_nova_browser_interactive.py`

- [x] **Step 1: Add CDP Element Interaction Methods in `nova_browser.py`**
  - `click_element(selector_or_text)`: Evaluates JavaScript query and dispatches simulated mouse click.
  - `type_in_element(selector, text)`: Focuses input field and sets values with input events.
  - `scroll_page(direction_or_pixels)`: Scrolls window by specified amount or to top/bottom.
  - `capture_tab_screenshot()`: Invokes CDP `Page.captureScreenshot` to get page visual base64.
- [x] **Step 2: Expose Browser DOM Skills in `server.py`**
  - `[[BROWSER_CLICK: selector_or_text]]`
  - `[[BROWSER_TYPE: selector | text]]`
  - `[[BROWSER_SCROLL: up/down/500]]`
  - `[[BROWSER_SCREENSHOT]]`
- [x] **Step 3: Update Skills & Nova Browser UI Panel**
  - Add interactive test controls in the Nova Browser panel to test DOM clicks and scrolls.

---

### Task 6: Local SQLite Second Brain & Semantic Memory Engine
**Files:**
- Create: `memory_engine.py`
- Modify: `server.py`
- Modify: `web/app.js`
- Modify: `web/index.html`

- [x] **Step 1: Create SQLite Brain Database (`data/nova_brain.db`)**
  - Tables:
    - `notes(id INTEGER PRIMARY KEY, title TEXT, content TEXT, category TEXT, created_at TEXT, updated_at TEXT)`
    - `memories(id INTEGER PRIMARY KEY, fact TEXT, category TEXT, score REAL, created_at TEXT)`
- [x] **Step 2: Implement BM25 / TF-IDF Semantic Search in Pure Python**
  - Index terms and retrieve top relevant notes/memories for any query without external vector database dependencies.
- [x] **Step 3: Expose Notes & Second Brain Skills**
  - `[[NOTE: title | content]]`
  - `[[SEARCH_NOTES: query]]`
  - `[[DELETE_NOTE: title_or_id]]`
  - Automatically query Second Brain when user asks about personal projects or saved notes.
- [x] **Step 4: Add "Second Brain" Tab in Web UI**
  - View, search, create, and delete rich notes and documents with category tags.

---

### Task 7: Proactive Daily Briefings, Reminders & System Hardware Watchdog
**Files:**
- Create: `scheduler_engine.py`
- Modify: `server.py`
- Modify: `web/app.js`
- Modify: `web/index.html`

- [x] **Step 1: Background Scheduler Engine (`scheduler_engine.py`)**
  - Recurring jobs:
    - Morning Briefing at configurable time (e.g. 09:00 AM) or on first wake-up: Weather (via open `wttr.in`), Top BBC news headlines, PC system status, and pending reminders.
    - Reminders & Timers:
      - `[[REMIND: 15m | Check the oven]]` or `[[REMIND: 17:30 | Meeting with team]]`
      - `[[TIMER: 5m | Tea is ready]]`
- [x] **Step 2: System Health & Battery Watchdog**
  - Periodic background check every 60 seconds:
    - Battery < 20% and discharging -> Trigger warning event.
    - RAM usage > 92% -> Trigger warning event.
    - Disk free space < 5GB -> Trigger warning event.
- [x] **Step 3: Event Notification Stream to Frontend**
  - Frontend polls `/api/notifications` or `/api/events` and plays voice/visual notifications when reminders fire or watchdog alerts trigger.
- [x] **Step 4: UI Scheduler & Reminders Management**
  - New "Schedule" panel in UI to view active timers, set morning briefing time, and view watchdog statuses.

---

## Verification & Testing
1. **Unit & Integration Tests**:
   - `test_agent_healing.py`: Verify self-healing loop successfully corrects a syntax/runtime error in Python script.
   - `test_nova_browser_interactive.py`: Verify CDP DOM click, type, and scroll actions.
   - `test_memory_engine.py`: Verify SQLite note storage, search retrieval, and memory indexing.
   - `test_scheduler.py`: Verify timer firing and reminder delivery.
2. **End-to-End Test**:
   - Run `python server.py`, execute test commands via API and browser UI, verify audio chimes, screen vision, browser DOM actions, second brain notes, and scheduler.
