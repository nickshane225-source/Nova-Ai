---
name: code-review
description: Review code for correctness, edge cases, readability, security, and performance with severity-ranked findings.
triggers: review, code review, audit, inspect, critique, check code, কোড রিভিউ
---

# Code Review

Perform a thorough, objective review of changed or submitted code:

### Step 1: Correctness & Logic Verification
- Does the code satisfy the exact functional requirement?
- Are off-by-one errors, infinite loops, or unhandled return states present?

### Step 2: Edge Cases & Boundary Handling
- Test handling of empty strings, zero values, special characters, and non-ASCII Unicode (e.g. Bengali).
- Verify resource cleanup (sockets, file descriptors, database connections).

### Step 3: Architecture & Invariant Compliance
- Does it adhere to the zero-dependency rule (standard library only)?
- Does it preserve strict mode isolation between Developer Mode and Cyber Mode?

### Step 4: Rank Findings by Severity
- `[CRITICAL]`: Bugs, data corruption, security exposures, or broken tests.
- `[WARNING]`: Unhandled edge cases, potential performance bottlenecks, or non-idiomatic patterns.
- `[SUGGESTION]`: Readability, style polish, or documentation improvements.

### Step 5: Deliver Actionable Recommendations
- Provide concrete replacement snippets or diffs for any flagged issues.
