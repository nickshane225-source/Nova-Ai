---
name: refactor-safely
description: Safely refactor code to improve structure, maintainability, and clarity without altering observable behavior.
triggers: refactor, clean up, restructure, simplify, optimize, রিফ্যাক্টর
---

# Refactor Safely

Improve internal code quality while guaranteeing that external behavior and interfaces remain invariant:

### Step 1: Establish Green Test Baseline
- Run the full test suite (`python -m unittest discover`) before touching a single line.
- Confirm all tests pass with zero failures.

### Step 2: Apply Small, Incremental Transformations
- Make one atomic change at a time:
  - Extract a helper function.
  - Simplify conditional branching.
  - Replace magic numbers with named constants.
- Avoid batching multiple structural changes simultaneously.

### Step 3: Verify Continuously
- Run the test suite immediately after each transformation.
- If a test fails, revert or fix immediately before continuing.

### Step 4: Preserve Public Signatures
- Keep function names, argument order, default values, and return types backward-compatible.

### Step 5: Clean Up Dead Code
- Remove unused variables or obsolete imports cleanly.
