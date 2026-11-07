---
name: systematic-debugging
description: Root-cause debugging: reproduce the issue, isolate failure points, form hypotheses, fix the root cause, and add regression tests.
triggers: bug, fix, debug, issue, error, traceback, exception, fail, broken, ক্র্যাশ, বাগ, ফিক্স
---

# Systematic Debugging

Follow this root-cause debugging procedure whenever encountering an error, traceback, or test failure:

### Step 1: Reproduce & Capture Exact Error
- Inspect the exact terminal output, stack trace, or unexpected return value.
- Note line numbers, exception types, and trigger conditions. Do not guess.

### Step 2: Trace & Isolate the Failure Point
- Trace execution backward from the failure point to where invalid state entered.
- Inspect variable values and type assumptions along the path.

### Step 3: Formulate a Single Hypothesis
- State clearly: *"I hypothesize the failure occurs because [condition]."*
- Test this specific hypothesis before making widespread edits.

### Step 4: Implement Surgical Fix
- Address the underlying root cause directly rather than masking symptoms with blanket try/except blocks.
- Preserve existing comments, docstrings, and unrelated code.

### Step 5: Add Regression Test
- Add a dedicated test case that reproduces the issue to ensure it never recurs.
- Verify that the test suite passes completely.
