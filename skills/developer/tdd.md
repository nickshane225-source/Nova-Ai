---
name: tdd
description: Test-Driven Development procedure: write a failing test first, write minimal code to pass, then refactor.
triggers: test, tdd, unit test, failing test, test driven, unittest, টেস্ট
---

# Test-Driven Development (TDD)

Apply disciplined test-driven engineering whenever implementing new functionality or fixing bugs:

### Step 1: Write a Failing Test (RED)
- Create or expand a test case in `test_*.py` using standard library `unittest`.
- Define expected inputs, outputs, and boundary conditions.
- Execute `python -m unittest test_<name>.py` and verify it fails for the expected reason.

### Step 2: Implement Minimal Solution (GREEN)
- Write the minimal, cleanest standard library code needed to make the test pass.
- Avoid premature optimization or unneeded abstractions.
- Re-run the test to confirm it now passes with exit code 0.

### Step 3: Refactor Cleanly (REFACTOR)
- Improve variable naming, modularity, and readability.
- Eliminate duplication while ensuring the test suite remains 100% green.

### Step 4: Regression Check
- Run the full suite (`python -m unittest discover -p "test_*.py"`) to guarantee existing behavior is unchanged.
