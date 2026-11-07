---
name: web-app-security-review
description: Systematic assessment of web applications against OWASP Top 10 vulnerabilities with findings and remedies.
triggers: web app security, owasp top 10, xss review, csrf review, ssrf review, access control review, ওয়েব সিকিউরিটি
---

> **Guardrail:** Defensive, educational, and authorized use only. Confirm written authorization before testing any system the user does not own. Do not produce working malware, ransomware, credential theft tools, or attack tooling against unauthorized targets. Focus on understanding, detection, prevention, and remediation.

## When to use
Use when auditing web applications, validating API security controls, conducting pre-deployment security reviews, or remediating OWASP Top 10 flaws.

## Procedure
1. **Audit Broken Access Control (A01)**: Verify server-side authorization on every endpoint; test IDOR by verifying users cannot access other tenants' resource IDs.
2. **Review Cryptographic Failures (A02)**: Ensure sensitive data in transit uses TLS 1.3; passwords use bcrypt/Argon2; session tokens have high cryptographic entropy.
3. **Inspect Injection Vectors (A03)**: Check SQL, OS command, and LDAP injection surfaces; ensure all database operations use parameterized queries.
4. **Evaluate Insecure Design & Misconfigurations (A04 & A05)**: Review default accounts, exposed debug endpoints, verbose error messages, and missing security headers (CSP, HSTS, X-Frame-Options).
5. **Analyze XSS, CSRF & SSRF Surfaces (A07 & A10)**: Ensure context-aware output encoding on HTML templates; verify anti-CSRF tokens on state-changing requests; validate URL schemes and IP ranges on server-side requests.
6. **Compile Prioritized Findings Table**: Record each issue with vulnerability class, technical evidence, impact, severity, and remediation guidance.

## Checklist
- [ ] Are all authorization decisions enforced server-side?
- [ ] Are SQL queries 100% parameterized with zero string concatenation?
- [ ] Are modern security headers (CSP, HSTS, X-Content-Type-Options) enabled?
- [ ] Are outgoing server requests restricted from querying internal/metadata IPs (`169.254.169.254`, `127.0.0.1`)?

## Output format
OWASP Findings Table: ID, Category, Endpoint/Component, Severity (Critical/High/Med/Low), Remediation.

## Example
| ID | OWASP Category | Component | Severity | Remediation |
| :--- | :--- | :--- | :--- | :--- |
| SEC-01 | A01: Broken Access Control | `/api/user/{id}/profile` | Critical | Validate session user identity matches target `{id}` server-side |
| SEC-02 | A05: Security Misconfig | `HTTP Headers` | Medium | Add `Strict-Transport-Security: max-age=31536000; includeSubDomains` |
