---
name: plan-before-code
description: Clarify requirements, inspect project structure, identify files to touch, and produce an actionable plan before implementing.
triggers: plan, planning, feature planning, new feature, roadmap, build plan, implementation plan, planning steps, পরিকল্পনা
---

# Plan Before Code

Follow this procedure before implementing any multi-step feature or architectural change:

### Step 1: Clarify the Goal & Invariants
- Identify the explicit user goal, functional requirements, and edge cases.
- Confirm critical project invariants (e.g. zero pip dependencies, mode isolation, backward compatibility).

### Step 2: Explore Context & Inspect Existing Files
- Read existing implementations and schemas using `[[READ_FILE: path]]` and `[[LIST_FILES: path]]`.
- Do not assume file structures or component names—verify on disk first.

### Step 3: Outline Affected Files
- Enumerate every file that will be created, modified, or deleted.
- Detail specific functions, routes, and data models to touch.

### Step 4: Step-by-Step Task Breakdown
- Draft sequential, bite-sized tasks.
- For each task, define clear completion and verification criteria.

### Step 5: Execute & Verify Methodically
- Work through the plan task-by-task.
- Test at each stage before moving to the next item.
