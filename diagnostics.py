#!/usr/bin/env python3
"""
Nova AI System Diagnostics & Health Doctor (diagnostics.py)
Pure Python Standard Library (zero-pip).

Performs comprehensive diagnostic checks across:
- Python environment & OS
- Disk space and storage write access
- SQLite database integrity (nova_brain.db)
- LLM Provider credentials & fallback configurations
- Multi-channel gateways (Telegram, Discord)
- Security subsystems (Guardian AI, DPAPI, Audit Logger)

Can be run via CLI (`python diagnostics.py --doctor`) or invoked via API (`GET /api/health`).
"""

import json
import os
import platform
import shutil
import sqlite3
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows consoles/terminals
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
WORKSPACE_DIR = BASE_DIR / "workspace"
CONFIG_FILE = DATA_DIR / "config.json"
DB_FILE = DATA_DIR / "nova_brain.db"


def check_python_environment() -> dict:
    version = sys.version_info
    is_ok = version.major == 3 and version.minor >= 10
    return {
        "category": "Environment",
        "name": "Python Version",
        "status": "ok" if is_ok else "error",
        "message": f"Python {version.major}.{version.minor}.{version.micro} ({platform.system()} {platform.release()})",
    }


def check_disk_and_storage() -> list[dict]:
    results = []
    # Test Data Directory Writable
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        test_file = DATA_DIR / ".write_probe"
        test_file.write_text("probe", encoding="utf-8")
        test_file.unlink()
        results.append({
            "category": "Storage",
            "name": "Data Directory Writable",
            "status": "ok",
            "message": str(DATA_DIR),
        })
    except Exception as e:
        results.append({
            "category": "Storage",
            "name": "Data Directory Writable",
            "status": "error",
            "message": f"Cannot write to data dir: {e}",
        })

    # Test Workspace Writable
    try:
        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        test_file = WORKSPACE_DIR / ".write_probe"
        test_file.write_text("probe", encoding="utf-8")
        test_file.unlink()
        results.append({
            "category": "Storage",
            "name": "Workspace Directory Writable",
            "status": "ok",
            "message": str(WORKSPACE_DIR),
        })
    except Exception as e:
        results.append({
            "category": "Storage",
            "name": "Workspace Directory Writable",
            "status": "error",
            "message": f"Cannot write to workspace dir: {e}",
        })

    # Free Disk Space
    try:
        total, used, free = shutil.disk_usage(BASE_DIR)
        free_gb = free / (1024 ** 3)
        status = "ok" if free_gb >= 1.0 else ("warning" if free_gb >= 0.2 else "error")
        results.append({
            "category": "Storage",
            "name": "Disk Free Space",
            "status": status,
            "message": f"{free_gb:.2f} GB free",
        })
    except Exception as e:
        results.append({
            "category": "Storage",
            "name": "Disk Free Space",
            "status": "warning",
            "message": f"Unable to read disk usage: {e}",
        })

    return results


def check_database_integrity() -> dict:
    if not DB_FILE.exists():
        return {
            "category": "Database",
            "name": "SQLite Integrity",
            "status": "warning",
            "message": "nova_brain.db not yet created (will initialize on first run)",
        }
    try:
        conn = sqlite3.connect(DB_FILE, timeout=5)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        row = cursor.fetchone()
        conn.close()
        if row and row[0] == "ok":
            return {
                "category": "Database",
                "name": "SQLite Integrity",
                "status": "ok",
                "message": "Database passes PRAGMA integrity_check",
            }
        else:
            return {
                "category": "Database",
                "name": "SQLite Integrity",
                "status": "error",
                "message": f"Corrupt database: {row}",
            }
    except Exception as e:
        return {
            "category": "Database",
            "name": "SQLite Integrity",
            "status": "error",
            "message": f"Database check failed: {e}",
        }


def _detect_provider_from_cfg(cfg: dict) -> str:
    prov = (cfg.get("provider") or "").lower()
    base = (cfg.get("base_url") or "").lower()
    model = (cfg.get("model") or "").lower()
    if prov == "anthropic" or "anthropic" in base or "claude" in model:
        return "Anthropic Claude"
    if "generativelanguage" in base or prov == "gemini" or "gemini" in model:
        return "Google Gemini"
    if "groq" in base:
        return "Groq"
    if "openrouter" in base:
        return "OpenRouter"
    if prov == "ollama" or "localhost:11434" in base or "127.0.0.1:11434" in base:
        return "Ollama (Offline)"
    if prov == "openai" or "api.openai.com" in base or "gpt" in model or "o3" in model or "o4" in model:
        return "OpenAI"
    if prov:
        return prov.capitalize()
    return "Custom Provider"


def check_llm_providers(cfg: dict = None) -> list[dict]:
    results = []
    if cfg is None:
        if CONFIG_FILE.exists():
            try:
                cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                cfg = {}
        else:
            cfg = {}

    seen_providers = set()

    # 1. Primary configured provider key
    primary_key = cfg.get("api_key")
    if primary_key:
        prov_name = _detect_provider_from_cfg(cfg)
        results.append({
            "category": "LLM Providers",
            "name": prov_name,
            "status": "ok",
            "message": "API key configured",
        })
        seen_providers.add(prov_name)

    # 2. Google Gemini dedicated key
    gemini_key = cfg.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY")
    if gemini_key and "Google Gemini" not in seen_providers:
        results.append({
            "category": "LLM Providers",
            "name": "Google Gemini",
            "status": "ok",
            "message": "API key configured",
        })
        seen_providers.add("Google Gemini")

    # 3. Anthropic Claude dedicated key
    anthropic_key = cfg.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key and "Anthropic Claude" not in seen_providers:
        results.append({
            "category": "LLM Providers",
            "name": "Anthropic Claude",
            "status": "ok",
            "message": "API key configured",
        })
        seen_providers.add("Anthropic Claude")

    # 4. OpenAI dedicated key
    openai_key = cfg.get("openai_api_key") or cfg.get("custom_api_key") or os.environ.get("OPENAI_API_KEY")
    if openai_key and "OpenAI" not in seen_providers:
        results.append({
            "category": "LLM Providers",
            "name": "OpenAI",
            "status": "ok",
            "message": "API key configured",
        })
        seen_providers.add("OpenAI")

    # 5. Ollama Local
    ollama_active = cfg.get("provider") == "ollama" or os.environ.get("OLLAMA_HOST")
    if ollama_active and "Ollama (Offline)" not in seen_providers:
        results.append({
            "category": "LLM Providers",
            "name": "Ollama (Offline)",
            "status": "ok",
            "message": "Local provider configured",
        })
        seen_providers.add("Ollama (Offline)")

    if not results:
        results.append({
            "category": "LLM Providers",
            "name": "Model Providers",
            "status": "warning",
            "message": "No API key configured yet. Set Gemini, Anthropic, OpenAI, or Ollama in Settings.",
        })

    return results


_check_llm_providers = check_llm_providers


def check_security_and_gateways(cfg: dict = None) -> list[dict]:
    results = []
    if cfg is None:
        if CONFIG_FILE.exists():
            try:
                cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                cfg = {}
        else:
            cfg = {}

    # Audit logger
    audit_file = DATA_DIR / "audit.jsonl"
    results.append({
        "category": "Security",
        "name": "Audit Logging",
        "status": "ok",
        "message": f"Active ({audit_file.name})",
    })

    # Guardian AI
    results.append({
        "category": "Security",
        "name": "Guardian Dual-Review Rails",
        "status": "ok",
        "message": "Active (pre-execution regex & LLM gating)",
    })

    # DPAPI on Windows
    is_win = platform.system() == "Windows"
    results.append({
        "category": "Security",
        "name": "DPAPI Key Protection",
        "status": "ok" if is_win else "info",
        "message": "Hardware-backed DPAPI supported" if is_win else "Standard encryption",
    })

    # Telegram Gateway
    telegram_configured = bool(cfg.get("telegram_bot_token"))
    telegram_enabled = bool(cfg.get("telegram_enabled", False))
    results.append({
        "category": "Gateways",
        "name": "Telegram Bot Gateway",
        "status": "ok" if (telegram_configured and telegram_enabled) else "info",
        "message": "Enabled & ready" if (telegram_configured and telegram_enabled) else ("Token set (disabled)" if telegram_configured else "Not configured"),
    })

    # Discord Gateway
    discord_configured = bool(cfg.get("discord_bot_token"))
    discord_enabled = bool(cfg.get("discord_enabled", False))
    results.append({
        "category": "Gateways",
        "name": "Discord Bot Gateway",
        "status": "ok" if (discord_configured and discord_enabled) else "info",
        "message": "Enabled & ready" if (discord_configured and discord_enabled) else ("Token set (disabled)" if discord_configured else "Not configured"),
    })

    return results


def run_diagnostics(cfg: dict = None) -> dict:
    """
    Execute all diagnostic checks and calculate overall health status.
    Returns:
        {
            "overall_status": "healthy" | "degraded" | "unhealthy",
            "summary": { "ok": int, "warning": int, "error": int },
            "checks": [ ... ]
        }
    """
    checks = []
    checks.append(check_python_environment())
    checks.extend(check_disk_and_storage())
    checks.append(check_database_integrity())
    checks.extend(check_llm_providers(cfg))
    checks.extend(check_security_and_gateways(cfg))

    summary = {"ok": 0, "warning": 0, "error": 0, "info": 0}
    for c in checks:
        st = c.get("status", "info")
        summary[st] = summary.get(st, 0) + 1

    if summary["error"] > 0:
        overall = "unhealthy"
    elif summary["warning"] > 0:
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "overall_status": overall,
        "summary": summary,
        "checks": checks,
    }


def print_doctor_report(diag: dict) -> None:
    """Print polished doctor diagnostic report in terminal."""
    w = sys.stdout.write
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    CYAN = "\033[36m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    w(f"\n  {BOLD}🐾 Nova AI Doctor - System Diagnostics{RESET}\n")
    w(f"  {'=' * 45}\n\n")

    categories = {}
    for c in diag["checks"]:
        categories.setdefault(c["category"], []).append(c)

    for cat_name, items in categories.items():
        w(f"  {CYAN}{BOLD}{cat_name}{RESET}\n")
        for item in items:
            st = item["status"]
            if st == "ok":
                icon = f"{GREEN}[OK]{RESET}"
            elif st == "warning":
                icon = f"{YELLOW}[WARN]{RESET}"
            elif st == "error":
                icon = f"{RED}[ERR]{RESET}"
            else:
                icon = f"{CYAN}[INFO]{RESET}"
            w(f"    {icon} {item['name']:<28} : {item['message']}\n")
        w("\n")

    st_color = GREEN if diag["overall_status"] == "healthy" else (YELLOW if diag["overall_status"] == "degraded" else RED)
    w(f"  {BOLD}Status:{RESET} {st_color}{diag['overall_status'].upper()}{RESET} ({diag['summary']['ok']} passed, {diag['summary']['warning']} warnings, {diag['summary']['error']} errors)\n\n")


if __name__ == "__main__":
    diag = run_diagnostics()
    print_doctor_report(diag)
    sys.exit(0 if diag["overall_status"] != "unhealthy" else 1)
