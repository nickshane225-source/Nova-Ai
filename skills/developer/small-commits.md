---
name: small-commits
description: Structure changes into atomic, focused logical units with clear conventional commit messages.
triggers: commit, git commit, atomic, patch, small commit, atomic commit, গিট, কমিট
---

# Small Atomic Commits

Maintain a clean, bisectable revision history by committing focused, logical increments:

### Step 1: Isolate Single Responsibility
- Ensure each commit addresses one coherent task (e.g. one bugfix, one feature, or one test addition).
- Do not mix unrelated refactorings or formatting changes with functional modifications.

### Step 2: Verify Working State
- Run tests before staging. Never commit code that breaks the build or fails existing tests.

### Step 3: Stage Explicit Files
- Stage specific files using `git add <file>`, avoiding broad `git add .` to prevent staging unintended artifacts.

### Step 4: Write Conventional Commit Message
- Structure commit messages clearly:
  - `feat(<scope>): concise imperative summary`
  - `fix(<scope>): describe problem and remedy`
  - `test(<scope>): add unit test coverage`
  - `refactor(<scope>): code cleanup without behavior change`

### Step 5: Verify Status
- Run `git status` to ensure working tree is clean.
