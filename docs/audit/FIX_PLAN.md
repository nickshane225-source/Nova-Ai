# Nova AI — Prioritized Remediation & Fix Plan

**Project**: Nova AI (`d:\Developer Mode on\nova-ai`)
**Companion Audit Report**: [AUDIT_REPORT.md](file:///d:/Developer%20Mode%20on/nova-ai/docs/audit/AUDIT_REPORT.md)
**Feature Checklist**: [FEATURE_CHECKLIST.md](file:///d:/Developer%20Mode%20on/nova-ai/docs/audit/FEATURE_CHECKLIST.md)

---

## Remediation Strategy

All Critical and High findings are organized into **8 ordered, self-contained, regression-safe fix batches**. After each batch:
- Add regression tests named with the finding IDs
- Run the full Python unit test suite + Node.js voice regression suite
- Show the diff and stop for approval before moving to the next batch

---

## Batch 1 & 1b — Local File Access, Sensitive Locations & Browser Navigation Guards (`HIGH-02`, `HIGH-03`, `HIGH-04`)

### Findings & Hardening Addressed
| ID | Severity | Location | Summary of Fix |
|---|---|---|---|
| **HIGH-02** | **High** | `nova_browser.py`, `server.py` | Refuse `file://` and local filesystem paths outside `workspace/`; route local paths through `resolve_workspace_path` and `is_sensitive_nova_file` inside `normalize_target_url`, `open_new_tab`, `open_or_activate`, `launch_browser`, `read_page_content`, `youtube_action`, `BROWSER_ACTIVATE`, and `open_url`. Fix `is_local_target` so `localhost:3000/dashboard`, `127.0.0.1:8765/x`, `react/redux`, and `github.com/user/repo` are never treated as local. Require confirmation for `BROWSER_RESEARCH`/`BROWSER_OPEN`/`OPEN_URL`/`OPEN_FILE`/`VIEW_FILE` on any local path. Extend `EXECUTABLE_EXTENSIONS` with `.hta .reg .scr .com .pif .jar .msi .dll .psm1 .url .chm`; require confirmation for tainted `WRITE_FILE`/`EDIT_FILE` to `.html .htm .svg` and for `BROWSER_OPEN` of an HTML file written in a tainted turn. |
| **HIGH-03** | **High** | `server.py` | Never continue after `PermissionError` in `skill_organize_folder()`. Enforce `is_system_folder` (`C:\Windows`, `C:\Program Files`) even when `allow_outside_workspace=True`, and return a clear message explaining `allow_outside_workspace` when `Downloads` is refused. |
| **HIGH-04** | **High** | `server.py` | Deny by default everything under `data/`, all project source files (`*.py`, `web/`, `skills/`, build files), `.git/`, and backups; resolve symlinks/junctions, compare case-insensitively on Windows, handle 8.3 short names, and reject UNC paths. Add a sensitive-location deny list enforced even when `allow_outside_workspace=True`: `~/.ssh`, `~/.aws`, `~/.config`, `~/.gnupg`, `%APPDATA%`, `%LOCALAPPDATA%` (browser profiles, Credentials), `Windows\System32\config`, and any `.env`/`.pem`/`.key`/`id_rsa`/`*.kdbx`/`wallet.dat` file. |

---

## Batch 2 — Security Audit Log (`HIGH-06`, `HIGH-07`)

### Findings Addressed
| ID | Severity | Location | Summary of Fix |
|---|---|---|---|
| **HIGH-06** | **High** | `web/app.js` | Read `ev.guardian || ev.guardian_verdict || "NONE"`, normalize bracketed/unbracketed `"SAFE"`/`"DANGEROUS"` verdicts, color `EXECUTED`/`APPROVED`/`ALLOWED` rows green (`#2ed573`), `AWAITING_CONFIRMATION` amber (`#ffa502`), and `DENIED`/`BLOCKED` red (`#ff4757`), and render newest events first (`events.slice().reverse()`). |
| **HIGH-07** | **High** | `audit_logger.py`, `server.py`, `telegram_gateway.py`, `discord_gateway.py` | Ensure `get_recent_audits(limit=N)` / `get_recent_audit_events(limit=N)` returns the **last N** lines via a bounded `collections.deque`; log every conversational approval (`"yes"`) and denial (`"no"`) in `_chat_inner`, and preserve the `guardian` verdict across `/api/confirm` and gateway confirmations. |

---

## Batch 3 — Settings Save & Atomic File Persistence (`CRIT-01`, `HIGH-10`)

### Findings Addressed
| ID | Severity | Location | Summary of Fix |
|---|---|---|---|
| **CRIT-01** | **Critical** | `server.py`, `web/app.js` | Add `monthly_budget_usd`, `discord_enabled`, `discord_channel_ids`, and `discord_allowed_user_ids` to `VALID_CONFIG_KEYS` with type and range validation and real persistence. Route `discord_bot_token` through the encrypted secret path and never return it in `/api/state`. Update `web/app.js` to check the response status, display the error, and keep the modal open on failure. Add an API test sending the exact UI payload plus a Playwright test that saves, reloads, and verifies persistence. |
| **HIGH-10** | **High** | `server.py`, `usage_tracker.py`, `audit_logger.py` | Use atomic writes (`tempfile` + `os.replace`) and unified lock protection around read-modify-write operations for `config.json`, `memory.json`, `usage.jsonl`, and `audit.jsonl`. |

---

## Batch 4 — Trust Window, Confirmations, 1-Hour Write Lock & Single-Submit Modal (`CRIT-02`, `CRIT-03`, `HIGH-05`, `HIGH-09`)

### Findings Addressed
| ID | Severity | Location | Summary of Fix |
|---|---|---|---|
| **CRIT-02** | **Critical** | `server.py` | Replace bare `LAST_RUN_CODE_APPROVED_TIME` float assignment with a lock-protected holder object updated and read across `/api/confirm` and conversational approval paths; verify that trusted minutes are ignored after a tainted turn or any workspace write. |
| **CRIT-03** | **Critical** | `server.py` | Extend `NO_CONFIRM_TOOLS` strictly under these rules: untainted `source="pc"` turns may auto-run `LIST_FILES`, `READ_FILE` (workspace, non-sensitive only), and `SEARCH`; any tainted turn or non-`pc` source still requires confirmation for `READ_FILE`, `VISION`, `OPEN_URL`, `BROWSER_*`, `GITHUB`, and all writes. Add a full test matrix of `tool x tainted x source`. |
| **HIGH-05** | **High** | `server.py` | Ensure any `CMD`/`POWERSHELL`/`RUN_CODE` execution within 1 hour of any workspace write requires confirmation, and widen `detect_written_files_from_command` to cover hyphenated PowerShell cmdlets (`Set-Content`, `Add-Content`, `Out-File`, `Copy-Item`, `Move-Item`, `New-Item`, `Tee-Object`) and multiline scripts. |
| **HIGH-09** | **High** | `web/app.js` | Clear `pendingConfirmId` before `closeModal()` in `resolveConfirmation()` so clicking Approve or Deny sends **exactly one** `/api/confirm` request; verify with a Playwright test. |

---

## Batch 5 — Multi-Step `[[PLAN]]` Execution & Gate Inheritance (`HIGH-01`)

### Findings Addressed
| ID | Severity | Location | Summary of Fix |
|---|---|---|---|
| **HIGH-01** | **High** | `server.py`, `plan_mode.py` | Pass a step runner into `plan_mode.execute_plan_batch()` that sends each plan step through the **same** taint, Guardian, and confirmation gate as normal tags, inherits the turn's `is_tainted` and `source`, pauses at the first pending confirmation and resumes remaining steps after approval, caps steps at 10, and counts toward the budget. Test that a plan can never run `CMD`/`POWERSHELL`/`RUN_CODE` without confirmation. |

---

## Batch 6 — Providers, Vision Budget & Diagnostics (`HIGH-08`, `MED-08`)

### Findings Addressed
| ID | Severity | Location | Summary of Fix |
|---|---|---|---|
| **HIGH-08** | **High** | `server.py` | Log the provider and model that actually answered in `call_llm_with_fallback()`; check the monthly budget and log token/cost usage in `call_llm_vision()`. |
| **MED-08** | **Medium** | `diagnostics.py` | Label configured API keys accurately by provider (`provider`, `openai`, `anthropic`, `groq`, `gemini`, etc.) instead of unconditionally reporting Google Gemini. |

---

## Batch 7 — Python 3.10 Minimum, Packaging & Launcher Fixes (`CRIT-04`, `CRIT-05`, `HIGH-11`)

### Findings Addressed
| ID | Severity | Location | Summary of Fix |
|---|---|---|---|
| **CRIT-04** | **Critical** | `README.md`, `run.bat`, `server.py` | Set the minimum Python version to **Python 3.10** in `README.md`, `run.bat`, and a startup version check in `server.py` with a clear error message; verify no syntax or stdlib feature newer than Python 3.10 is used across all `.py` files. |
| **CRIT-05** | **Critical** | `build_exe.bat`, `skills_engine.py`, `integrations/__init__.py` | Add missing `--hidden-import` flags (`skills_engine`, `audit_logger`, `guardian_agent`, `plan_mode`, `telegram_gateway`, `discord_gateway`, `usage_tracker`, `diagnostics`, `integrations.github_connector`) and `--add-data "skills;skills"` to `build_exe.bat`; use a `sys._MEIPASS`-aware resource path helper in `skills_engine.py` and `integrations/__init__.py`. |
| **HIGH-11** | **High** | `quick_summon.bat`, `installer_wizard.py` | Update `quick_summon.bat` to use port `8765` (or configured port) instead of `8000`, and remove the obsolete `speech_engine.py` check from `installer_wizard.py`. |

---

## Batch 8 — Session Token Isolation, One-Time Mobile Pairing, Guardian Allowlist & `TAINT_SOURCE_TOOLS` Verification

### Security Controls Covered & Verified
| Control | Location | Verification & Hardening Scope |
|---|---|---|
| **Session Cookie + `X-Nova-Token` Header Isolation** | `server.py:1311-1312, 3935-3975`, `web/app.js` | Require **both** the `HttpOnly` `nova_session` cookie (issued via one-time `/?boot=<code>` exchange) and the per-session `X-Nova-Token` header (`secrets.compare_digest`, fail-closed) on every `/api/*` request, plus strict `Origin == http://127.0.0.1:<port>` and `Sec-Fetch-Site in {"same-origin", "none"}`. |
| **One-Time 5-Minute Mobile Pairing with Per-Device Tokens** | `server.py:1316-1344, 4124-4136, 4496-4503, 4947-5012`, `web/remote.js` | Generate single-use, 5-minute pairing codes (`generate_remote_pairing_code`), exchange via `POST /api/remote/pair` for a per-device bearer token stored in `PAIRED_DEVICES`, strip `?pair=` from the URL after load, and support listing (`GET /api/remote/devices`) and revoking (`POST /api/remote/devices/revoke`) paired devices. |
| **Guardian Explicit Allowlist for Auto-Approved Commands** | `guardian_agent.py:103-195`, `server.py:1624-1628` | Require any remote/scheduled command that skips confirmation to match `guardian_agent.is_command_in_allowlist()` in addition to passing the regex denylist (`_is_local_rail_dangerous`), blocking destructive commands (`vssadmin`, `reg delete`, `diskpart`, `Clear-Disk`, `Remove-Item -Recurse -Force`). |
| **Full `TAINT_SOURCE_TOOLS` Coverage** | `server.py:3455-3468` | Verify `TAINT_SOURCE_TOOLS` includes all external/untrusted data ingestion tools (`GITHUB`, `SEARCH`, `OPEN_URL`, `BROWSER_RESEARCH`, `BROWSER_READ`, `READ_PAGE`, `PAGE_CONTENT`, `BROWSER_OPEN`, `BROWSER_TABS`, `VISION`, `SCREEN_ANALYZE`, `READ_FILE`, `SEARCH_NOTES`, `ACTIVE_WINDOW`, `GET_WINDOW`, `LIST_FILES`, `SMART_HOME`, `WEBHOOK`, `IOT`, `BRIEFING`, `MORNING_BRIEFING`, `NEWS`) plus any aliases. |
