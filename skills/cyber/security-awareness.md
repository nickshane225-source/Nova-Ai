---
name: security-awareness
description: Create engaging security awareness training modules on phishing, password hygiene, and incident reporting.
triggers: security awareness, phishing training, password hygiene, mfa training, social engineering defense, সিকিউরিটি সচেতনতা
---

> **Guardrail:** Defensive, educational, and authorized use only. Confirm written authorization before testing any system the user does not own. Do not produce working malware, ransomware, credential theft tools, or attack tooling against unauthorized targets. Focus on understanding, detection, prevention, and remediation.

## When to use
Use when designing enterprise security awareness campaigns, educating teams on phishing recognition, drafting password policies, or designing security training quizzes.

## Procedure
1. **Identify audience and cultural context**: Tailor training scenarios to specific organizational roles (finance, HR, engineering, general staff) and localized languages (English, Bengali, Hindi, Urdu).
2. **Teach practical phishing recognition**: Explain telltale social engineering cues: artificial urgency, unexpected sender domains, generic greetings, and suspicious attachment formats (.iso, .hta, .vbs, password-protected zips).
3. **Promote password and MFA hygiene**: Encourage passphrases (3-4 random words), dedicated password managers, and phishing-resistant MFA (FIDO2/WebAuthn or authenticator apps; discourage SMS).
4. **Establish safe browsing and clean desk habits**: Emphasize locking workstations when away (`Win+L`), avoiding unknown USB devices, and verifying HTTPS padlock details.
5. **Standardize an easy incident reporting process**: Ensure employees know the exact button or address to report suspicious emails or behaviors without fear of penalty.
6. **Deploy interactive scenarios and quizzes**: Use short, realistic scenario questions to reinforce learning and track participation metrics.

## Checklist
- [ ] Are training concepts translated into clear, jargon-free localized language?
- [ ] Is reporting framed constructively without punitive language?
- [ ] Are real-world phishing indicators clearly illustrated?
- [ ] Does training emphasize modern phishing-resistant MFA?

## Output format
Security Awareness Module: Topic, Learning Objective, Key Guidance, Practical Scenario & Quiz.

## Example
```markdown
### Spotting Suspicious Email Links
**Rule**: Always inspect the sender domain and hover over links before clicking.
**Scenario**: You receive an email from `billing@paypa1-support.com` stating: *"Account suspended. Verify within 1 hour."*
**Analysis**:
- High urgency ("within 1 hour") is a classic social engineering pressure tactic.
- The domain replaces the letter 'l' with the number '1' (`paypa1`).
**Action**: Do not click. Use the "Report Phishing" button in your email client immediately.
```
