---
name: network-defense
description: Implement network hardening, segmentation, intrusion detection rules (Snort/Suricata concepts), and telemetry logging.
triggers: network defense, firewall, hardening, snort, suricata, segmentation, ids, ips, নেটওয়ার্ক
---

# Network Defense & Hardening (Defensive & Educational)

> **Guardrail:** Defensive, educational, and authorized use only. Confirm written authorization before testing any system the user does not own. Do not produce working malware, ransomware, credential theft tools, or attack tooling against unauthorized targets. Focus on understanding, detection, prevention, and remediation.

Establish and maintain layered defense-in-depth across enterprise or local network architectures:

### Step 1: Perimeter Hardening & Egress Filtering
- Enforce strict default-deny ingress and egress firewall rules.
- Restrict outbound connections on standard administrative ports (SSH 22, RDP 3389, SMB 445, DNS 53 except to authorized forwarders).

### Step 2: Network Segmentation & Micro-Segmentation
- Isolate critical servers, IoT devices, guest Wi-Fi, and user workstations into dedicated VLANs.
- Enforce jump-box / bastion host architecture with multi-factor authentication for server management.

### Step 3: Intrusion Detection & Prevention (IDS/IPS)
- Formulate detection signatures for Snort/Suricata to catch anomalous protocols and known exploit patterns.
- Deploy Zeek (Bro) for connection metadata analysis.

### Step 4: Encrypted Protocols & Certificate Governance
- Enforce TLS 1.3 for internal and external communications.
- Disable deprecated ciphers (RC4, 3DES, SSLv3, TLS 1.0/1.1).
- Implement DNS-over-HTTPS (DoH) / DNS-over-TLS (DoT) to prevent DNS spoofing.

### Step 5: Centralized Logging & Telemetry
- Aggregate NetFlow/IPFIX, firewall logs, and DHCP/DNS queries into a central SIEM for automated behavioral analysis.
