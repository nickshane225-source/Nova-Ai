"""
Nova AI - Append-Only Security Audit Logger.
Pure Python standard library (no pip packages).

Appends immutable, timestamped JSON lines to data/audit.jsonl
recording all tool invocations, confirmations, and security verdicts.
Automatically masks secrets, credentials, and API keys.
"""

import datetime
import json
import os
import re
import threading
from pathlib import Path

# Base directories
_ROOT = Path(__file__).resolve().parent
_DATA_DIR = _ROOT / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_DEFAULT_AUDIT_FILE = _DATA_DIR / "audit.jsonl"

_AUDIT_FILE = _DEFAULT_AUDIT_FILE
_LOCK = threading.Lock()

# Secret pattern regexes for automated masking
_SECRET_PATTERNS = [
    re.compile(r"(?:sk-[a-zA-Z0-9_\-]{20,})", re.IGNORECASE),
    re.compile(r"(?:ghp_[a-zA-Z0-9]{20,})", re.IGNORECASE),
    re.compile(r"(?:AIza[0-9A-Za-z-_]{35})", re.IGNORECASE),
    re.compile(r"(?:bearer\s+[a-zA-Z0-9_\-\.]{20,})", re.IGNORECASE),
    re.compile(r"(?:x-token-auth:[a-zA-Z0-9_\-@]+@)", re.IGNORECASE),
    re.compile(r"(?:password\s*[:=]\s*[^\s,;]+)", re.IGNORECASE),
    re.compile(r"(?:api_key\s*[:=]\s*[^\s,;]+)", re.IGNORECASE),
]


def set_audit_file(path: Path | None) -> None:
    """Set custom audit file location (used in tests). Pass None to reset to default."""
    global _AUDIT_FILE
    with _LOCK:
        _AUDIT_FILE = path or _DEFAULT_AUDIT_FILE


def get_audit_file() -> Path:
    """Return the currently configured audit file path."""
    with _LOCK:
        return _AUDIT_FILE


def mask_secrets(text: str) -> str:
    """Mask known secret patterns from command arguments and previews."""
    if not text or not isinstance(text, str):
        return ""
    masked = text
    for pat in _SECRET_PATTERNS:
        masked = pat.sub("[MASKED_SECRET]", masked)
    return masked


def log_audit_event(
    channel: str,
    tool: str,
    preview: str,
    guardian_verdict: str = "NONE",
    status: str = "EXECUTED",
    cfg: dict = None,
) -> dict:
    """
    Appends a security audit entry to the audit log.
    Thread-safe and fail-safe.
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    clean_preview = mask_secrets(preview)
    if len(clean_preview) > 500:
        clean_preview = clean_preview[:500] + "... [truncated]"

    entry = {
        "timestamp": now_utc,
        "channel": str(channel or "unknown").strip().lower(),
        "tool": str(tool or "unknown").strip().upper(),
        "preview": clean_preview,
        "guardian": str(guardian_verdict or "NONE").strip().upper(),
        "status": str(status or "UNKNOWN").strip().upper(),
    }

    with _LOCK:
        target_path = _AUDIT_FILE
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            # Audit logger must never crash the main application
            print(f"[Nova Audit Logger] Error appending to audit log: {e}")

    return entry


def get_recent_audit_events(limit: int = 50) -> list[dict]:
    """Retrieve recent audit events from disk, most recent last."""
    with _LOCK:
        target_path = _AUDIT_FILE
        if not target_path.exists():
            return []
        try:
            lines = [l.strip() for l in target_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            records = []
            for l in lines[-limit:]:
                try:
                    records.append(json.loads(l))
                except Exception:
                    pass
            return records
        except Exception as e:
            print(f"[Nova Audit Logger] Error reading audit log: {e}")
            return []
