---
name: threat-modeling
description: Model threat boundaries, assets, and data flows using STRIDE to score risks and formulate mitigations.
triggers: threat modeling, stride, data flow diagram, trust boundaries, threat matrix, থ্রেট মডেলিং, ঝুঁকি মূল্যায়ন
---

> **Guardrail:** Defensive, educational, and authorized use only. Confirm written authorization before testing any system the user does not own. Do not produce working malware, ransomware, credential theft tools, or attack tooling against unauthorized targets. Focus on understanding, detection, prevention, and remediation.

## When to use
Use during system design or major feature planning to identify threat boundaries, anticipate attack vectors, and design proactive security controls.

## Procedure
1. **Define assets and trust boundaries**: Inventory critical assets (user credentials, cryptographic keys, databases) and boundary transition points (public internet to DMZ, DMZ to internal network).
2. **Draft a text Data Flow Diagram (DFD)**: Map processes, data stores, external entities, and data flows connecting them.
3. **Apply the STRIDE threat model**: Systematically evaluate each component against Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, and Elevation of Privilege.
4. **Score risks objectively**: Calculate risk scores using qualitative Likelihood $\times$ Impact ratings.
5. **Map defensive mitigations**: Detail controls for every high/critical risk (e.g. mutual TLS, HMAC signatures, rate limiting).
6. **Document residual risks**: Record acknowledged risks and verify compensatory controls.

## Checklist
- [ ] Are all trust boundaries and protocol transitions clearly delimited?
- [ ] Has every STRIDE category been evaluated for critical data paths?
- [ ] Are mitigations assigned to specific architectural components?
- [ ] Are residual risks formally acknowledged?

## Output format
Structured Threat Model Table: Component, STRIDE Category, Threat Description, Impact, Mitigation.

## Example
| Component | STRIDE | Threat Description | Likelihood | Impact | Mitigation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| API Ingress | Spoofing | External site forges requests to local API | Med | High | Validate `Host` & `Origin` headers strictly |
| Config File | Tampering | Unauthorized local user modifies API key | Low | High | Restrict filesystem ACLs (read-only to user) |
