---
name: log-analysis-detection
description: Analyze security event logs, correlate suspicious anomalies, build timelines, and draft Sigma detection rules.
triggers: log analysis, detection engineering, sigma rule, event logs, anomaly detection, siem analysis, লগ অ্যানালিসিস, ডিটেকশন
---

> **Guardrail:** Defensive, educational, and authorized use only. Confirm written authorization before testing any system the user does not own. Do not produce working malware, ransomware, credential theft tools, or attack tooling against unauthorized targets. Focus on understanding, detection, prevention, and remediation.

## When to use
Use when triaging security alerts, investigating suspicious authentication anomalies, inspecting server access logs, or crafting detection signatures.

## Procedure
1. **Identify and collect log sources**: Aggregate relevant telemetry (syslog, Windows Event Logs, web server access logs, firewall flows).
2. **Normalize fields and timestamps**: Align disparate formats into consistent schema fields (timestamp, source IP, user identity, process name, status code).
3. **Isolate anomalies**: Query for outlier patterns: repeated failed logins followed by success, off-hours administrative access, or rare process parentage (e.g. `powershell.exe` spawned by `w3wp.exe`).
4. **Reconstruct incident timelines**: Chronologically order events surrounding the anomalous activity to identify initial entry and lateral movement.
5. **Author Sigma-style detection rules**: Codify detection criteria in generic YAML Sigma syntax for SIEM translation.
6. **Tune detection rules for false positives**: Filter legitimate administrative behavior and background maintenance jobs.

## Checklist
- [ ] Are timestamps normalized to a single standard timezone (UTC)?
- [ ] Are correlated indicators verified across at least two independent log sources?
- [ ] Does the Sigma rule specify explicit positive and negative condition boundaries?
- [ ] Have potential false positive baselines been documented?

## Output format
- **Timeline Table**: Timestamp (UTC), Event Source, User, Action, Indicator.
- **Sigma Detection Rule**: YAML specification with Title, Status, Logsource, Detection, Condition.

## Example
```yaml
title: Suspicious PowerShell Process Spawning from Web Server
status: experimental
logsource:
  category: process_creation
  product: windows
detection:
  selection:
    ParentImage|endswith: '\w3wp.exe'
    Image|endswith: '\powershell.exe'
  condition: selection
level: high
```
