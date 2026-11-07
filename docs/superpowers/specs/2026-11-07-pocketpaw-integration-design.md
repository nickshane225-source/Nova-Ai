# Design Document: Nova AI Multi-Tier PocketPaw Architecture

**Date:** 2026-11-07  
**Status:** Under User Review (Builder-Verified)  
**Author:** Pair Programming Agent & User  
**Target Project:** Nova AI (`d:\Developer Mode on\nova-ai`)

---

## 1. Executive Summary & Intent

The goal is to integrate the most powerful, battle-tested architectural features of **PocketPaw** into **Nova AI**, creating a unified, multi-tiered AI assistant. 

Nova AI is a voice-first, local JARVIS PC companion built on a strict **zero-pip-dependencies (Python Standard Library only)** foundation. PocketPaw is a heavy, multi-channel autonomous agent framework built on 50+ third-party dependencies (FastAPI, Playwright, LangGraph, Tauri/Rust, etc.).

By adopting the **"All Approaches"** strategy, Nova AI implements a 3-tier hybrid architecture:
- **Tier 1 (Core Stdlib):** 100% Python Standard Library implementations of PocketPaw's premier capabilities (Telegram remote gateway, Guardian AI safety verifier, Plan Mode, Model Fallback Router, Append-Only Audit Log, and Memory Reflection).
- **Tier 2 (Extensible Plugin Engine):** An `integrations/` loader that gracefully discovers optional heavy adapters (Slack Socket Mode, Discord bot SDK, Playwright) if installed, with zero penalties or errors when uninstalled.
- **Tier 3 (Universal Client Gateway):** Standardized SSE/WebSocket streaming endpoints (`/api/chat/stream`) so external frontends (such as native desktop Tauri clients) can bind directly to Nova AI on port 8765.

---

## 2. Core Constraints & Guarantees

1. **Zero Mandatory Pip Packages:** Nova AI out-of-the-box (`run.bat`) MUST run with standard Python 3.11+ without running `pip install` for any core feature.
2. **Strict Developer / Cyber Mode Separation:** Cyber mode tools remain strictly isolated and restricted.
3. **Multilingual Mirroring Intact:** All voice and chat responses must mirror the user's language (English, Bengali, Hindi, Urdu, etc.) across all new channels.
4. **Silent Remote Execution:** Remote messages (from Telegram/mobile) do not blare audio across host PC speakers; they stream silent replies back to the requesting channel.
5. **Backward Compatibility:** All existing 116+ unit tests (`python -m unittest discover -p "test_*.py"`) and Node voice tests (`test_voice_regression.js`) must continue to pass.
6. **No Disruptive UI Redesign:** Web UI keeps its signature canvas particle core, HUD notifications, and existing settings dialog.

---

## 3. Tier 1: Core Standard-Library Implementation (Zero-Pip)

### 3.1 Telegram Remote Gateway (`telegram_gateway.py`)
- **How it works:** A background daemon thread utilizing standard library `urllib.request` that polls the official Telegram Bot API via `getUpdates` (long-polling with 30s timeout).
- **Configuration in `data/config.json`:**
  - `telegram_bot_token`: string (encrypted at rest via DPAPI on Windows).
  - `telegram_allowed_chat_ids`: list of integers (whitelisted user IDs).
  - `telegram_enabled`: boolean (default `false`).
- **Session & Audio Isolation:**
  - Remote user conversations maintain their own session context (`HISTORIES["telegram_{chat_id}"]`).
  - Remote turns set `source="telegram"`, preventing host PC speakers from reading responses aloud.
  - If an action requires confirmation, a prompt with inline confirmation commands (`/allow`, `/deny`) is delivered to Telegram.

### 3.2 Guardian AI Safety Reviewer (`guardian_agent.py`)
- **How it works:** Before executing high-impact tools (`RUN_CODE`, `CMD`, `POWERSHELL`, `ORGANIZE_FILES`), Nova AI performs an automated safety evaluation:
  1. Local regex patterns (`rails.py`) check for immediate forbidden actions (`rm -rf /`, `format`, `dd`).
  2. If clean, an isolated secondary LLM prompt (with `temperature=0.0` and max tokens=64) reviews the exact command and outputs JSON:
     ```json
     {"status": "SAFE" | "DANGEROUS", "reason": "Explanation"}
     ```
- **Execution Authority & Decision (Builder Verified):**
  - **Default:** Human confirmation remains **mandatory** for high-impact tools. The Guardian AI verdict enriches the confirmation prompt (e.g. `[Guardian: SAFE - listing directories only]`) and the audit log.
  - **Opt-in Autonomy:** Users can enable `"guardian_auto_approve_safe": true` in `config.json` to allow verified `SAFE` commands to run autonomously without modal confirmation.

### 3.3 Plan Mode (`plan_mode.py`)
- **Tool Tag:** `[[PLAN: Title | Step 1 | Step 2 | Step 3 ...]]`
- **Execution Lifecycle:**
  - When given complex engineering tasks, Nova AI outputs a `[[PLAN: ...]]` tag.
  - The UI Action HUD and Telegram bot render an interactive checklist.
  - Upon user approval, an execution coordinator runs the steps sequentially, streaming step-level progress updates and halting immediately if any intermediate step fails.

### 3.4 Multi-Model Fallback Router
- **Credential Storage (Builder Verified):** Uses Nova AI's existing encrypted flat key schema in `data/config.json`:
  - `anthropic_api_key`, `gemini_api_key`, `groq_api_key`, `openrouter_api_key`, `custom_api_key`.
- **Failover Logic:**
  - Configurable `fallback_providers: ["gemini", "anthropic", "openai", "ollama"]`.
  - When primary provider encounters HTTP 429 (rate-limit), 500/503 (server error), or read timeout, Nova automatically fails over to the next configured provider without dropping context.

### 3.5 Append-Only Security Audit Log (`data/audit.jsonl`)
- Every execution event is appended to `data/audit.jsonl` with:
  - `timestamp`: ISO-8601 UTC string.
  - `channel`: `web`, `phone`, `telegram`, or `scheduler`.
  - `tool`: tool name (e.g. `RUN_CODE`, `WRITE_FILE`).
  - `preview`: sanitized/masked argument.
  - `guardian`: `SAFE` / `DANGEROUS` / `BYPASS`.
  - `status`: `APPROVED`, `DENIED`, or `EXECUTED`.

### 3.6 Dynamic Memory Reflection & Soul
- Upgrades `memory_engine.py` with periodic background reflection. Every 10 conversation turns, Nova synthesizes durable user facts into SQLite `nova_brain.db`.

---

## 4. Tier 2: Extensible Plugin Engine (`integrations/`)

- A lightweight loader (`integrations/__init__.py`) scans the `integrations/` folder on server startup.
- Inbound adapters (e.g. `discord_bot.py`, `slack_bot.py`) inherit `BaseIntegration` and start background daemons if their optional packages are installed.
- Outbound tools (e.g. `github_connector.py`) register via `skills_engine.py` using standard library `urllib` to inspect GitHub issues/PRs using personal access tokens.

---

## 5. Tier 3: Universal Client & Desktop Interoperability

- **Streaming API (`/api/chat/stream`):**
  - Implements Server-Sent Events (SSE) over standard library `http.server`, eliminating external WebSocket dependencies while providing real-time streaming chunks.
  - Internal tool tags (`[[...]]`) are buffered using a sliding character window so raw tool syntax is never leaked into voice or chat streams.
- Allows external native frontends (Tauri desktop app, mobile PWAs) to interface seamlessly with Nova AI on port 8765.

---

## 6. Implementation Phasing

- **Phase 1: Security & Resiliency Foundation (Tier 1)**
  - Audit Logger (`data/audit.jsonl`).
  - Multi-Model Fallback Router.
  - Guardian AI review logic and regex rails.
- **Phase 2: Plan Mode & Remote Telegram Channel (Tier 1)**
  - `telegram_gateway.py` with session isolation and silent audio handling.
  - `[[PLAN: ...]]` checklist handler and step executor.
- **Phase 3: Extensible Plugin Architecture & GitHub Connector (Tier 2)**
  - `integrations/` dynamic loader.
  - Native GitHub REST connector.
- **Phase 4: Streaming SSE API & Verification (Tier 3)**
  - `/api/chat/stream` SSE endpoint.
  - Full automated regression test suite (`test_*.py`).
