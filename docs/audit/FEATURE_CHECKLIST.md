# Nova AI — Complete Feature & Function Checklist

**Audit Date:** 2026-11-08  
**Status Legend:**
- `PASS` — Verified working as designed via live execution and/or automated test harness.
- `PARTIAL` — Works in basic cases, but has edge-case bugs, UI display issues, or documentation mismatches.
- `FAIL` — Broken in normal usage or fails its primary design contract.
- `NOT TESTED` — Requires physical audio hardware or live third-party cloud credentials prohibited by audit safety rules.

---

## 1. Core Server & Authentication (`server.py`)

| Feature / Function | Location | Status | Notes / Finding Reference |
| :--- | :--- | :---: | :--- |
| Server startup & busy-port detection (`main`) | [`server.py:4904-4950`](file:///d:/Developer%20Mode%20on/nova-ai/server.py#L4904-L4950) | `PASS` | Detects port in use and exits cleanly without opening a duplicate browser tab. |
| One-time boot URL exchange (`generate_boot_code`, `GET /?boot=`) | [`server.py:1326-1334`](file:///d:/Developer%20Mode%20on/nova-ai/server.py#L1326-L1334), [`server.py:3970-4004`](file:///d:/Developer%20Mode%20on/nova-ai/server.py#L3970-L4004) | `PARTIAL` | Valid code sets `HttpOnly; SameSite=Strict` cookie and `sessionStorage` token, but invalid code `403` omits `Content-Length` on keep-alive connections (`MED-02`). |
| Session lock page (`GET /` without cookie) | [`server.py:4007-4026`](file:///d:/Developer%20Mode%20on/nova-ai/server.py#L4007-L4026) | `PASS` | Serves `"Nova is locked - restart Nova or open the original tab"` (`01_locked_page_no_cookie.png`). |
| Dual-token API authentication (`check_session_auth`) | [`server.py:3924-3951`](file:///d:/Developer%20Mode%20on/nova-ai/server.py#L3924-L3951) | `PASS` | Requires both `nova_session` cookie and `X-Nova-Token` header via `secrets.compare_digest`; fails closed (`401`). |
| Localhost / Origin / `Sec-Fetch-Site` check (`check_local_request`) | [`server.py:3855-3921`](file:///d:/Developer%20Mode%20on/nova-ai/server.py#L3855-L3921) | `PASS` | Blocks non-localhost `Host`, cross-port `Origin`, and `same-site` / `cross-site` requests (`403`). |
| JSON request body parsing & size/depth limits (`BaseHandler._body`) | [`server.py:3822-3848`](file:///d:/Developer%20Mode%20on/nova-ai/server.py#L3822-L3848) | `PARTIAL` | Enforces 10 MB size limit and 50-level depth limit, but does not verify root JSON value is a `dict` (`MED-01`: JSON array causes `500 AttributeError`). |
| Python 3.8+ runtime compatibility | [`server.py:1313`](file:///d:/Developer%20Mode%20on/nova-ai/server.py#L1313), 6 modules | `FAIL` | Crashes on Python 3.8/3.9 due to PEP 585 (`dict[...]`) and PEP 604 (`X \| Y`) annotations without `from __future__ import annotations` (`CRIT-04`). |

---

## 2. Web Dashboard UI & UX (`web/index.html`, `web/app.js`)

| Screen / Control / Feature | Location | Status | Notes / Finding Reference |
| :--- | :--- | :---: | :--- |
| Main HUD & Particle Core Canvas (`#core`) | [`web/app.js:1886-1925`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L1886-L1925) | `PASS` | Smooth 60fps 3D particle sphere reactive to `idle`, `listening`, `thinking`, and `speaking` states (`02_dashboard_authenticated.png`). |
| Wireframe Globe & World Headlines (`#globe`, `loadNews`) | [`web/app.js:1856-1883`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L1856-L1883) | `PASS` | Renders rotating wireframe globe and fetches BBC World RSS headlines. |
| Text Chat Input & Subtitle Display (`#textform`, `send`) | [`web/app.js:763-822`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L763-L822) | `PASS` | Sends chat turn, displays subtitle and Action HUD (`03_chat_and_action_hud.png`). |
| SSE Streaming Chat (`streamChat`, `/api/chat/stream`) | [`web/app.js:27-44`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L27-L44), [`server.py:4163,4381`](file:///d:/Developer%20Mode%20on/nova-ai/server.py#L4163) | `FAIL` | `streamChat()` in `web/app.js` is dead code never called by `send()`, and backend `/api/chat/stream` blocks until `chat()` finishes synchronously and corrupts the stream on `LLMError` (`MED-03`). |
| Quick Language Selector (`#quickLang`) | [`web/index.html:307-321`](file:///d:/Developer%20Mode%20on/nova-ai/web/index.html#L307-L321), [`web/app.js:126-143`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L126-L143) | `PASS` | Supports 13 languages including English, Bengali, Hindi, and Urdu. |
| Mode Switch: Developer Mode <-> Cyber Mode (`ModeManager`) | [`web/app.js:856-892`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L856-L892) | `PASS` | Switches theme to red terminal HUD, hides sidebars, and isolates chat history (`22_cyber_mode_theme.png`). |
| Mini Floating HUD (`#btnMiniMode`) | [`web/index.html:153-181`](file:///d:/Developer%20Mode%20on/nova-ai/web/index.html#L153-L181), [`web/app.js:894-899`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L894-L899) | `PASS` | Collapses and expands compact overlay (`23_mini_hud_mode.png`). |
| Quick Summon Spotlight Modal (`Ctrl+Space`, `#spotlightModal`) | [`web/index.html:372-388`](file:///d:/Developer%20Mode%20on/nova-ai/web/index.html#L372-L388), [`web/app.js:2084-2128`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L2084-L2128) | `PASS` | Opens via `Ctrl+Space`, supports quick actions and direct prompt submission (`20_spotlight_modal.png`). |
| Agent Activity Monitor & Dropdown (`#agentBadge`, `#agentDetail`) | [`web/app.js:1957-2055`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L1957-L2055) | `PASS` | Polls `/api/activity` and renders live job status and step history (`21_agent_activity_dropdown.png`). |
| Confirmation Modal (`#confirmModal`, `showConfirmModal`) | [`web/index.html:357-370`](file:///d:/Developer%20Mode%20on/nova-ai/web/index.html#L357-L370), [`web/app.js:2133-2173`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L2133-L2173) | `PASS` | Displays full command preview without truncation, Guardian verdict, and Allow (`Enter`) / Deny (`Esc`) controls (`04_confirmation_modal.png`). |
| Toast Notifications (`showToast`) | [`web/app.js:155-182`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L155-L182) | `PARTIAL` | Works for `"normal"`, `"warning"`, `"alert"`, but callers passing `"error"` get `"normal"` cyan styling + success chime (`LOW-02`). |
| Left-Nav Panel: **Nova Browser** (`data-panel="browser"`) | [`web/app.js:915-1044`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L915-L1044) | `PASS` | Launches browser, opens quick links, lists/switches/closes tabs, and dispatches DOM click/type/scroll (`05_panel_nova_browser.png`). |
| Left-Nav Panel: **Second Brain** (`data-panel="brain"`) | [`web/app.js:1046-1127`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L1046-L1127) | `PARTIAL` | Add, BM25 search, and delete notes work, but tainted notes (`tainted=1`) are missing the `[untrusted source]` badge (`HIGH-09`, `06_panel_second_brain.png`). |
| Left-Nav Panel: **Schedule** (`data-panel="schedule"`) | [`web/app.js:1129-1185`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L1129-L1185) | `PARTIAL` | Timers and Morning Briefing work, but `"☀️ Run Morning Briefing Now"` button text is nearly invisible due to undefined `var(--c)`/`var(--c2)` (`LOW-01`, `07_panel_schedule_timers.png`). |
| Left-Nav Panel: **Automations** (`data-panel="automations"`) | [`web/app.js:1187-1237`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L1187-L1237) | `PASS` | Add, list, and cancel recurring automations (`08_panel_automations.png`). |
| Left-Nav Panel: **Skills** (`data-panel="skills"`) | [`web/app.js:1505-1677`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L1505-L1677) | `PASS` | Displays full interactive catalog of skills and active mode markdown procedures (`09_panel_skills.png`). |
| Left-Nav Panel: **Workspace** (`data-panel="workspace"`) | [`web/app.js:1679-1713`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L1679-L1713) | `PASS` | Displays workspace path, opens folder in Explorer, and triggers quick project scaffolds (`10_panel_workspace.png`). |
| Left-Nav Panel: **Memory** (`data-panel="memory"`) | [`web/app.js:1467-1488`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L1467-L1488) | `PASS` | Lists memories, shows `[untrusted source]` badge on tainted items, and supports add/delete (`11_panel_memory.png`). |
| Left-Nav Panel: **Character** (`data-panel="characters"`) | [`web/app.js:1490-1503`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L1490-L1503) | `PASS` | Switches active persona (`Nova`, `Jarvis`, `Mentor`, `Best Friend`) and adds custom personas (`12_panel_characters.png`). |
| Left-Nav Panel: **Mobile** (`data-panel="mobile"`) | [`web/app.js:1239-1310`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L1239-L1310) | `PARTIAL` | QR generation, regenerate code, and paired device list/revoke work, but network `<select>` regex checks `?t=` instead of `?pair=` (`LOW-03`, `13_panel_mobile_remote.png`). |
| Left-Nav Panel: **Doctor** (`data-panel="doctor"`) | [`web/app.js:1312-1350`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L1312-L1350) | `PARTIAL` | Renders health checks, but backend `diagnostics.py` mislabels OpenAI/Anthropic `api_key` as Google Gemini (`MED-08`, `14_panel_doctor_diagnostics.png`). |
| Left-Nav Panel: **Usage** (`data-panel="usage"`) | [`web/app.js:1352-1391`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L1352-L1391) | `PASS` | Displays monthly spend progress bar, token totals, and per-provider/model table (`15_panel_usage_budget.png`). |
| Left-Nav Panel: **GitHub Tools** (`data-panel="github"`) | [`web/app.js:1393-1422`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L1393-L1422) | `PASS` | Inspects repo info, issues, PRs, tree, files, clones, and installs skills (`16_panel_github_tools.png`). |
| Left-Nav Panel: **Audit Log** (`data-panel="audit"`) | [`web/app.js:1424-1465`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L1424-L1465) | `FAIL` | Always shows `Guardian: NONE` (reads `ev.guardian_verdict` instead of `ev.guardian`), colors normal `EXECUTED` actions red, and lists oldest events first (`HIGH-06`, `17_panel_audit_log.png`). |
| Left-Nav Panel: **Settings** (`data-panel="settings"`) | [`web/app.js:1715-1852`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L1715-L1852) | `FAIL` | Clicking **"Save Settings"** always fails with `HTTP 400 Unknown configuration key: monthly_budget_usd` and silently discards all changes (`CRIT-01`, `18_panel_settings.png`, `19_settings_save_400_bug.png`). |
| Mobile Phone Viewport (`375x812`) | [`web/index.html:328,345`](file:///d:/Developer%20Mode%20on/nova-ai/web/index.html#L328) | `PASS` | Hides right globe panel and wraps navigation buttons cleanly above footer (`24_mobile_responsive_375w.png`). |

---

## 3. Voice Pipeline (`web/app.js`, `test_voice_regression.js`)

| Feature / Function | Location | Status | Notes / Finding Reference |
| :--- | :--- | :---: | :--- |
| Wake-word detection (`checkWakeWord`: `"hey nova"`, `"jarvis"`, Bengali/Hindi/Urdu) | [`web/app.js:244-292`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L244-L292) | `PASS` | Verified via `node test_voice_regression.js` (Test 2 & Test 5). |
| Speech synthesis & 15s watchdog (`speak`) | [`web/app.js:354-472`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L354-L472) | `PASS` | Cleans markdown/URLs, chunks sentences, and recovers from browser TTS hang via watchdog (Test 3). |
| Barge-in voice interruption (`startBargeInMonitor`, `cancelSpeech`) | [`web/app.js:317-352`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L317-L352) | `PASS` | Cancels TTS speech when user speaks ≥2 words or stop command during playback (Test 6). |
| Multi-tab microphone coordination (`BroadcastChannel("nova_mic_channel")`) | [`web/app.js:56-73`](file:///d:/Developer%20Mode%20on/nova-ai/web/app.js#L56-L73) | `PASS` | Releases mic in background tab when a new tab claims microphone. |
| Physical hardware microphone acoustic pickup & speaker echo | Hardware / Browser | `NOT TESTED` | Cannot be tested in headless environment without physical audio hardware. |

---

## 4. Action Tag System (`[[TAG]]` in `server.py:2846-3191`)

| Action Tag | Executor Function | Status | Notes / Finding Reference |
| :--- | :--- | :---: | :--- |
| `[[OPEN_APP: name]]` | `open_any_app` (`server.py:1878`) | `PASS` | Launches configured/Start-Menu apps and rejects shell metacharacters. |
| `[[CLOSE_APP: name]]` | `close_app` (`server.py:1940`) | `PASS` | Always gated for confirmation (`server.py:1616`). |
| `[[VOLUME: up\|down\|mute\|unmute\|0-100]]` | `control_volume` (`server.py:1955`) | `PASS` | Dispatches virtual key codes on Windows. |
| `[[MEDIA: play\|pause\|next\|prev\|stop]]` | `control_media` (`server.py:1981`) | `PASS` | Dispatches media virtual key codes. |
| `[[SCREENSHOT]]` | `skill_screenshot` (`server.py:2032`) | `PARTIAL` | Captures PNG to `workspace/screenshots/`, whereas `README.md` and `SKILL_DOC` claim `Pictures` & open viewer (`LOW-05`). |
| `[[SYSTEM: stats\|lock\|sleep\|minimize\|empty_recycle_bin\|shutdown\|restart\|cancel_shutdown]]` | `control_system` (`server.py:2095`) | `PARTIAL` | Works on Windows; `get_system_stats()` and `shutdown`/`restart` run Windows commands unconditionally on non-Windows (`MED-12`). |
| `[[CMD: command]]` | `skill_cmd` (`server.py:2402`) | `PASS` | Gated for confirmation, enforces 2,000-char limit and `BLOCKED_CMD_PATTERNS`. |
| `[[POWERSHELL: script]]` | `skill_powershell` (`server.py:2420`) | `PARTIAL` | Gated for confirmation and enforces 2,000-char limit, but `r"\bformat\b"` in `BLOCKED_CMD_PATTERNS` falsely blocks harmless `Get-Date -Format yyyy` (`MED-13`). |
| `[[WRITE_FILE: path \| content]]` | `skill_write_file` (`server.py:2138`) | `PARTIAL` | Enforces workspace jail & executable extension confirmation, but untainted `.txt` writes also require confirmation because `WRITE_FILE` is not in `NO_CONFIRM_TOOLS` (`CRIT-03`). |
| `[[EDIT_FILE: path \| search \| replace]]` | `skill_edit_file` (`server.py:2158`) | `PARTIAL` | Performs literal substring replacement (`README.md:150` claims regex, `LOW-07`) and always requires confirmation due to `CRIT-03`. |
| `[[READ_FILE: path]]` | `skill_read_file` (`server.py:2225`) | `PARTIAL` | Enforces workspace jail and taints turn, but unexpectedly requires confirmation on PC because `READ_FILE` is missing from `NO_CONFIRM_TOOLS` (`CRIT-03`). |
| `[[LIST_FILES: path]]` | `skill_list_files` (`server.py:2243`) | `PARTIAL` | Lists directory inside workspace jail, but unexpectedly requires confirmation on PC because `LIST_FILES` is missing from `NO_CONFIRM_TOOLS` (`CRIT-03`). |
| `[[CREATE_PROJECT: template \| name]]` | `skill_create_project` (`server.py:2191`) | `PASS` | Scaffolds `web`, `python`, `fastapi`, or `node` projects inside `workspace/`. |
| `[[RUN_CODE: lang \| code]]` | `skill_run_code` (`server.py:2315`) | `PARTIAL` | Executes Python/Node/Batch/PS1, but uses hardcoded `"python"` instead of `sys.executable`, fixed `_run_temp.py` (`MED-12`), and broken `LAST_RUN_CODE_APPROVED_TIME` (`CRIT-02`). |
| `[[PLAN: goal \| step1 \| step2]]` | `plan_mode.execute_plan_batch` (`server.py:2906`) | `FAIL` | **Complete no-op (`HIGH-01`)**: `server.py:2912` omits `runner`, so `plan_mode.py` returns `"Step N: OK"` without executing any step! |
| `[[ORGANIZE: path]]` | `skill_organize_folder` (`server.py:2272`) | `FAIL` | **`HIGH-03`**: `except PermissionError:` fallback bypasses `allow_outside_workspace=False` for any non-system folder! |
| `[[GIT: args]]` | `skill_git` (`server.py:2440`) | `PASS` | Enforces subcommand allowlist (`status`, `log`, `diff`, `branch`, `add`, `commit`, etc.) and blocks `-c`, `--exec-path`, `--upload-pack`. |
| `[[GITHUB: repo \| action]]` | `GitHubConnector.run` (`integrations/github_connector.py:29`) | `PARTIAL` | Works for `info`, `issues`, `readme`, `tree`, `file:`, `clone`, `skills`, but labels PRs as `Issue #` (`MED-07`), extracts zip files twice (`MED-06`), and calls non-existent `skills_engine.invalidate_cache()` (`MED-05`). |
| `[[MOUSE_MOVE: x, y]]` | `skill_mouse_move` (`server.py:1141`) | `PASS` | Moves cursor via `ctypes.windll.user32.SetCursorPos`. |
| `[[MOUSE_CLICK: button \| x, y]]` | `skill_mouse_click` (`server.py:1166`) | `PASS` | Dispatches mouse click events on Windows. |
| `[[TYPE_KEYS: text]]` | `skill_type_keys` (`server.py:1209`) | `PASS` | Escapes SendKeys metacharacters and types into active window. |
| `[[HOTKEY: keys]]` | `skill_hotkey` (`server.py:1234`) | `PASS` | Dispatches system hotkeys (`ctrl+c`, `alt+tab`, `win+d`, etc.). |
| `[[ACTIVE_WINDOW]]` | `get_active_window_info` (`server.py:1278`) | `PASS` | Inspects foreground window title and process via Win32 API. |
| `[[VISION: question]]` | `skill_screen_analyze` (`server.py:2513`) | `PARTIAL` | Captures screen and calls `call_llm_vision`, but omits budget/usage tracking (`HIGH-08`) and requires confirmation due to `CRIT-03`. |
| `[[NOTE: title \| content]]` | `memory_engine.save_note` (`server.py:2938`) | `PARTIAL` | Saves to SQLite with `tainted` provenance, but single-argument `[[NOTE: text]]` saves empty `content=""` (`LOW-04`). |
| `[[SEARCH_NOTES: query]]` | `memory_engine.search_notes` (`server.py:2946`) | `PASS` | Runs BM25 search and wraps results in `<UNTRUSTED_NOTES_DATA>`. |
| `[[DELETE_NOTE: id_or_title]]` | `memory_engine.delete_note` (`server.py:2980`) | `PASS` | Gated for confirmation (`server.py:1629`). |
| `[[REMIND: spec \| msg]]` | `SCHEDULER.add_timer` (`server.py:2985`) | `PARTIAL` | Schedules reminder, but rapid calls in same millisecond collide on ID (`MED-11`). |
| `[[TIMER: spec \| msg]]` | `SCHEDULER.add_timer` (`server.py:3013`) | `PARTIAL` | Schedules countdown timer, but rapid calls in same millisecond collide on ID (`MED-11`). |
| `[[SCHEDULE_AUTO: spec \| action]]` | `SCHEDULER.add_recurring_task` (`server.py:3041`) | `PARTIAL` | Gated for confirmation (`server.py:1626`), but IDs can collide in same ms (`MED-11`). |
| `[[LIST_AUTOMATIONS]]` | `SCHEDULER.list_recurring` (`server.py:3049`) | `PASS` | Lists active recurring tasks. |
| `[[CANCEL_AUTOMATION: id]]` | `SCHEDULER.cancel_recurring` (`server.py:3057`) | `PASS` | Cancels recurring task by ID. |
| `[[SMART_HOME: url \| method \| json]]` | `skill_smart_home` (`server.py:2656`) | `PASS` | Blocks loopback, cloud metadata, public IPs, and Nova ports; pins resolved IP to defeat DNS rebinding. |
| `[[BRIEFING]]` | `SCHEDULER.get_morning_briefing_summary` (`server.py:3064`) | `PASS` | Generates weather, system health, and schedule summary. |
| `[[REMEMBER: fact]]` | `run_skill` (`server.py:3096`) | `PARTIAL` | Saves fact with `tainted` flag, but untainted `REMEMBER` unexpectedly requires confirmation because `REMEMBER` is omitted from `NO_CONFIRM_TOOLS` (`CRIT-03`). |
| `[[FORGET: keyword]]` | `run_skill` (`server.py:3113`) | `PASS` | Gated for confirmation (`server.py:1629`). |
| `[[OPEN_URL: url]]` | `open_url` (`server.py:2800`) | `PARTIAL` | Opens URL, but converts existing local file paths to `file:///` URIs without workspace jail check (`HIGH-02`). |
| `[[SEARCH: query]]` | `open_url` (`server.py:3089`) | `PASS` | Searches Google in browser. |
| `[[PLAY: query]]` | `nova_browser.youtube_action` (`server.py:3091`) | `PASS` | Searches YouTube and auto-plays top video. |
| `[[BROWSER_OPEN: url]]` | `nova_browser.open_or_activate` (`server.py:3119`) | `PARTIAL` | Opens or focuses tab, but `normalize_target_url` converts local files to `file:///` without workspace check (`HIGH-02`). |
| `[[BROWSER_TABS]]` | `nova_browser.list_tabs` (`server.py:3124`) | `PASS` | Lists open tabs in Nova Browser. |
| `[[BROWSER_ACTIVATE: query]]` | `nova_browser.activate_tab` (`server.py:3132`) | `PASS` | Brings matching tab to foreground. |
| `[[BROWSER_CLOSE: query]]` | `nova_browser.close_tab` (`server.py:3141`) | `PASS` | Closes matching tab via CDP. |
| `[[BROWSER_CLICK: target]]` | `nova_browser.click_element` (`server.py:3068`) | `PASS` | Gated for confirmation on non-allowlisted domains (`server.py:1640`). |
| `[[BROWSER_TYPE: sel \| text]]` | `nova_browser.type_in_element` (`server.py:3072`) | `PASS` | Gated for confirmation on non-allowlisted domains (`server.py:1640`). |
| `[[BROWSER_SCROLL: dir]]` | `nova_browser.scroll_page` (`server.py:3083`) | `PASS` | Scrolls active tab up/down/top/bottom. |
| `[[BROWSER_RESEARCH: url_or_query]]` | `nova_browser.read_page_content` (`server.py:3150`) | `FAIL` | **`HIGH-02`**: In `NO_CONFIRM_TOOLS` (`server.py:1567`), and `normalize_target_url()` converts local file paths (like `data/config.json`) to `file:///` URIs and extracts DOM text without checking `resolve_workspace_path()`! |
| `[[BROWSER_YOUTUBE: action \| query]]` | `nova_browser.youtube_action` (`server.py:3157`) | `PASS` | Controls YouTube playback in Nova Browser. |
| `[[BROWSER_WHATSAPP: contact \| msg]]` | `nova_browser.whatsapp_action` (`server.py:3175`) | `PASS` | Always gated for confirmation (`server.py:1613`). |
| `[[BROWSER_TELEGRAM: chat \| msg]]` | `nova_browser.telegram_action` (`server.py:3182`) | `PASS` | Always gated for confirmation (`server.py:1613`). |

---

## 5. Companion Modules & Subsystems

| Module / Subsystem | File | Status | Notes / Finding Reference |
| :--- | :--- | :---: | :--- |
| **Memory Engine & Second Brain** (`init_db`, `save_note`, `search_notes`, `delete_note`) | [`memory_engine.py`](file:///d:/Developer%20Mode%20on/nova-ai/memory_engine.py) | `PARTIAL` | Schema migration, 20-thread concurrency, and BM25 search pass; unhandled `sqlite3.DatabaseError` on corrupt DB file (`MED-09`) and 3 unused `memories` table functions (`MED-16`). |
| **Scheduler Engine & Watchdog** (`SchedulerEngine`) | [`scheduler_engine.py`](file:///d:/Developer%20Mode%20on/nova-ai/scheduler_engine.py) | `PARTIAL` | Countdown timers, recurring tasks, automation tokens, and morning briefing work; millisecond ID collisions (`MED-11`). |
| **Guardian Security Agent** (`review_command_safety`, `is_command_in_allowlist`) | [`guardian_agent.py`](file:///d:/Developer%20Mode%20on/nova-ai/guardian_agent.py) | `PASS` | Fail-closed dual-layer regex denylist + explicit remote allowlist + secondary LLM review. |
| **Plan Mode Coordinator** (`parse_plan_tag`, `execute_plan_batch`) | [`plan_mode.py`](file:///d:/Developer%20Mode%20on/nova-ai/plan_mode.py) | `FAIL` | `server.py:2912` calls `execute_plan_batch` with `runner=None`, so steps are never executed (`HIGH-01`). |
| **Skills Engine** (`load_skills`, `select_skills`, `build_skill_prompt`) | [`skills_engine.py`](file:///d:/Developer%20Mode%20on/nova-ai/skills_engine.py) | `PARTIAL` | Loads and matches developer/cyber skills, but lacks `invalidate_cache()` called by `GitHubConnector` (`MED-05`). |
| **Usage & Budget Tracker** (`record_usage`, `get_usage_summary`, `check_budget_status`) | [`usage_tracker.py`](file:///d:/Developer%20Mode%20on/nova-ai/usage_tracker.py) | `PARTIAL` | Enforces monthly budget cap (`PASS`), but `call_llm_with_fallback` logs primary provider instead of fallback (`HIGH-08`) and `get_usage_summary(days)` ignores `days` (`MED-10`). |
| **Security Audit Logger** (`log_audit_event`, `get_recent_audit_events`) | [`audit_logger.py`](file:///d:/Developer%20Mode%20on/nova-ai/audit_logger.py) | `PARTIAL` | Masks secrets and writes append-only JSONL, but UI reads `ev.guardian_verdict` instead of `ev.guardian` (`HIGH-06`) and conversational approvals aren't logged (`HIGH-07`). |
| **System Diagnostics / Doctor** (`run_diagnostics`) | [`diagnostics.py`](file:///d:/Developer%20Mode%20on/nova-ai/diagnostics.py) | `PARTIAL` | Checks environment, disk, SQLite integrity, DPAPI, and gateways, but misidentifies OpenAI/Anthropic `api_key` as Google Gemini (`MED-08`). |
| **Telegram Remote Gateway** (`TelegramGateway`, `handle_remote_confirm`) | [`telegram_gateway.py`](file:///d:/Developer%20Mode%20on/nova-ai/telegram_gateway.py) | `PASS` | Enforces `telegram_allowed_chat_ids` whitelist, `/allow` & `/deny`, `is_tainted` preservation, dynamic backtick fences, and `pc_only` for messages >4000 chars. |
| **Discord Remote Gateway** (`DiscordGateway`, `handle_remote_confirm`) | [`discord_gateway.py`](file:///d:/Developer%20Mode%20on/nova-ai/discord_gateway.py) | `PASS` | Enforces channel & user whitelists, `/allow` & `/deny`, `is_tainted` preservation, dynamic backtick fences, and `pc_only` for messages >1950 chars. |
| **Mobile Remote Server (`:8766`)** (`RemoteHandler`, `web/remote.js`) | [`server.py:4742-4880`](file:///d:/Developer%20Mode%20on/nova-ai/server.py#L4742-L4880), [`web/remote.js`](file:///d:/Developer%20Mode%20on/nova-ai/web/remote.js) | `PASS` | Enforces 5-min one-time pairing code, per-device token, URL stripping, device revocation, `SAFE_REMOTE_TOOLS` allowlist, and 5-attempt lockout (`25_remote_phone_ui_paired.png`). |
| **GitHub Integration Connector** (`GitHubConnector`) | [`integrations/github_connector.py`](file:///d:/Developer%20Mode%20on/nova-ai/integrations/github_connector.py) | `PARTIAL` | Validates owner/repo, blocks path traversal & Windows reserved names, but duplicates zip extraction (`MED-06`), labels PRs as `Issue #` (`MED-07`), and calls missing `invalidate_cache()` (`MED-05`). |
| **Installer & Packaging Scripts** (`build_exe.bat`, `installer_wizard.py`, `NovaAI_Installer.iss`) | Root scripts | `FAIL` | `build_exe.bat` omits 7 modules and `skills/` (`CRIT-05`); `installer_wizard.py` calls Tkinter from background thread (`MED-14`). |
