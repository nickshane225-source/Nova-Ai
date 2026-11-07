---
name: cloud-security-basics
description: Audit cloud security posture across IAM least privilege, public storage, network ACLs, and encryption.
triggers: cloud security, aws security, azure security, gcp security, iam least privilege, s3 bucket security, ক্লাউড সিকিউরিটি
---

> **Guardrail:** Defensive, educational, and authorized use only. Confirm written authorization before testing any system the user does not own. Do not produce working malware, ransomware, credential theft tools, or attack tooling against unauthorized targets. Focus on understanding, detection, prevention, and remediation.

## When to use
Use when reviewing cloud configurations (AWS, Azure, GCP), establishing security baselines, hardening IAM policies, or auditing public resource exposure.

## Procedure
1. **Enforce Identity & Access Management (IAM) least privilege**: Remove wildcard permissions (`*`); bind policies to roles rather than users; enforce mandatory MFA on all human accounts.
2. **Audit public storage exposure**: Inspect cloud object storage (AWS S3, Azure Blob, GCS) to ensure public read/write access is blocked unless explicitly intended for static assets.
3. **Establish secure network perimeters**: Restrict virtual network security groups (AWS SG, Azure NSG, GCP VPC firewall); close administrative ports (22, 3389) to the public internet (`0.0.0.0/0`).
4. **Mandate encryption at rest and in transit**: Enforce customer-managed or cloud-provider KMS encryption across databases, disk volumes, and storage buckets; enforce HTTPS/TLS on API gateways.
5. **Enable centralized audit logging and alerts**: Turn on CloudTrail, Azure Activity Log, or GCP Cloud Audit Logs; configure real-time alerts for root account usage or policy modifications.
6. **Review the Shared Responsibility Model**: Differentiate customer obligations (data protection, identity, app security) from cloud provider infrastructure responsibilities.

## Checklist
- [ ] Is root/subscription administrator usage protected by hardware MFA?
- [ ] Are all public cloud storage buckets verified against unintended public access?
- [ ] Are administrative ports (SSH/RDP) blocked from `0.0.0.0/0`?
- [ ] Is multi-region audit logging turned on with tamper-proof storage?

## Output format
Cloud Security Assessment Matrix: Cloud Provider, Resource Category, Configuration Risk, Recommended Hardening.

## Example
| Provider | Resource | Risk Identified | Hardening Action |
| :--- | :--- | :--- | :--- |
| AWS | IAM Role `app-worker` | Policy contains `s3:*` on all resources | Restrict to `s3:GetObject` on specific bucket ARN |
| AWS | S3 Bucket `data-backups`| Public Read ACL enabled | Enable "Block Public Access" at account and bucket level |
