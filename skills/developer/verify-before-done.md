---
name: verify-before-done
description: Run verification commands and show concrete test evidence before claiming any task is complete.
triggers: verify, done, complete, finish, tests pass, evidence, শেষ, সম্পন্ন
---

# Verify Before Done

Never claim work is complete, passing, or fixed without running verification commands and presenting evidence:

### Step 1: Identify Verification Gates
- Determine which unit tests, build commands, or syntax checks validate the work.
- If no test exists for the new behavior, write one first.

### Step 2: Execute Test Suite
- Run `python -m unittest discover -p "test_*.py"` or targeted test runner.
- Execute syntax check (`python -m py_compile <files>`) to rule out parsing errors.

### Step 3: Inspect Actual Command Output
- Verify that exit code is 0.
- Check the exact test count and confirm 0 failures and 0 errors.

### Step 4: Present Evidence Before Assertions
- Quote the specific output lines (e.g. `Ran 34 tests in 10.896s: OK`).
- Only after evidence is verified, conclude that the task is finished.
