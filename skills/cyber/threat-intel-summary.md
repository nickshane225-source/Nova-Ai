---
name: threat-intel-summary
description: Structure threat intelligence reports: extract IOCs, map TTPs to MITRE ATT&CK, identify threat actors, and recommend defenses.
triggers: threat intel, ioc, ttp, mitre, att&ck, threat actor, apt, থ্রেট ইন্টেল
---

# Threat Intelligence Summary (Defensive & Educational)

> **Guardrail:** Defensive, educational, and authorized use only. Confirm written authorization before testing any system the user does not own. Do not produce working malware, ransomware, credential theft tools, or attack tooling against unauthorized targets. Focus on understanding, detection, prevention, and remediation.

Synthesize raw threat reports, campaign data, or telemetry into structured cyber threat intelligence:

### Step 1: Extract & Classify Indicators of Compromise (IOCs)
- Categorize atomic indicators: SHA256/MD5 file hashes, C2 IP addresses, malicious domains, and registry run-keys.
- Provide structured outputs (STIX/JSON or Markdown tables).

### Step 2: Map TTPs to MITRE ATT&CK
- Map observed adversary behaviors to Enterprise ATT&CK matrix tactics and techniques:
  - Initial Access (e.g. T1566 Phishing)
  - Execution (e.g. T1059 Command and Scripting Interpreter)
  - Persistence & Defense Evasion (e.g. T1078 Valid Accounts)
  - Lateral Movement & Exfiltration

### Step 3: Threat Actor & Campaign Attribution
- Summarize known threat actor aliases, geographic focus, targeted sectors, and primary motivations.

### Step 4: Actionable Detection Signatures
- Scaffold concrete detection rules:
  - Sigma rules for SIEM event logs.
  - YARA signatures for binary/file detection.
  - Snort/Suricata network patterns for C2 beaconing.

### Step 5: Defensive Countermeasures
- Prioritize hardening recommendations to neutralize the observed TTPs.
