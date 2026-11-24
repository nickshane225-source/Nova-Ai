"""
Nova AI - Append-Only Security Audit Logger.
Pure Python standard library (no pip packages).

Appends immutable, timestamped JSON lines to data/audit.jsonl
recording all tool invocations, confirmations, and security verdicts.
Automatically masks secrets, credentials, and API keys.
"""

import collections
import datetime
import json
import os
import platform
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
    re.compile(r"(?:sk-[a-zA-Z0-9_\-]{8,})", re.IGNORECASE),
    re.compile(r"(?:ghp_[a-zA-Z0-9]{10,})", re.IGNORECASE),
    re.compile(r"(?:github_pat_[a-zA-Z0-9_]{10,})", re.IGNORECASE),
    re.compile(r"(?:AIza[0-9A-Za-z\-_]{10,})", re.IGNORECASE),
    re.compile(r"AQ\.[A-Za-z0-9_.\-]{20,}"),
    re.compile(r"(?:\b\d{8,12}:[A-Za-z0-9_\-]{25,}\b)"),  # Telegram bot token
    re.compile(r"(?:\b[MN][A-Za-z\d]{23,28}\.[\w-]{6}\.[\w-]{27,40}\b)"),  # Discord bot token
    re.compile(r"(?:bearer\s+[a-zA-Z0-9_\-\.]{8,})", re.IGNORECASE),
    re.compile(r"(?:bot\s+[a-zA-Z0-9_\-\.]{16,})", re.IGNORECASE),
    re.compile(r"(?:x-token-auth:[a-zA-Z0-9_\-@]+@)", re.IGNORECASE),
    re.compile(r"(?:password\s*[:=]\s*[^\s,;]+)", re.IGNORECASE),
    re.compile(r"(?:api[_-]?key\s*[:=]\s*[^\s,;]+)", re.IGNORECASE),
    re.compile(r"(?:bot[_-]?token\s*[:=]\s*[^\s,;]+)", re.IGNORECASE),
]

MAX_AUDIT_BYTES = 5 * 1024 * 1024  # 5 MB rotation threshold


def set_audit_file(path: Path | None) -> None:
    """Set custom audit file location (used in tests). Pass None to reset to default."""
    global _AUDIT_FILE
    with _LOCK:
        _AUDIT_FILE = path or _DEFAULT_AUDIT_FILE


def get_audit_file() -> Path:
    """Return the currently configured audit file path."""
    with _LOCK:
        return _AUDIT_FILE


_SECRET_VALUES_PROVIDER = None


def register_secret_values_provider(fn) -> None:
    """Register a callable returning current configured secret string values."""
    global _SECRET_VALUES_PROVIDER
    _SECRET_VALUES_PROVIDER = fn


def mask_secrets(text: str, cfg: dict = None) -> str:
    """Mask known secret values and secret patterns from text."""
    if not text or not isinstance(text, str):
        return ""
    masked = text

    # Authorization: Bearer <token>
    masked = re.sub(
        r'(?i)(Authorization:\s*(?:Bearer\s+)?)([^\s,;\'"]+)',
        r'\1[REDACTED:token]',
        masked
    )
    masked = re.sub(
        r'(?i)(\bBearer\s+)([A-Za-z0-9_\-\.]{8,})',
        r'\1[REDACTED:token]',
        masked
    )

    secret_vals = []
    if isinstance(cfg, dict):
        for k, v in cfg.items():
            kl = str(k).lower()
            if isinstance(v, str) and len(v) >= 8 and any(w in kl for w in ("key", "token", "secret", "password", "pairing")):
                secret_vals.append(v)
    if callable(_SECRET_VALUES_PROVIDER):
        try:
            for v in (_SECRET_VALUES_PROVIDER() or ()):
                if isinstance(v, str) and len(v) >= 8:
                    secret_vals.append(v)
        except Exception:
            pass
    for val in sorted(set(secret_vals), key=len, reverse=True):
        if len(val) >= 8 and val in masked:
            masked = masked.replace(val, "[REDACTED:key]")
    for pat in _SECRET_PATTERNS:
        masked = pat.sub("[REDACTED:key]", masked)
    return masked


def log_security_event(
    event_type: str,
    details: str,
    severity: str = "WARNING",
    cfg: dict = None,
) -> dict:
    """Convenience wrapper for logging security-specific events (e.g. skill hash mismatch, tampering)."""
    return log_audit_event(
        channel="security",
        tool=str(event_type or "SECURITY").strip().upper(),
        preview=details,
        guardian_verdict=str(severity or "WARNING").strip().upper(),
        status="BLOCKED" if str(severity).upper() in ("HIGH", "CRITICAL") else "WARNED",
        cfg=cfg,
    )


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
    clean_preview = mask_secrets(preview, cfg=cfg)
    was_truncated = False
    if len(clean_preview) > 500:
        clean_preview = clean_preview[:500]
        was_truncated = True

    entry = {
        "timestamp": now_utc,
        "channel": str(channel or "unknown").strip().lower(),
        "tool": str(tool or "unknown").strip().upper(),
        "preview": clean_preview,
        "guardian": str(guardian_verdict or "NONE").strip().upper(),
        "status": str(status or "UNKNOWN").strip().upper(),
    }
    if was_truncated:
        entry["truncated"] = True

    with _LOCK:
        target_path = _AUDIT_FILE
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists():
                try:
                    if target_path.stat().st_size >= MAX_AUDIT_BYTES:
                        rotated = target_path.with_name(target_path.name + ".1")
                        os.replace(target_path, rotated)
                        if platform.system() != "Windows":
                            try:
                                os.chmod(rotated, 0o600)
                            except Exception:
                                pass
                except Exception:
                    pass
            with open(target_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
            if platform.system() != "Windows":
                try:
                    os.chmod(target_path, 0o600)
                except Exception:
                    pass
        except Exception as e:
            # Audit logger must never crash the main application
            print(f"[Nova Audit Logger] Error appending to audit log: {e}")

    return entry


def get_recent_audit_events(limit: int = 50) -> list[dict]:
    """Retrieve the last N audit events from disk (clamped to 1..1000)."""
    with _LOCK:
        target_path = _AUDIT_FILE
        if not target_path.exists():
            return []
        try:
            limit_n = max(1, min(int(limit or 50), 1000))
            tail_lines = collections.deque(maxlen=limit_n)
            with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                for raw_line in f:
                    s = raw_line.strip()
                    if s:
                        tail_lines.append(s)
            records = []
            for l in tail_lines:
                try:
                    records.append(json.loads(l))
                except Exception:
                    pass
            return records
        except Exception as e:
            print(f"[Nova Audit Logger] Error reading audit log: {e}")
            return []


def get_recent_audits(limit: int = 50) -> list[dict]:
    """Alias for get_recent_audit_events returning the last N lines."""
    return get_recent_audit_events(limit=limit)
