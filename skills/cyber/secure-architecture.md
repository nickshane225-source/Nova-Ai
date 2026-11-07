---
name: secure-architecture
description: Design layered defense-in-depth, zero trust boundaries, network segmentation, and secure key management.
triggers: secure architecture, zero trust, defense in depth, security architecture, network segmentation, সিকিউর আর্কিটেকচার
---

> **Guardrail:** Defensive, educational, and authorized use only. Confirm written authorization before testing any system the user does not own. Do not produce working malware, ransomware, credential theft tools, or attack tooling against unauthorized targets. Focus on understanding, detection, prevention, and remediation.

## When to use
Use when architecting enterprise or cloud infrastructure, designing microservices boundaries, or applying zero-trust security models.

## Procedure
1. **Apply Zero Trust principles**: Assume breach; enforce explicit verification on every transaction, user, and device regardless of network location.
2. **Implement Defense in Depth**: Layer redundant security controls across physical, perimeter, network, endpoint, application, and data tiers.
3. **Establish micro-segmentation boundaries**: Partition networks into isolated zones (DMZ, application, database); enforce strict firewall ACLs preventing lateral movement.
4. **Enforce secure default configurations**: Disable unused services, ports, and default credentials; mandate least privilege on system accounts.
5. **Centralize secrets and key management**: Store credentials, TLS certificates, and API keys in dedicated encrypted vaults with automated rotation policies.
6. **Integrate continuous monitoring and recovery**: Deploy automated telemetry logging, anomaly detection, and immutable backup infrastructure.

## Checklist
- [ ] Is authentication and authorization required for all internal service-to-service calls?
- [ ] Are databases and storage tiers isolated behind non-routable private subnets?
- [ ] Are secrets managed outside source code repositories?
- [ ] Are backups immutable and tested regularly for recovery?

## Output format
- **Layered Security Architecture Diagram**: Text-based breakdown of security tiers.
- **Security Control Checklist**: Tier, Control Implemented, Invariant Enforced.

## Example
```markdown
[Internet] -> (WAF / Cloudflare)
                 |
             [DMZ Zone] -> (Reverse Proxy / Envoy Gateway)
                              |  (mTLS + Strict JWT Auth)
                          [App Zone] -> (Isolated Microservices)
                                           |  (Database Credentials via Vault)
                                       [Data Zone] -> (Private DB / AES-256 Storage)
```
