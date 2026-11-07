---
name: project-conventions
description: Enforce Nova AI architectural invariants: zero external dependencies, strict mode separation, multilingual mirroring, and test coverage.
triggers: conventions, project conventions, blueprint, codebase rules, zero dependency, standards, coding standards, নিয়ম, নীতি
---

# Nova AI Project Conventions

Strictly adhere to the core design principles defined in Nova AI's Master Blueprint:

### Invariant 1: Zero External Dependencies
- The backend runs exclusively on the Python 3.8+ Standard Library.
- Never add external pip dependencies (`pip install`). Use built-in modules (`socket`, `urllib`, `sqlite3`, `ctypes`, `threading`, `json`, `re`, `subprocess`, `hashlib`).

### Invariant 2: Strict Mode Separation
- Developer Mode and Cyber Mode operate with isolated conversation memory (`HISTORIES["developer"]` vs `HISTORIES["cyber"]`).
- Skills, tools, and prompts from one mode must never leak into the other.

### Invariant 3: Multilingual Consistency
- Always detect and mirror the user's spoken or typed language (English, Bengali, Hindi, Urdu, Spanish, French, etc.) based on `cfg.get("language")` and input detection.

### Invariant 4: Preserve UI & Visual Identity
- Do not alter existing layout, fonts, spacing, or component hierarchies of Developer Mode.
- Cyber Mode theme is applied strictly via color overrides (`.cyber-mode`).

### Invariant 5: Test Verification Gate
- Every feature or bugfix must be accompanied by automated unit tests.
- Verify `python -m unittest discover -p "test_*.py"` completes with 100% pass rate.
