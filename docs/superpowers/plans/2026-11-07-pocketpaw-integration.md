# Nova AI Multi-Tier PocketPaw Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement PocketPaw's premier capabilities (Telegram remote gateway, Guardian AI safety verifier, Plan Mode, Model Fallback Router, Append-Only Audit Log, extensible plugins, and SSE chat streaming) natively into Nova AI.

**Architecture:** A 3-tier architecture maintaining a strict 100% Python Standard Library core (Zero pip packages) with an extensible plugin loader for optional third-party integrations and an SSE streaming endpoint for external client interoperability.

**Tech Stack:** Python 3.11+ (Standard Library: `http.server`, `urllib.request`, `sqlite3`, `threading`, `json`, `re`, `ctypes`), Vanilla JS / Web Speech API.

**Spec:** [`docs/superpowers/specs/2026-11-07-pocketpaw-integration-design.md`](file:///d:/Developer%20Mode%20on/nova-ai/docs/superpowers/specs/2026-11-07-pocketpaw-integration-design.md)

## Global Constraints

- Zero third-party pip packages (stdlib only).
- Strict Developer / Cyber mode separation.
- Minimal edits to existing code, no unrelated refactors, no UI redesign.
- Multilingual mirroring intact (English, Bengali, Hindi, Urdu, etc.).
- All existing 116 unit tests and Node voice regression tests must pass without regressions.
- Remote messages (Telegram/mobile) must remain silent and not speak aloud over host PC speakers.

## Review Focus

1. **Malicious Telegram Chat IDs:** Telegram messages from non-whitelisted users must be rejected with HTTP 403 / silent drop and never touch `chat()`.
2. **Guardian AI Fail-Closed:** If Guardian AI secondary LLM call times out or returns malformed output, the action must fail closed as `DANGEROUS`.
3. **Model Fallback Timeout Guard:** Fallback loop across providers must not exceed a cumulative 90-second ceiling to prevent server thread starvation.
4. **Tag Leakage in SSE Stream:** `[[TAG: ...]]` tokens emitted during real-time streaming must be intercepted by a sliding window buffer so internal syntax is not leaked to clients.
5. **Audit Log Secret Scrubbing:** Sensitive keys (API keys, passwords, bearer tokens) must be stripped/masked before writing to `data/audit.jsonl`.

---

### Task 1: Append-Only Security Audit Logger (`audit_logger.py`)

**Files:**
- Create: `d:/Developer Mode on/nova-ai/audit_logger.py`
- Modify: `d:/Developer Mode on/nova-ai/server.py`
- Test: `d:/Developer Mode on/nova-ai/test_audit_logger.py`

**Interfaces:**
- Produces: `log_audit_event(channel: str, tool: str, preview: str, guardian_verdict: str, status: str, cfg: dict = None) -> None`
- Format: JSON Lines appended to `data/audit.jsonl` with ISO-8601 UTC timestamp and masked secrets.

- [x] **Step 1: Write the failing test in `test_audit_logger.py`**
  Asserts that `log_audit_event` creates `data/audit.jsonl`, writes well-formed JSON lines, and masks secrets like `sk-ant-12345` and passwords.

- [x] **Step 2: Run test to verify it fails**
  Run: `python -m unittest test_audit_logger.py`
  Expected: FAIL with `ModuleNotFoundError: No module named 'audit_logger'`

- [x] **Step 3: Implement `audit_logger.py`**
  Implement thread-safe file appending using standard library `threading.Lock()` and secret scrubbing via regex.

- [x] **Step 4: Wire `audit_logger.py` into `server.py`**
  Call `log_audit_event` inside `check_tool_confirmation_required` and tag execution paths.

- [x] **Step 5: Run test to verify it passes**
  Run: `python -m unittest test_audit_logger.py`
  Expected: PASS

---

### Task 2: Multi-Model Fallback Router in `server.py`

**Files:**
- Modify: `d:/Developer Mode on/nova-ai/server.py:440-560`
- Test: `d:/Developer Mode on/nova-ai/test_model_fallback.py`

**Interfaces:**
- Consumes: `cfg["fallback_providers"]` (list of provider names, e.g. `["gemini", "anthropic", "openai", "ollama"]`)
- Produces: `call_llm_with_fallback(cfg: dict, prompt: str, system_prompt: str) -> str`

- [x] **Step 1: Write the failing test in `test_model_fallback.py`**
  Mock primary provider returning HTTP 429 / Timeout; assert router automatically invokes secondary provider and returns secondary response without error.

- [x] **Step 2: Run test to verify it fails**
  Run: `python -m unittest test_model_fallback.py`
  Expected: FAIL with missing fallback mechanism.

- [x] **Step 3: Implement `call_llm_with_fallback` in `server.py`**
  Catch `urllib.error.HTTPError` (429, 500, 502, 503, 504) and `TimeoutError`; cycle through `fallback_providers` using corresponding encrypted keys (`anthropic_api_key`, `gemini_api_key`, etc.) while enforcing total timeout under 90s.

- [x] **Step 4: Run test to verify it passes**
  Run: `python -m unittest test_model_fallback.py`
  Expected: PASS

---

### Task 3: Guardian AI Safety Reviewer (`guardian_agent.py`)

**Files:**
- Create: `d:/Developer Mode on/nova-ai/guardian_agent.py`
- Modify: `d:/Developer Mode on/nova-ai/server.py:1184-1267`
- Test: `d:/Developer Mode on/nova-ai/test_guardian_agent.py`

**Interfaces:**
- Produces: `review_command_safety(cfg: dict, tool_name: str, argument: str) -> tuple[bool, str]`
- Returns: `(is_safe: bool, reason: str)`

- [x] **Step 1: Write the failing test in `test_guardian_agent.py`**
  Test dangerous commands (`rm -rf`, `mkfs`, format) fail regex rails; test read-only commands (`dir`, `ls`, `git status`) are recognized as `SAFE`.

- [x] **Step 2: Run test to verify it fails**
  Run: `python -m unittest test_guardian_agent.py`
  Expected: FAIL with `ModuleNotFoundError: No module named 'guardian_agent'`

- [x] **Step 3: Implement `guardian_agent.py`**
  Implement regex pattern rails and secondary LLM evaluation using stdlib `urllib.request`. Fail-closed on error.

- [x] **Step 4: Wire into `server.py:check_tool_confirmation_required`**
  Include Guardian verdict in confirmation preview string. Support `"guardian_auto_approve_safe": false` (default false).

- [x] **Step 5: Run test to verify it passes**
  Run: `python -m unittest test_guardian_agent.py`
  Expected: PASS

---

### Task 4: Plan Mode Coordinator (`plan_mode.py`)

**Files:**
- Create: `d:/Developer Mode on/nova-ai/plan_mode.py`
- Modify: `d:/Developer Mode on/nova-ai/server.py`
- Test: `d:/Developer Mode on/nova-ai/test_plan_mode.py`

**Interfaces:**
- Produces: `parse_plan_tag(arg: str) -> dict` and `execute_plan_batch(plan: dict, cfg: dict) -> list[str]`
- Tool Tag: `[[PLAN: title | step 1 | step 2 ...]]`

- [x] **Step 1: Write the failing test in `test_plan_mode.py`**
  Test plan parsing, step extraction, and sequential step execution with error abort.

- [x] **Step 2: Run test to verify it fails**
  Run: `python -m unittest test_plan_mode.py`
  Expected: FAIL with `ModuleNotFoundError`

- [x] **Step 3: Implement `plan_mode.py`**
  Implement parsing, step execution state machine, and error short-circuiting.

- [x] **Step 4: Register `PLAN` tool tag in `server.py`**
  Add `PLAN` to system prompt tool specifications and dispatch in `run_skill`.

- [x] **Step 5: Run test to verify it passes**
  Run: `python -m unittest test_plan_mode.py`
  Expected: PASS

---

### Task 5: Telegram Remote Gateway (`telegram_gateway.py`)

**Files:**
- Create: `d:/Developer Mode on/nova-ai/telegram_gateway.py`
- Modify: `d:/Developer Mode on/nova-ai/server.py`
- Test: `d:/Developer Mode on/nova-ai/test_telegram_gateway.py`

**Interfaces:**
- Produces: `start_telegram_daemon(cfg: dict, chat_callback: callable) -> TelegramGateway`
- Daemon polling: Standard library `urllib.request` long polling against `https://api.telegram.org/bot<TOKEN>/getUpdates`.

- [x] **Step 1: Write the failing test in `test_telegram_gateway.py`**
  Mock Telegram API responses; test message ingestion, chat ID whitelisting, silent turn delivery (`source="telegram"`), and rejection of unauthorized chat IDs.

- [x] **Step 2: Run test to verify it fails**
  Run: `python -m unittest test_telegram_gateway.py`
  Expected: FAIL with `ModuleNotFoundError`

- [x] **Step 3: Implement `telegram_gateway.py`**
  Implement long-poll worker thread, `/allow` and `/deny` remote action confirmation, and message sender.

- [x] **Step 4: Wire into server startup in `server.py`**
  Start gateway thread if `"telegram_enabled": true` in `config.json`.

- [x] **Step 5: Run test to verify it passes**
  Run: `python -m unittest test_telegram_gateway.py`
  Expected: PASS

---

### Task 6: Extensible Plugin & Connector Engine (`integrations/`)

**Files:**
- Create: `d:/Developer Mode on/nova-ai/integrations/__init__.py`
- Create: `d:/Developer Mode on/nova-ai/integrations/github_connector.py`
- Modify: `d:/Developer Mode on/nova-ai/server.py`
- Test: `d:/Developer Mode on/nova-ai/test_integrations.py`

**Interfaces:**
- Produces: `load_integrations() -> list[BaseIntegration]`
- Tool: `[[GITHUB: owner/repo | issues/prs]]`

- [x] **Step 1: Write the failing test in `test_integrations.py`**
  Test plugin loader scans directory and ignores missing packages; mock GitHub API call and test repository inspection.

- [x] **Step 2: Run test to verify it fails**
  Run: `python -m unittest test_integrations.py`
  Expected: FAIL

- [x] **Step 3: Implement `integrations/__init__.py` and `github_connector.py`**
  Implement clean base protocol and stdlib GitHub REST client (`urllib.request`).

- [x] **Step 4: Register GitHub tool in `server.py:run_skill`**
  Connect `GITHUB` skill to `github_connector.run`.

- [x] **Step 5: Run test to verify it passes**
  Run: `python -m unittest test_integrations.py`
  Expected: PASS

---

### Task 7: Server-Sent Events (SSE) Streaming Endpoint (`/api/chat/stream`)

**Files:**
- Modify: `d:/Developer Mode on/nova-ai/server.py:3230-3330`
- Test: `d:/Developer Mode on/nova-ai/test_chat_stream.py`

**Interfaces:**
- Route: `GET /api/chat/stream?text=...&mode=...` returning `Content-Type: text/event-stream`
- Emits: `data: {"type": "chunk", "text": "..."}\n\n`, `data: {"type": "done"}\n\n`

- [x] **Step 1: Write the failing test in `test_chat_stream.py`**
  Connect via HTTP GET to `/api/chat/stream`; assert response is SSE format and tool tags are buffered.

- [x] **Step 2: Run test to verify it fails**
  Run: `python -m unittest test_chat_stream.py`
  Expected: FAIL with 404 or missing endpoint.

- [x] **Step 3: Implement `/api/chat/stream` in `server.py`**
  Stream SSE events with sliding window tag buffer.

- [x] **Step 4: Run test to verify it passes**
  Run: `python -m unittest test_chat_stream.py`
  Expected: PASS

---

### Task 8: Full Regression Suite Verification

- [x] **Step 1: Run complete Python unittest suite**
  Run: `python -m unittest discover -p "test_*.py"`
  Expected: All 116+ unit tests pass with 0 failures. (143 passed)

- [x] **Step 2: Run Node.js voice regression suite**
  Run: `node test_voice_regression.js`
  Expected: All 6 real app.js voice regression tests pass. (6/6 passed)

- [x] **Step 3: Verify zero external pip packages**
  Confirm no `pip install` commands were run and all implementations use stdlib only. (Verified)
