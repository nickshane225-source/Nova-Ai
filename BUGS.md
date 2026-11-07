# Nova AI - Bug Tracking & Quality Audit Report (BUGS.md)

| ID | Location | Steps to Reproduce | Expected vs Actual | Root Cause | Severity | Status |
|---|---|---|---|---|---|:---:|
| **BUG-001** | `server.py:3560-3566` | Send `DELETE /api/notes` with empty body `{}` | Expected: HTTP 400 Bad Request. Actual: Returned HTTP 200 `{"ok": false}`. | Missing validation for note identifier (`id` or `title`) before delegating to `memory_engine`. | **Medium** | **Fixed** |
| **BUG-002** | `server.py:3550-3568` | Send REST request `DELETE /api/timers` or `DELETE /api/automations` with `{ "id": ... }` | Expected: HTTP 200 if cancelled, 404 if not found. Actual: HTTP 404 for all requests. | `do_DELETE` only handled `/api/notes`; `/api/timers` and `/api/automations` were omitted from DELETE handler. | **Medium** | **Fixed** |
| **BUG-003** | `server.py:3698-3720` | Send `POST /api/config` with non-integer value for `run_code_trusted_minutes` (e.g. `"not_an_int"`) | Expected: Immediate HTTP 400 Bad Request with validation error. Actual: Prompted for security confirmation token with HTTP 200 before validation. | Confirmation check intercepted request before input syntax and numeric type validation was executed. | **Medium** | **Fixed** |
| **BUG-004** | `server.py:3595-3645` | Send `POST /api/chat` or `POST /api/chat/stream` with an excessively large payload (>50,000 characters) | Expected: HTTP 413 / 400 rejection for exceeding maximum message size. Actual: Hangs processing giant prompt over remote LLM, tying up server worker thread. | Missing input size guard rails on incoming chat message endpoints. Enforced 30,000 character maximum. | **High** | **Fixed** |
| **BUG-005** | `web/app.js:1592` | Open Settings and click "Clear chat history" (`#reset`) | Expected: Server chat history reset and onscreen `#subtitle` and `#actionHud` cleared. Actual: Subtitle and action HUD remained on screen. | `#reset.onclick` only called `api("/api/reset")` without updating DOM subtitle or hiding action HUD. | **Low** | **Fixed** |
| **BUG-006** | `web/app.js:618-623` | Speak and pause or stop listening in Chrome/Edge | Expected: Silent handling of normal speech recognition abort events. Actual: Console warning logged on every turn: `[Nova AI] Speech error: aborted`. | `me.onerror` only ignored `"no-speech"`, treating standard `"aborted"` lifecycle event as an unhandled warning. | **Low** | **Fixed** |
| **BUG-007** | `web/index.html`, `web/remote.html`, `server.py` | Load app in browser and observe developer tools network tab | Expected: Valid favicon with 200 OK. Actual: Browser logs 404: `:8765/favicon.ico:1 Failed to load resource`. | Missing explicit `<link rel="icon">` in `<head>` and missing icon asset fallback on static handlers. Served SVG data URI and crisp fallback. | **Low** | **Fixed** |
| **BUG-008** | `web/remote.js:104-123` | Execute Second Brain, Plan, or Integration skill via mobile remote | Expected: Clean human-readable action label (e.g. `✓ Note`, `✓ Plan`, `✓ GitHub`). Actual: Raw skill token displayed. | Missing mappings in `ACTION_LABEL` table in `web/remote.js`. | **Low** | **Fixed** |
| **BUG-009** | `integrations/github_connector.py:34-55, 165-215` | Send `[[GITHUB: ../repo | info]]` or `CON/repo` or trigger zip extract traversal | Expected: Strict regex and device name rejection, safe directory path resolution. Actual: Path traversal and illegal device names permitted. | Missing regex validation on owner/repo tokens, missing check against Windows reserved device names (`CON`, `PRN`, `AUX`, `NUL`), and unvalidated zip member extraction path. | **High** | **Fixed** |
| **BUG-010** | `discord_gateway.py:129-140` | Run `!confirm <expired_token>` or `!confirm` without a token | Expected: Clear error message explaining why confirmation failed, and execution result attached on success. Actual: Inspected nonexistent `result.get("message")`, reported false `"Action allowed"` when execution failed, and discarded execution output on success. | Evaluated wrong dictionary key (`result.get("message")` instead of `result.get("ok")`) and failed to attach `result.get("result")` to Discord response embed. | **Medium** | **Fixed** |
| **BUG-011** | `usage_tracker.py:65-115` | Call `record_usage(...)` with `None` or non-integer token parameters | Expected: Defensive type coercion (`int(tokens or 0)`) without crashing. Actual: Threw `TypeError` during float division/multiplication when computing USD pricing. | Missing defensive type coercion and non-negative clamping on token input parameters. | **Medium** | **Fixed** |
| **BUG-012** | `server.py:3584, 3746` | Call `GET` or `POST /api/github` when network or GitHub API throws an unhandled exception | Expected: HTTP 500 JSON response `{"ok": false, "error": "..."}`. Actual: Unhandled exception escaped to HTTP server loop, closing connection without structured response. | Missing `try...except Exception as e:` wrapping around `gh.run(cfg, ...)` in HTTP request handlers. | **Low** | **Fixed** |
| **BUG-013** | `web/remote.js:104-135` | Execute `DIAGNOSTICS`, `USAGE`, or `AUDIT` tools via the mobile web remote interface | Expected: User-friendly action pill (`✓ System health`, `✓ Token usage`, `✓ Security audit`). Actual: Displayed raw internal tool token name (`✓ DIAGNOSTICS`). | Missing action mappings in the `ACTION_LABEL` lookup table in `web/remote.js`. | **Low** | **Fixed** |
| **BUG-014** | `integrations/github_connector.py:100-115` | Send `[[GITHUB: owner/repo | file:]]` with an empty file path | Expected: Informative validation error requesting a relative file path. Actual: Queried GitHub repository root content JSON endpoint. | Splitting action on `file:` returned an empty string which was passed directly to GitHub API without empty check. | **Low** | **Fixed** |

---

## How I Tested

1. **Automated Comprehensive Audit Suite (`test_comprehensive_audit.py`)**:
   - Spawns live `SilentThreadingHTTPServer` test instance.
   - Tests all REST methods (GET, POST, DELETE) for normal, malformed, empty, and boundary conditions.
   - Verifies HTTP 413 on message overflow (>30,000 chars).
   - Verifies HTTP 400 on empty note deletion, non-integer config values, invalid parameters, and missing GitHub repo.
   - Verifies HTTP 404 on nonexistent timer/automation cancel.
   - Verifies DNS rebinding and cross-site request forgery prevention (`Host` header and `Sec-Fetch-Site: cross-site`).
   - Verifies `/api/diagnostics` and `/api/metrics/usage` / `/api/usage` aliases.
   - Verifies graceful error handling on GitHub connector exceptions without server crashes.
   - Results: **31 / 31 tests passed in 2.805s**.

2. **Full Regression Test Suite across all 25 test modules**:
   - Command: `python -m unittest discover -p "test_*.py"`
   - Verifies core server, memory engine, scheduler, guardian safety agent, plan mode, audio synthesis, fallback routing, voice regression, token usage tracker, system diagnostics, Telegram gateway, Discord gateway, GitHub connector, and workspace boundaries.
   - Results: **198 / 198 tests passed in 52.397s** (0 failures, 0 errors).

3. **Node.js Voice Pipeline Regression Suite**:
   - Command: `node test_voice_regression.js`
   - Real `web/app.js` sandboxed VM testing speech lifecycle, abort streak limiters, echo guards, and debounce scheduling.
   - Results: **6 / 6 tests passed cleanly**.
