#!/usr/bin/env python3
"""
Nova AI Usage & Budget Tracker
Pure Python Standard Library (zero-pip).

Tracks token usage and calculates estimated USD costs across LLM providers
(Gemini, Anthropic, OpenAI, Ollama). Enforces monthly budget caps and logs
every request to an append-only JSONL file (data/usage.jsonl).
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("nova_ai.usage_tracker")

# Model pricing per 1M tokens (USD)
# Standard rates as of 2025/2026
MODEL_PRICING = {
    # Anthropic
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-7-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "o3-mini": {"input": 1.10, "output": 4.40},
    "o4-mini": {"input": 1.10, "output": 4.40},
    # Google Gemini
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.0-flash-exp": {"input": 0.00, "output": 0.00},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    # Local Ollama / Custom offline
    "ollama": {"input": 0.00, "output": 0.00},
}

_USAGE_LOCK = threading.Lock()
_USAGE_FILE = Path(__file__).resolve().parent / "data" / "usage.jsonl"


def set_usage_file(path: Path) -> None:
    """Override usage log path (useful for testing)."""
    global _USAGE_FILE
    with _USAGE_LOCK:
        _USAGE_FILE = Path(path)


def estimate_tokens_from_text(text: str) -> int:
    """Rough heuristic: ~4 characters per token if model provider omits exact usage."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def calculate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate estimated cost in USD based on model pricing table."""
    try:
        in_tok = max(0, int(input_tokens or 0))
    except (ValueError, TypeError):
        in_tok = 0
    try:
        out_tok = max(0, int(output_tokens or 0))
    except (ValueError, TypeError):
        out_tok = 0

    model_lower = (model_name or "").lower()
    pricing = None

    for m_key, rates in MODEL_PRICING.items():
        if m_key in model_lower:
            pricing = rates
            break

    if not pricing:
        if "haiku" in model_lower or "mini" in model_lower or "flash" in model_lower:
            pricing = {"input": 0.20, "output": 0.80}
        elif "opus" in model_lower or "o3" in model_lower:
            pricing = {"input": 10.00, "output": 50.00}
        else:
            pricing = {"input": 2.50, "output": 10.00}

    input_cost = (in_tok / 1_000_000.0) * pricing["input"]
    output_cost = (out_tok / 1_000_000.0) * pricing["output"]
    return round(input_cost + output_cost, 6)


def record_usage(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    source: str = "web",
    duration_sec: float = 0.0,
) -> dict:
    """
    Append a single usage event to data/usage.jsonl.
    Returns the recorded event dictionary.
    """
    try:
        in_tok = max(0, int(input_tokens or 0))
    except (ValueError, TypeError):
        in_tok = 0
    try:
        out_tok = max(0, int(output_tokens or 0))
    except (ValueError, TypeError):
        out_tok = 0

    cost_usd = calculate_cost(model, in_tok, out_tok)
    now_utc = datetime.now(timezone.utc)
    
    event = {
        "timestamp": now_utc.isoformat(),
        "date": now_utc.strftime("%Y-%m-%d"),
        "month": now_utc.strftime("%Y-%m"),
        "provider": provider,
        "model": model,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "total_tokens": int(in_tok + out_tok),
        "cost_usd": cost_usd,
        "source": source,
        "duration_sec": round(duration_sec, 3),
    }

    with _USAGE_LOCK:
        try:
            _USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_USAGE_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Failed to append to usage log: {e}")

    return event


def get_usage_summary(days: int = 30) -> dict:
    """
    Aggregate usage statistics across the specified number of days.
    """
    summary = {
        "total_requests": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens": 0,
        "total_cost_usd": 0.0,
        "by_provider": {},
        "by_model": {},
        "by_date": {},
        "current_month_cost_usd": 0.0,
    }

    current_month = datetime.now(timezone.utc).strftime("%Y-%m")

    with _USAGE_LOCK:
        if not _USAGE_FILE.exists():
            return summary

        try:
            with open(_USAGE_FILE, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except Exception:
                        continue

                    summary["total_requests"] += 1
                    inp = record.get("input_tokens", 0)
                    out = record.get("output_tokens", 0)
                    tot = record.get("total_tokens", inp + out)
                    cost = record.get("cost_usd", 0.0)

                    summary["total_input_tokens"] += inp
                    summary["total_output_tokens"] += out
                    summary["total_tokens"] += tot
                    summary["total_cost_usd"] = round(summary["total_cost_usd"] + cost, 6)

                    # Monthly spend
                    if record.get("month") == current_month:
                        summary["current_month_cost_usd"] = round(
                            summary["current_month_cost_usd"] + cost, 6
                        )

                    prov = record.get("provider", "unknown")
                    mod = record.get("model", "unknown")
                    d = record.get("date", "unknown")

                    # By Provider
                    p_entry = summary["by_provider"].setdefault(prov, {"tokens": 0, "cost_usd": 0.0, "requests": 0})
                    p_entry["tokens"] += tot
                    p_entry["cost_usd"] = round(p_entry["cost_usd"] + cost, 6)
                    p_entry["requests"] += 1

                    # By Model
                    m_entry = summary["by_model"].setdefault(mod, {"tokens": 0, "cost_usd": 0.0, "requests": 0})
                    m_entry["tokens"] += tot
                    m_entry["cost_usd"] = round(m_entry["cost_usd"] + cost, 6)
                    m_entry["requests"] += 1

                    # By Date
                    d_entry = summary["by_date"].setdefault(d, {"tokens": 0, "cost_usd": 0.0, "requests": 0})
                    d_entry["tokens"] += tot
                    d_entry["cost_usd"] = round(d_entry["cost_usd"] + cost, 6)
                    d_entry["requests"] += 1

        except Exception as e:
            logger.warning(f"Error reading usage log: {e}")

    return summary


def check_budget_status(cap_usd: float | None = None) -> dict:
    """
    Check if monthly budget limit has been reached.
    """
    summary = get_usage_summary(days=31)
    spent = summary["current_month_cost_usd"]
    
    if cap_usd is None or cap_usd <= 0.0:
        return {
            "budget_active": False,
            "cap_usd": None,
            "spent_usd": spent,
            "remaining_usd": None,
            "percent_used": 0.0,
            "exhausted": False,
            "warning": False,
        }

    remaining = max(0.0, round(cap_usd - spent, 6))
    pct = round((spent / cap_usd) * 100.0, 1)
    exhausted = spent >= cap_usd
    warning = pct >= 80.0 and not exhausted

    return {
        "budget_active": True,
        "cap_usd": cap_usd,
        "spent_usd": spent,
        "remaining_usd": remaining,
        "percent_used": pct,
        "exhausted": exhausted,
        "warning": warning,
    }
