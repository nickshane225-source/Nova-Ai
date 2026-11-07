---
name: security-reporting
description: Produce clear executive and technical security assessment reports without exposing exploit payloads.
triggers: security report, audit report, pentest report, vulnerability report, executive summary security, সিকিউরিটি রিপোর্ট
---

> **Guardrail:** Defensive, educational, and authorized use only. Confirm written authorization before testing any system the user does not own. Do not produce working malware, ransomware, credential theft tools, or attack tooling against unauthorized targets. Focus on understanding, detection, prevention, and remediation.

## When to use
Use when preparing penetration test reports, security audit summaries, executive briefings, or compliance assessments.

## Procedure
1. **Draft an actionable Executive Summary**: Provide non-technical leadership with a concise overview of overall security posture, key risks, and strategic business impact.
2. **Document scope and testing methodology**: Explicitly state assessed IP ranges, domains, dates, rules of engagement, and testing methodologies (e.g. black-box, gray-box).
3. **Structure technical findings by severity**: Categorize findings into Critical, High, Medium, Low, and Informational using CVSS v3.1 scoring.
4. **Detail proof-of-concept evidence without weaponized code**: Provide benign verification artifacts (e.g. harmless string reflection or screenshot) without publishing destructive exploit payloads.
5. **Provide clear, prioritized remediation steps**: Supply developers with concrete code adjustments, configuration settings, and vendor patches.
6. **Include references and retest recommendations**: Cite CVEs, CWEs, and NIST/OWASP documentation; specify retesting milestones after patches are applied.

## Checklist
- [ ] Is the Executive Summary concise and clear for business leadership?
- [ ] Are findings ranked objectively with CVSS scores and impact analysis?
- [ ] Are weaponized exploit codes strictly omitted from the report?
- [ ] Are remediation recommendations actionable with code or config examples?

## Output format
Formal Security Assessment Report: Executive Summary, Scope, Findings Matrix, Detailed Finding Breakdown, Retest Plan.

## Example
```markdown
### Finding SEC-01: Insecure Direct Object Reference (IDOR)
- **Severity**: High (CVSS 7.5 - `CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N`)
- **Impact**: Authenticated user can view sensitive invoices belonging to other organizations.
- **Evidence**: `GET /api/invoices/1042` returned account data for non-associated tenant.
- **Remediation**: Implement tenant ownership validation check in invoice handler.
```
