---
name: ctf-practice
description: Educational walkthrough and conceptual guidance for CTF challenges across Web, Crypto, Forensics, and Reverse Engineering.
triggers: ctf, challenge, capture the flag, hackthebox, tryhackme, pwn, crypto challenge, সিটিএফ
---

# Capture The Flag (CTF) Practice (Defensive & Educational)

> **Guardrail:** Defensive, educational, and authorized use only. Confirm written authorization before testing any system the user does not own. Do not produce working malware, ransomware, credential theft tools, or attack tooling against unauthorized targets. Focus on understanding, detection, prevention, and remediation.

Guide learners through CTF problem solving with deep conceptual understanding rather than spoiling answers:

### Step 1: Classify Challenge Domain
- Identify the problem category:
  - **Web Security**: SQLi, XSS, SSRF, JWT tampering, path traversal.
  - **Cryptography**: RSA math, XOR ciphers, ECB padding oracle, hash collisions.
  - **Forensics**: PCAP packet analysis, memory dumps (Volatility), steganography.
  - **Reverse Engineering**: Static disassembler analysis, decompilation, binary patching.

### Step 2: Surface the Core Principle First
- Explain the underlying theoretical flaw or algorithmic property behind the challenge before touching tools.
- Help the user understand *why* the vulnerability exists.

### Step 3: Guiding Questions & Socratic Hints
- Provide hints that guide the learner's own investigation rather than instantly giving the flag.
- Example: *"What happens if the RSA public exponent e is 3 and the modulus n is significantly larger than the message m?"*

### Step 4: Step-by-Step Tooling & Analysis
- Walk through standard educational tools (Wireshark, CyberChef, Ghidra, Python standard library).
- Emphasize scripting automated solutions cleanly in Python.

### Step 5: Post-Challenge Defense Takeaway
- Conclude every challenge with how a software engineer would patch or avoid that vulnerability in production code.
