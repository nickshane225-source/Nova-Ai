# Nova AI - Security Notes & Residual Risks by Design

**Version:** Security-Hardened 2.0  
**Branch:** `security-hardening`  
**Date:** November 2026  

---

## 1. Overview
Nova AI has undergone extensive security hardening, eliminating all 45 Critical, High, and Medium vulnerabilities identified during the comprehensive A-to-Z audit. This document articulates the residual risks that remain **by design** as fundamental properties of a local desktop AI pair programming assistant, along with the protective controls and mitigations implemented for each.

---

## 2. Residual Risks by Design

### 2.1 Local Loopback & OS Privilege Model
* **Risk Description:** Nova AI operates as a desktop service bound to loopback interfaces (`127.0.0.1:8765` and `127.0.0.1:8766`) under the privileges of the active operating system user.
* **Threat Profile:** Any malicious software or untrusted binary already executing locally with user privileges on the host machine could theoretically interact with loopback ports or access local user files.
* **Mitigating Controls:**
  - Strict loopback validation (`_local_only()`) preventing DNS rebinding, remote host spoofing, and LAN access.
  - Dual-tier authentication requiring both an HTTP-only SameSite cookie (`nova_session`) and an ephemeral API header (`X-Nova-Token`).
  - Zero plaintext persistence of boot authentication codes. Boot codes exist in memory only and expire automatically after 5 minutes or single use.
  - Rate-limited 401 boot code minting (maximum 1 mint per 60 seconds, capped at 5 live codes).

### 2.2 User-Confirmed Destructive Operations
* **Risk Description:** Nova AI is designed to automate software engineering workflows, including creating projects, running build scripts, and executing system commands. By design, Nova permits these operations when explicitly approved by the user.
* **Threat Profile:** If a user is socially engineered or carelessly approves a dangerous command presented in the confirmation modal, Nova will execute it.
* **Mitigating Controls:**
  - Unified pending action gateway (`create_pending_action()`) enforcing 2,000-character caps, preview sanitization, secret masking, and provenance tracking.
  - Dual-engine Guardian Agent safety classifier reviewing all commands; commands classified as `DANGEROUS` or encountering classifier errors fail closed.
  - Action tags in tainted turns or originating from remote gateways (Telegram, Discord, mobile, automations) are strictly gated.
  - Remote confirmation restricts oversized or complex actions to PC-only confirmation.

### 2.3 LLM Non-Determinism and Indirect Prompt Injection
* **Risk Description:** Large Language Models are inherently probabilistic. Malicious third-party data (web pages, git repositories, external documentation) may contain adversarial indirect prompt injections designed to hijack the model's instructions.
* **Threat Profile:** Injected text may attempt to instruct the model to execute unwanted action tags or exfiltrate private data.
* **Mitigating Controls:**
  - **Sticky Conversation Taint:** Once untrusted external data enters a conversation, the conversation is permanently marked tainted until explicitly cleared by the user.
  - **Tool Output Isolation:** All tool feedback is wrapped inside `<UNTRUSTED_TOOL_OUTPUT>` blocks, action tag delimiters (`[[` and `]]`) are neutralized, angle brackets are stripped, and content is truncated.
  - **Strict Tainted Gating:** In a tainted conversation, `SEARCH`, `READ_FILE`, `VISION`, browser interaction, and all write operations require explicit user approval. The `<=80` character search exemption has been removed.
  - **Entropy & Secret Exfiltration Backstop:** Unconfirmed search queries are inspected for high-entropy tokens (base64/hex tokens >= 20 characters), tainted file content shingles, and a hard limit of 5 unconfirmed queries per conversation.

### 2.4 External Skills Isolation
* **Risk Description:** Users may install community or repository skills via GitHub integration. External skills could contain malicious prompts or disguised commands.
* **Threat Profile:** Third-party skills attempting to masquerade as trusted system procedures or overwrite bundled engineering skills.
* **Mitigating Controls:**
  - **ASCII Whitelist & Path Containment:** Skill names are strictly constrained to `^[A-Za-z0-9_-]{1,64}$`, Windows reserved device names are blocked, and path traversal is refused.
  - **Bundled Skill Protection:** User skills are strictly prevented from replacing or overriding bundled skills.
  - **Mandatory Approval & Integrity Tracking:** Installing external skills always requires confirmation showing the full skill body and SHA-256 hash. Hashes are recorded in `data/skills_manifest.json`; tampered on-disk files are ignored until re-approved.
  - **Prompt Quarantining:** External skills are injected exclusively within `<UNTRUSTED_SKILL_DATA>` blocks with live tags neutralized and character caps enforced (4,000 chars per skill, 12,000 chars total).

### 2.5 Sandboxed Read-Only Git Diagnostics
* **Risk Description:** Nova allows interacting with local git repositories via `[[GIT: ...]]`. Malicious repositories can exploit git features (such as `core.fsmonitor` hooks or credential helpers).
* **Threat Profile:** Arbitrary code execution triggered via git hooks or config manipulation during repository inspection.
* **Mitigating Controls:**
  - Subcommands are restricted strictly to read-only diagnostics (`status`, `log`, `diff`, `show`, `clone`). Destructive or mutative subcommands (`commit`, `push`, `branch`, `checkout -b`) are refused immediately.
  - Invocations enforce `--no-optional-locks`, `-c core.hooksPath=NUL`, `-c core.fsmonitor=false`, and `-c protocol.ext.allow=never`.
  - All `GIT_*` environment variables are stripped prior to execution.

---

## 3. Summary of Design Guarantees
1. **Zero Unauthenticated Access:** No API route can be invoked without a valid authenticated session.
2. **Zero Plaintext Persistence of Auth Codes:** Authentication codes exist solely in memory.
3. **Zero Untrusted Code Execution Without Approval:** All executable commands and tainted file access require explicit user confirmation.
4. **Zero Path Traversal:** File access is confined to `workspace/` unless explicit configuration allows broader access, with system-critical directories permanently excluded.
