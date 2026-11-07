---
name: digital-forensics
description: Follow forensic best practices to preserve volatile artifacts, verify hashes, and reconstruct incident timelines.
triggers: digital forensics, evidence preservation, chain of custody, memory forensics, disk forensics, artifact analysis, ফরেনসিক, ডিজিটাল ফরেনসিক
---

> **Guardrail:** Defensive, educational, and authorized use only. Confirm written authorization before testing any system the user does not own. Do not produce working malware, ransomware, credential theft tools, or attack tooling against unauthorized targets. Focus on understanding, detection, prevention, and remediation.

## When to use
Use during post-breach investigations, evidence preservation, volatility analysis, or forensic artifact extraction from disk and memory dumps.

## Procedure
1. **Preserve volatile data first (Order of Volatility)**: Capture RAM, active network connections, running processes, and temporary memory caches before powering down or rebooting.
2. **Establish legal Chain of Custody**: Document date, time, physical location, acquiring investigator, and evidence serial numbers on formal custody logs.
3. **Acquire forensic bit-stream images**: Create bit-for-bit physical copies (E01 or raw `dd`) of target storage devices using hardware write-blockers.
4. **Calculate and verify cryptographic hashes**: Compute SHA-256 hashes of original media and working copies immediately upon acquisition; confirm match before analysis.
5. **Analyze disk and operating system artifacts**: Parse Windows Registry (Shimcache, Amcache), Event Logs, prefetch files, bash histories, and browser cache data to locate execution evidence.
6. **Reconstruct chronological timelines and report findings**: Produce an objective event timeline correlating artifact activity; maintain factual neutrality without speculation.

## Checklist
- [ ] Was memory acquired before shutting down or disconnecting power?
- [ ] Were bit-stream images verified against SHA-256 acquisition hashes?
- [ ] Are all investigative steps executed exclusively on forensically verified copies?
- [ ] Is every action logged with exact UTC timestamps?

## Output format
- **Evidence Log**: Artifact ID, Source System, SHA-256 Hash, Chain of Custody.
- **Forensic Timeline**: UTC Timestamp, Artifact Source, User / Process, Forensic Significance.

## Example
```markdown
### Evidence Item: DISK-IMG-01
- **Acquired**: 2026-10-31 03:15:00 UTC
- **Source**: Host SRV-APP-02 (NVMe Serial: WD-55219)
- **SHA-256 Hash**: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- **Verification**: Verified identical match between acquisition and working copy.
```
