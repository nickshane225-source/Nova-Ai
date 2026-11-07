# Nova Browser Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform Nova AI from opening basic default browser windows to operating a dedicated, persistent browser named "Nova Browser" with full tab tracking, research extraction, and automation for YouTube, WhatsApp Web, and Telegram Web without requiring third-party pip dependencies.

**Architecture:** A standalone Python module `nova_browser.py` wraps Chrome/Edge using the Chrome DevTools Protocol (CDP) over localhost HTTP and WebSocket JSON endpoints. A dedicated user data profile (`data/nova_browser_profile`) preserves user logins (YouTube, WhatsApp Web, Telegram Web). `server.py` and `build_system()` are updated with tab-aware browser skills (`BROWSER_OPEN`, `BROWSER_TABS`, `BROWSER_READ`, `BROWSER_CLOSE`, `BROWSER_WHATSAPP`, `BROWSER_TELEGRAM`, `BROWSER_YOUTUBE`), and the web UI is given a Nova Browser status/control badge and launcher.

**Tech Stack:** Python 3 (standard library: `urllib`, `json`, `subprocess`, `threading`, `time`, `http`, `zipfile`), Chrome DevTools Protocol (CDP HTTP/WebSocket APIs), Windows Chrome/Edge executables, HTML5/CSS/JavaScript (Nova web interface).

**Spec:** In-conversation requirements: dedicated "Nova Browser" with persistent logins (YouTube, WhatsApp, Telegram), tab & session awareness to prevent duplicate tabs, research extraction, social/messaging management, and full zip export.

## Global Constraints
- Pure Python standard library: zero external pip dependencies required to launch and control the browser.
- Support Windows Edge (`msedge.exe`) and Chrome (`chrome.exe`) paths automatically.
- Store profile in `nova-ai/data/nova_browser_profile` so cookies and logins persist across app restarts.
- Preserve backward compatibility with existing voice/text skills.

## Review Focus
- Browser already running vs cold start: must safely connect to existing CDP port if already running or launch a new process.
- Duplicate URL prevention: normalizing URLs (e.g. `youtube.com` matching `https://www.youtube.com/`) to focus the tab instead of opening another.
- WebSocket / JSON CDP responsiveness: resilient timeout and error handling if tabs are closed or unresponsive.
- WhatsApp Web / Telegram Web message automation: verify input field selectors and safe sending.
- Clean packaging: zip generation creates an easily extractable archive excluding temporary files or bulky caches.

---

### Task 1: Core Nova Browser Engine (`nova_browser.py`)
**Files:**
- Create: `c:\Users\Devil\Downloads\Documents\nova-ai\nova-ai\nova_browser.py`
- Test: `c:\Users\Devil\Downloads\Documents\nova-ai\nova-ai\test_nova_browser.py`

- [ ] Detect installed Chrome or Edge executable on Windows.
- [ ] Implement browser launcher with `--remote-debugging-port=9222`, `--user-data-dir=<profile_path>`, and custom window title / app parameters.
- [ ] Implement CDP HTTP client functions:
  - `list_tabs()` -> query `http://127.0.0.1:9222/json/list`
  - `open_or_activate(url)` -> check if tab matching domain/URL exists; if yes activate via `/json/activate/<id>`, if not create tab via `/json/new?<url>`
  - `close_tab(target_id_or_keyword)`
  - `execute_js(tab_id, script)` -> execute JavaScript in tab context to inspect text or interact with DOM
  - `read_page_text(tab_id_or_url)` -> extract title and readable text content for AI research
- [ ] Add automation helpers for YouTube, WhatsApp Web, and Telegram Web.
- [ ] Create automated unit/integration test in `test_nova_browser.py` verifying detection, tab listing, and URL normalization.

### Task 2: Integrate Nova Browser Skills into `server.py`
**Files:**
- Modify: `c:\Users\Devil\Downloads\Documents\nova-ai\nova-ai\server.py`

- [ ] Import `nova_browser` into `server.py`.
- [ ] Add new skills to `SKILL_DOC`:
  - `[[BROWSER_OPEN: url]]` (tab-aware open or switch)
  - `[[BROWSER_TABS]]` (list open tabs and URLs)
  - `[[BROWSER_ACTIVATE: tab_id or search]]` (focus specific tab)
  - `[[BROWSER_CLOSE: tab_id or search]]` (close tab)
  - `[[BROWSER_RESEARCH: query or url]]` (open/read page text and summarize)
  - `[[BROWSER_YOUTUBE: play query | url]]`
  - `[[BROWSER_WHATSAPP: contact | message]]`
  - `[[BROWSER_TELEGRAM: contact | message]]`
- [ ] Update `run_skill()` to route `OPEN_URL`, `SEARCH`, `PLAY`, and new `BROWSER_*` skills through Nova Browser.
- [ ] Add HTTP API endpoints `/api/browser/status`, `/api/browser/tabs`, `/api/browser/open` for the web UI.

### Task 3: Update Web UI with Nova Browser Controls
**Files:**
- Modify: `c:\Users\Devil\Downloads\Documents\nova-ai\nova-ai\web\index.html`
- Modify: `c:\Users\Devil\Downloads\Documents\nova-ai\nova-ai\web\app.js`
- Modify: `c:\Users\Devil\Downloads\Documents\nova-ai\nova-ai\web\style.css`

- [ ] Add a "Nova Browser" button / panel in the left sidebar navigation.
- [ ] Show browser status indicator (Running / Closed, Open Tabs list with quick switch & close buttons).
- [ ] Add quick-launch shortcuts for YouTube, WhatsApp Web, Telegram Web, and Google Research.
- [ ] Add a "Launch Nova Browser" button so the user can open it at any time to sign in.

### Task 4: Automated Verification and Full ZIP Packaging
**Files:**
- Create: `c:\Users\Devil\Downloads\Documents\nova-ai\package_nova_ai.py`
- Output: `c:\Users\Devil\Downloads\Documents\nova-ai\nova-ai-updated.zip`

- [ ] Run test suite to verify browser launch, tab listing, CDP interaction, and server skills.
- [ ] Verify startup via `run.bat` and standard commands.
- [ ] Create Python packaging script to generate a clean `nova-ai-updated.zip` containing the entire updated project.
