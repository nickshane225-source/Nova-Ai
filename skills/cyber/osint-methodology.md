---
name: osint-methodology
description: Legal, ethical open-source intelligence collection, digital footprint mapping, source verification, and privacy preservation.
triggers: osint, recon, intelligence, open source, passive reconnaissance, footprinting, ওসিন্ট
---

# OSINT Methodology (Defensive & Educational)

> **Guardrail:** Defensive, educational, and authorized use only. Confirm written authorization before testing any system the user does not own. Do not produce working malware, ransomware, credential theft tools, or attack tooling against unauthorized targets. Focus on understanding, detection, prevention, and remediation.

Conduct ethical, passive Open-Source Intelligence gathering while maintaining strict legal and operational boundaries:

### Step 1: Establish Strict Ethical Scope
- Confirm that targets are public and within authorized bounds.
- Never engage in social engineering, unauthorized access, credential stuffing, or intrusive surveillance.

### Step 2: Passive Footprint Mapping
- Domain & DNS Intelligence: inspect public WHOIS, DNS records (A, MX, TXT, SPF/DMARC), and Certificate Transparency logs (crt.sh).
- Infrastructure Mapping: leverage search engines (Shodan/Censys concepts, Google dorking syntax) to identify exposed public services.

### Step 3: Multi-Source Verification
- Cross-reference all discovered artifacts across at least two independent sources.
- Account for misinformation, stale records, or honeypots before reporting.

### Step 4: Operational Security (OpSec)
- Maintain passive posture: do not send active probes to target infrastructure.
- Protect researcher identity using dedicated virtual environments and clean network routing.

### Step 5: Structured Intelligence Reporting
- Synthesize raw data into actionable intelligence with high source reliability ratings.
