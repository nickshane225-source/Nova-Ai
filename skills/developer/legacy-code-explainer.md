---
name: legacy-code-explainer
description: Analyze, trace, and demystify complex or legacy codebases with structural mapping and refactoring paths.
triggers: legacy code, explain codebase, trace request, understand legacy, code walkthrough, পুরানো কোড, কোড ব্যাখ্যা
---

## When to use
Use when onboarding onto unfamiliar source code, deciphering large monolithic files, or preparing to refactor undocumented legacy modules.

## Procedure
1. **Map external entry points**: Locate where requests, CLI flags, or events enter the system (`main()`, HTTP handler, event loop).
2. **Trace a single request end-to-end**: Follow the exact code path from raw input parsing, validation, business processing, to final response serialization.
3. **Inventory modules and responsibilities**: Create a table mapping source files and classes to their single responsibilities.
4. **Identify hidden state and side effects**: Flag global variables, mutable module-level dictionaries, unmanaged background threads, or unclosed file handles.
5. **Summarize in plain, readable language**: Explain the design intent and operational mechanics without dense jargon.
6. **Propose safe, incremental refactors**: Suggest high-leverage refactorings accompanied by proposed characterization unit tests.

## Checklist
- [ ] Has the end-to-end data lifecycle been mapped from ingress to egress?
- [ ] Are all shared global states and locks identified and documented?
- [ ] Are hidden coupling points between modules exposed?
- [ ] Are characterization tests proposed before any structural refactoring?

## Output format
- **System Flow Diagram**: Text/ASCII or Mermaid trace of a typical transaction.
- **Component Inventory**: File, Main Function, Input, Output, Side Effects.
- **Risk Assessment & Refactoring Roadmap**: Prioritized cleanup items.

## Example
```markdown
### Request Lifecycle: `/api/chat`
1. `Handler.do_POST()` receives JSON `{message: "hi", mode: "developer"}`.
2. `_local_only()` validates `Host: 127.0.0.1` and `Origin`.
3. `server.chat()` delegates to `_chat_inner()` under thread `LOCK`.
4. `skills_engine.build_skill_prompt()` ranks and appends active skills.
5. `call_llm()` queries API; tags are parsed and executed via `run_skill()`.
6. Spoken summary synthesized and returned in JSON response.
```
