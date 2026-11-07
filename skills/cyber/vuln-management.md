---
name: vuln-management
description: Manage vulnerability lifecycles: scanning, deduplication, contextual risk scoring, and SLA tracking.
triggers: vulnerability management, vuln scan, cvss scoring, patch prioritization, remediation tracking, ভালনারেবিলিটি ম্যানেজমেন্ট
---

> **Guardrail:** Defensive, educational, and authorized use only. Confirm written authorization before testing any system the user does not own. Do not produce working malware, ransomware, credential theft tools, or attack tooling against unauthorized targets. Focus on understanding, detection, prevention, and remediation.

## When to use
Use when processing vulnerability scan results, prioritizing patch cycles, tracking remediation SLAs, or establishing vulnerability management programs.

## Procedure
1. **Maintain comprehensive asset inventory**: Catalog all infrastructure, operating systems, software packages, containers, and web services.
2. **Execute authenticated scans & deduplicate findings**: Run regular vulnerability scans; normalize and aggregate duplicate alerts into distinct issues per asset.
3. **Score risks with environmental context**: Adjust base CVSS scores using exploitability context (e.g. CISA Known Exploited Vulnerabilities - KEV) and asset exposure (Internet-facing vs isolated internal LAN).
4. **Prioritize remediation actions**: Rank items into remediation tiers: Critical (Internet-exposed with public exploit), High, Medium, and Low.
5. **Assign remediation and define SLAs**: Assign tickets to responsible engineering teams with clear resolution timeframes (e.g. Critical: 48h, High: 14d, Medium: 30d).
6. **Verify fixes and maintain governance metrics**: Re-scan remediated assets to confirm patches; report Mean Time to Remediate (MTTR) and open risk exposure.

## Checklist
- [ ] Are scan results correlated against CISA KEV and active exploit intelligence?
- [ ] Does risk prioritization consider internet exposure and network segmentation?
- [ ] Are remediation tickets bounded by enforced SLAs?
- [ ] Is remediation verified with follow-up validation scanning?

## Output format
Prioritized Remediation Plan: CVE/Vulnerability, Asset, Base CVSS, Contextual Priority, Remediation Action, SLA Due Date.

## Example
| CVE | Asset | CVSS | Exposure | Priority | Remediation Action | SLA Due |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| CVE-2024-3400 | `vpn-gateway.corp` | 10.0 | Internet | Critical (Tier 1) | Upgrade firmware to hotfix version | 24 Hours |
| CVE-2023-44487 | `internal-api-01` | 7.5 | Internal | Medium (Tier 3) | Apply HTTP/2 mitigation patch | 30 Days |
