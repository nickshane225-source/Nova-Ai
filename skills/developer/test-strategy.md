---
name: test-strategy
description: Formulate a comprehensive test strategy covering unit, integration, edge cases, and deterministic testing.
triggers: test strategy, testing strategy, test plan, integration tests, test pyramid, deterministic tests, টেস্ট স্ট্র্যাটেজি, টেস্ট প্ল্যান
---

## When to use
Use when onboarding new modules, designing regression suites, increasing code coverage, or auditing software reliability.

## Procedure
1. **Identify core behaviors and contracts**: Define the critical invariants (e.g. mode separation, standard library compliance, localized output).
2. **Implement fast unit tests**: Test internal functions and pure algorithmic logic using Python's standard `unittest` module with sub-millisecond execution.
3. **Build integration tests for endpoints**: Test HTTP handlers with simulated requests verifying status codes, headers, and payload structures.
4. **Target edge cases and failure paths**: Explicitly test malformed inputs, boundary lengths, empty strings, missing keys, and non-ASCII characters.
5. **Enforce deterministic execution**: Mock non-deterministic dependencies (system clocks, live external network calls, file system locks) so tests pass reliably.
6. **Verify mode-isolation boundaries**: Write automated checks verifying that Developer Mode and Cyber Mode states cannot leak into one another.

## Checklist
- [ ] Does the test suite run fast (<15s) using standard library `unittest`?
- [ ] Are all test cases deterministic and reproducible in any timezone/environment?
- [ ] Are boundary conditions, empty values, and failure paths tested?
- [ ] Do mode-isolation tests assert disjoint sets of state and skills?

## Output format
- **Test Matrix Table**: Feature, Test Level (Unit/Integration), Test Case, Invariant Verified.
- **Runnable Test Code**: Standard library `unittest.TestCase` implementation.

## Example
| Subsystem | Level | Test Case | Target Invariant |
| :--- | :--- | :--- | :--- |
| `skills_engine` | Unit | `test_mode_isolation` | Dev and Cyber skill sets are strictly disjoint. |
| `server.py` | Integration | `test_local_only_guard` | Non-loopback Host headers receive 403 Forbidden. |
| `memory_engine`| Unit | `test_bm25_empty_query` | Empty search queries return default recents. |
