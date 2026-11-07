---
name: incident-response
description: Guide incident response lifecycle: preparation, identification, containment, eradication, recovery, and post-incident review (PICERL).
triggers: incident, breach, compromised, hacked, ransomware incident, ir, containment, ইন্সিডেন্ট
---

# Incident Response Lifecycle (Defensive & Educational)

> **Guardrail:** Defensive, educational, and authorized use only. Confirm written authorization before testing any system the user does not own. Do not produce working malware, ransomware, credential theft tools, or attack tooling against unauthorized targets. Focus on understanding, detection, prevention, and remediation.

Execute a structured, calm response to an ongoing or suspected security incident following the PICERL framework:

### Step 1: Identification & Triage
- Confirm the incident scope: affected hosts, user accounts, and sensitive data assets.
- Preserve volatile evidence (memory dump, process lists, active connections) before shutting down machines.

### Step 2: Containment (Short-term & Long-term)
- Isolate affected network segments or endpoints from the LAN/Internet.
- Disable or revoke compromised Active Directory / IAM credentials and active sessions.
- Block malicious C2 IPs and domains at the border firewall and DNS resolver.

### Step 3: Eradication
- Identify and remove all persistence mechanisms (scheduled tasks, web shells, unauthorized SSH keys).
- Patch the root-cause entry vector that enabled initial access.

### Step 4: Recovery & Validation
- Restore affected systems from verified clean, offline backups.
- Monitor enhanced logging telemetry for reinfection attempts before returning systems to production.

### Step 5: Post-Incident Review & Lessons Learned
- Compile a comprehensive post-mortem: detailed timeline, root cause analysis, total impact, and preventative roadmap.
