---
name: secure-code-review
description: Audit source code for injection vectors, authentication flaws, exposed secrets, insecure deserialization, and dangerous sinks.
triggers: secure code review, audit vulnerability, sqli, xss, sanitize, owasp, secrets, সিকিউরিটি, সিকিউর কোড
---

# Secure Code Review (Defensive & Educational)

> **Guardrail:** Defensive, educational, and authorized use only. Confirm written authorization before testing any system the user does not own. Do not produce working malware, ransomware, credential theft tools, or attack tooling against unauthorized targets. Focus on understanding, detection, prevention, and remediation.

Follow this systematic procedure to audit source code for vulnerabilities and prescribe robust defenses:

### Step 1: Input Validation & Injection Sinks
- Search for unparameterized SQL queries, dynamic command construction (`shell=True`, `subprocess.Popen` with concatenated strings), and unescaped HTML reflection (XSS).
- Verify input type checking, length constraints, and whitelisting.

### Step 2: Authentication & Authorization Flow
- Review password storage (enforce bcrypt/argon2/PBKDF2; reject MD5/plain SHA-1).
- Inspect session token generation (require cryptographically secure tokens via `secrets`).
- Verify access control checks on every privileged endpoint (prevent IDOR).

### Step 3: Hardcoded Secrets & Cryptographic Hygiene
- Scan for embedded API keys, private keys, passwords, and tokens.
- Ensure cryptographic keys are loaded securely from environment variables or encrypted secret vaults.

### Step 4: Safe Deserialization & Sinks
- Flag dangerous deserialization primitives (`pickle.loads`, `yaml.load` without SafeLoader, `eval()`, `exec()`).
- Recommend structured formats (JSON, Protobuf) with strict schema validation.

### Step 5: Deliver Concrete Remediation
- Present parameterized and sanitized code examples demonstrating exact fixes.
