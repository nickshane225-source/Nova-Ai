# Nova AI — Agent & LLM Fast-Context Specification

> **Stack:** Python 3.8+ Standard Library (**Zero Pip Dependencies**), Vanilla ES6 JS, Tailwind JIT (`web/tailwind.js`), SQLite 3.  
> **Ports:** `:8765` (Main Web HUD / SSE API), `:8766` (Mobile QR Remote), `:9222` (Chrome CDP Debugger).

---

## 1. Directory & Module Map
* `server.py`: Primary HTTP server (`SilentThreadingHTTPServer`), SSE streaming, router, LLM orchestration, and skill execution bus (`run_skill`).
* `guardian_agent.py`: Pre-execution security filter (`review_command_safety`) detecting destructive commands.
* `memory_engine.py`: SQLite Second Brain (`data/nova_brain.db`) with Robertson-Spärck Jones BM25 semantic search.
* `plan_mode.py`: Autonomous multi-turn plan parsing (`parse_plan_tag`) and sequential execution (`execute_plan_batch`).
* `nova_browser.py`: Chrome DevTools Protocol (CDP) client driving DOM automation, tab tracking, and session persistence.
* `scheduler_engine.py`: Cron parser, countdown timers, morning daily briefings, and hardware watchdog (RAM/disk/battery).
* `usage_tracker.py`: Per-model token/USD cost estimator, append-only ledger (`data/usage.jsonl`), and budget caps.
* `diagnostics.py`: System self-healing checks (Python version, directory writability, SQLite integrity check, DPAPI).
* `audit_logger.py`: Thread-safe append-only security audit trail (`data/audit.jsonl`) with automatic secret redaction.
* `skills_engine.py`: Dynamic skill loader parsing Markdown documents from `skills/developer/` and `skills/cyber/`.
* `integrations/`: Extensible plugins (e.g. `github_connector.py` for traversal-safe GitHub API queries and cloning).
* `telegram_gateway.py` & `discord_gateway.py`: Zero-pip bot gateways with user whitelisting and interactive confirmations.
* `web/`: `index.html` (HUD), `app.js` (Web Speech API, 3D particle core, audio synthesizer), `style.css`, `remote.html/js`.

---

## 2. Key Conventions
* **Zero Pip Dependency Rule:** Never import third-party packages in runtime backend files. Standard library only (`urllib.request`, `http.server`, `sqlite3`, `ctypes`, etc.).
* **Single-Origin Defense:** Requests must pass `check_local_request()` (validates `Host: 127.0.0.1:<port>` and blocks cross-site headers).
* **Workspace Jail:** File read/write and code execution must be jailed to `./workspace/` via `resolve_workspace_path(path)`.
* **Hardware DPAPI Encryption:** API keys are encrypted with Windows DPAPI (`CryptProtectData`) and prefixed with `dpapi:`.
* **Taint Tracking:** Reading external web pages, files, or notes marks turns as `is_tainted`, forcing user confirmation on destructive tags.

---

## 3. How to Add a New Action Tag (`[[MY_TOOL]]`)
1. **Define Schema:** Add tag syntax to system prompts in `server.py:build_system` (or `skills/developer/` / `skills/cyber/`).
2. **Configure Security Gate:** In `server.py:check_tool_confirmation_required()`, specify if user approval is required or if it belongs in `NO_CONFIRM_TOOLS`.
3. **Implement Execution Branch:** In `server.py:run_skill()`, add handler:
   ```python
   if name == "MY_TOOL":
       return skill_my_tool(raw_arg, cfg=cfg)
   ```
4. **Register Mobile Label:** In `web/remote.js:ACTION_LABEL`, add `'MY_TOOL': 'My Tool Description'`.
5. **Add Automated Regression Test:** Add test cases in `test_comprehensive_audit.py` or `test_skills.py`.

---

## 4. How to Add a New LLM Provider
1. **Add Preset:** In `server.py:PRESETS`, add model identifier, base URL, and provider type:
   ```python
   "myprovider": {"model": "my-model-name", "base_url": "https://api.myprovider.com/v1"}
   ```
2. **Implement API Call:** In `server.py:_call_single_llm()`, add header/auth mapping (or use standard OpenAI-compatible block).
3. **Register Fallback Chain:** In `server.py:call_llm_with_fallback()`, add failover mapping for the new provider.
4. **Register Pricing:** In `usage_tracker.py:calculate_cost()`, register per-million token input/output pricing.
5. **Add Frontend Option:** In `web/index.html` (Settings panel), add `<option value="myprovider">`.

---

## 5. How to Add a New UI Panel
1. **Add Navigation Button:** In `web/index.html` under `<nav id="nodes">`:
   ```html
   <button class="btn" data-panel="mypanel">My Panel</button>
   ```
2. **Implement Panel View:** In `web/app.js:renderPanel(name)`, add branch:
   ```javascript
   if (name === "mypanel") {
     const data = await api("/api/mypanel/data");
     body.innerHTML = `<h2>My Panel</h2><div class="p-3">${esc(data.text)}</div>`;
   }
   ```
3. **Add Backend Endpoint:** In `server.py:do_GET` or `do_POST`, route `/api/mypanel/data` with `check_local_request` validation.

---

## 6. Cardinal Rules (DO NOT BREAK)
1. **NEVER add pip packages.** The codebase must run on a clean standard Python install.
2. **NEVER expose raw secrets.** Always pass configuration dicts through `mask_secrets()` before returning over REST.
3. **NEVER bypass `resolve_workspace_path()`.** Direct `open(user_path)` escapes the sandboxed workspace jail.
4. **NEVER play audio on host PC during remote turns.** Calls with `source in ("phone", "telegram", "discord")` must remain silent.
5. **NEVER bypass `check_tool_confirmation_required()`.** Destructive shell/file operations must strictly enforce approval tokens.
