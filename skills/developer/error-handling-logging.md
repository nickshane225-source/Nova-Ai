---
name: error-handling-logging
description: Implement structured logging, explicit exception handling, exponential backoffs, and user-facing messages.
triggers: error handling, logging design, structured logging, exception handling, log levels, retry backoff, এরর হ্যান্ডলিং, লগিং
---

## When to use
Use when handling network calls, filesystem operations, third-party API interactions, or refactoring unhandled try/catch blocks.

## Procedure
1. **Catch explicit exceptions**: Avoid bare `except:`; catch specific exception types (`ConnectionError`, `KeyError`, `TimeoutError`) and handle each appropriately.
2. **Prevent silent swallows**: Always log caught errors with context (timestamp, operation, parameters) unless explicitly designed for graceful fallback.
3. **Configure structured logging**: Use the standard `logging` module with appropriate log levels (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).
4. **Implement network retries with exponential backoff**: When invoking external LLM APIs, retry transient network failures (429, 503) with jittered exponential delay.
5. **Set explicit timeouts everywhere**: Specify socket and HTTP timeouts on every network request (`timeout=10`) to prevent unkillable thread hangs.
6. **Return friendly localized messages**: Present concise, understandable error explanations to the user in their active language while keeping raw tracebacks in backend logs.

## Checklist
- [ ] Are all `try/except` blocks handling explicit, expected exception types?
- [ ] Do all external HTTP and socket connections specify an explicit timeout?
- [ ] Are sensitive tokens, credentials, or keys omitted from log statements?
- [ ] Are user-facing error strings clear and free of raw memory addresses?

## Output format
- **Error Taxonomy**: Exception Type, Root Trigger, Handler Action.
- **Logging Configuration & Code**: Python standard library logging setup.

## Example
```python
import logging, time, urllib.error
logger = logging.getLogger("nova.network")

def fetch_with_retry(req, retries=3, backoff=1.0):
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read()
        except urllib.error.URLError as e:
            if attempt == retries:
                logger.error("Request failed after %d attempts: %s", retries, e)
                raise
            time.sleep(backoff * (2 ** (attempt - 1)))
```
