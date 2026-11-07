---
name: security-hardening
description: Harden application endpoints, file permissions, input validation, and localhost-binding security.
triggers: security hardening, secure endpoints, sanitize input, host check, localhost binding, secure config, হার্ডেনিং, নিরাপত্তা সুরক্ষা
---

## When to use
Use when auditing application architecture, adding network endpoints, handling external file operations, or verifying local process safety.

## Procedure
1. **Enforce credential separation**: Store sensitive API keys exclusively in local environment files (`data/config.json`); never hardcode in source code or emit in log streams.
2. **Validate and sanitize all inputs**: Check type, length, and allowed character sets for every parameter before passing to system commands or file APIs.
3. **Guard filesystem operations**: Resolve paths against approved sandbox roots (`WORKSPACE` or `ROOT`) using `.resolve()` and verify path ancestry to block directory traversal (`../`).
4. **Bind strictly to loopback interface**: Bind server listeners to `127.0.0.1` or `localhost`; never bind to `0.0.0.0` unless intentionally configured for remote access with authentication.
5. **Enforce Host and Origin header validation**: Block cross-site request forgery (CSRF) and DNS rebinding attacks by validating `Host` and `Origin` headers on every incoming HTTP request.
6. **Require confirmation for destructive operations**: Implement an explicit user verification gate before executing file deletion, process termination, or irreversible system actions.

## Checklist
- [ ] Are listeners bound strictly to `127.0.0.1`?
- [ ] Does `_local_only()` inspect both `Host` and `Origin` headers on every API route?
- [ ] Are file paths resolved and verified against directory traversal?
- [ ] Are all API keys masked when returning state payloads to frontend clients?

## Output format
- **Hardening Assessment**: Endpoint/Component, Risk Class, Security Control.
- **Remediation Code**: Concrete code implementation of boundary checks.

## Example
```python
def _local_only(self):
    host = (self.headers.get("Host") or "").split(":")[0]
    origin = self.headers.get("Origin")
    if host not in ("127.0.0.1", "localhost"):
        return False
    if origin and urllib.parse.urlparse(origin).hostname not in ("127.0.0.1", "localhost"):
        return False
    return True
```
