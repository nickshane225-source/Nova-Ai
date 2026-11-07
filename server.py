#!/usr/bin/env python3
"""
Nova AI - a local, voice-first AI character for your PC.

Pure Python standard library (no pip install needed).
Runs a small web server on 127.0.0.1 and opens the UI in your browser.
Your API key is stored only in data/config.json on your own machine.
"""
import datetime
import hashlib
import hmac
import ipaddress
import json
import mimetypes
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import shlex
import signal
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Ensure UTF-8 output on Windows consoles/terminals to prevent Bengali/multilingual charmap crashes
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

try:
    import ctypes
except Exception:
    ctypes = None

OS = platform.system()
if OS == "Windows" and ctypes:
    try:
        u32 = ctypes.windll.user32
        u32.GetForegroundWindow.restype = ctypes.c_void_p
        u32.GetForegroundWindow.argtypes = []
        u32.GetWindowTextLengthW.restype = ctypes.c_int
        u32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
        u32.GetWindowTextW.restype = ctypes.c_int
        u32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
        u32.GetWindowThreadProcessId.restype = ctypes.c_ulong
        u32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        u32.GetSystemMetrics.restype = ctypes.c_int
        u32.GetSystemMetrics.argtypes = [ctypes.c_int]
        u32.SetCursorPos.restype = ctypes.c_bool
        u32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        u32.mouse_event.restype = None
        u32.mouse_event.argtypes = [ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
        u32.keybd_event.restype = None
        u32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_ulong, ctypes.c_void_p]
        u32.LockWorkStation.restype = ctypes.c_bool
        u32.LockWorkStation.argtypes = []

        s32 = ctypes.windll.shell32
        s32.SHEmptyRecycleBinW.restype = ctypes.c_long
        s32.SHEmptyRecycleBinW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_ulong]
    except Exception:
        pass


SECRET_FIELDS = {
    "api_key",
    "anthropic_api_key",
    "groq_api_key",
    "gemini_api_key",
    "openrouter_api_key",
    "custom_api_key",
    "pairing_code",
    "smart_home_token",
    "remote_token",
    "remote_key",
    "telegram_bot_token",
    "discord_bot_token",
}

SAFE_STATE_FIELDS = {
    "provider", "model", "base_url", "character", "user_name", "language",
    "voice_rate", "voice_pitch", "voice_volume", "wake_word_enabled",
    "barge_in_enabled", "port", "remote_enabled", "remote_port",
    "allow_outside_workspace", "confirm_destructive", "remote_allow_dangerous",
    "process_timeout", "max_tokens", "apps", "run_code_trusted_minutes",
    "encrypt_keys", "mode", "shortcuts", "theme", "smart_home_hosts",
    "llm_timeout", "debug_llm", "llm_reasoning_effort", "fallback_providers",
    "telegram_enabled", "telegram_allowed_chat_ids",
    "discord_enabled", "discord_channel_ids", "discord_allowed_user_ids",
    "monthly_budget_usd"
}

def is_secret_field(key: str) -> bool:
    if not isinstance(key, str):
        return False
    k = key.lower()
    return (
        k in SECRET_FIELDS
        or k.endswith("_key")
        or k.endswith("_token")
        or k.endswith("_secret")
        or "password" in k
        or "api_key" in k
    )


def is_dpapi_available() -> bool:
    if OS != "Windows" or not ctypes:
        return False
    try:
        return hasattr(ctypes, "windll") and hasattr(ctypes.windll, "crypt32")
    except Exception:
        return False


def encrypt_dpapi(plaintext: str) -> str:
    if not plaintext or not isinstance(plaintext, str):
        return plaintext
    if not is_dpapi_available():
        print("[Nova DPAPI] Warning: DPAPI encryption requested but unavailable on this platform.")
        return plaintext
    try:
        import base64
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        data_bytes = plaintext.encode("utf-8")
        in_blob = DATA_BLOB(len(data_bytes), ctypes.cast(ctypes.create_string_buffer(data_bytes), ctypes.POINTER(ctypes.c_byte)))
        out_blob = DATA_BLOB()
        if not crypt32.CryptProtectData(ctypes.byref(in_blob), "NovaKey", None, None, None, 0, ctypes.byref(out_blob)):
            print("[Nova DPAPI] Warning: CryptProtectData call failed; keeping plaintext.")
            return plaintext
        try:
            cipher_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            return "dpapi:" + base64.b64encode(cipher_bytes).decode("ascii")
        finally:
            kernel32.LocalFree(out_blob.pbData)
    except Exception as e:
        print(f"[Nova DPAPI] Warning: DPAPI encrypt failed: {e}; keeping plaintext.")
        return plaintext


def decrypt_dpapi(ciphertext: str) -> str:
    if not ciphertext or not isinstance(ciphertext, str):
        return ciphertext
    if not ciphertext.startswith("dpapi:"):
        return ciphertext
    if not is_dpapi_available():
        print("[Nova DPAPI] Warning: Encrypted DPAPI blob found but DPAPI is unavailable on this platform.")
        return ciphertext
    try:
        import base64
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        raw_b64 = ciphertext[len("dpapi:"):]
        cipher_bytes = base64.b64decode(raw_b64)
        in_blob = DATA_BLOB(len(cipher_bytes), ctypes.cast(ctypes.create_string_buffer(cipher_bytes), ctypes.POINTER(ctypes.c_byte)))
        out_blob = DATA_BLOB()
        if not crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
            print("[Nova DPAPI] Warning: CryptUnprotectData failed.")
            return ciphertext
        try:
            plain_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            return plain_bytes.decode("utf-8")
        finally:
            kernel32.LocalFree(out_blob.pbData)
    except Exception as e:
        print(f"[Nova DPAPI] Warning: DPAPI decrypt failed: {e}")
        return ciphertext

try:
    import nova_browser
except Exception:
    nova_browser = None

try:
    import memory_engine
except Exception:
    memory_engine = None

try:
    import scheduler_engine
except Exception:
    scheduler_engine = None

try:
    import skills_engine
except Exception:
    skills_engine = None

try:
    import audit_logger
except Exception:
    audit_logger = None

try:
    import guardian_agent
except Exception:
    guardian_agent = None

try:
    import plan_mode
except Exception:
    plan_mode = None

try:
    import telegram_gateway
except Exception:
    telegram_gateway = None

try:
    import integrations
    integrations.load_integrations()
except Exception:
    integrations = None

try:
    import usage_tracker
except Exception:
    usage_tracker = None

try:
    import diagnostics
except Exception:
    diagnostics = None

try:
    import discord_gateway
except Exception:
    discord_gateway = None

if getattr(sys, "frozen", False):
    exe_dir = Path(sys.executable).resolve().parent
    try:
        test_file = exe_dir / ".write_test"
        test_file.touch()
        test_file.unlink()
        ROOT = exe_dir
    except Exception:
        appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        ROOT = Path(appdata) / "NovaAI"
        ROOT.mkdir(parents=True, exist_ok=True)
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", exe_dir))
else:
    ROOT = Path(__file__).resolve().parent
    BUNDLE_DIR = ROOT

WEB = BUNDLE_DIR / "web"
if not WEB.exists():
    WEB = ROOT / "web"

DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
WORKSPACE = ROOT / "workspace"
WORKSPACE.mkdir(exist_ok=True)

CONFIG_FILE = DATA / "config.json"
MEMORY_FILE = DATA / "memory.json"
CHARS_FILE = DATA / "characters.json"

LOCK = threading.Lock()

# ----------------------------------------------------------------------------
# Defaults
# ----------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "provider": "anthropic",  # anthropic | openai  (openai = any OpenAI-compatible API)
    "api_key": "",
    "model": "claude-3-5-sonnet-latest",
    "base_url": "https://api.openai.com/v1",  # only used for provider=openai
    "user_name": "",
    "language": "en-US",
    "character": "jarvis",
    "port": 8765,
    "coding_workspace": str(WORKSPACE),
    "voice_rate": 1.0,
    "voice_pitch": 1.0,
    "voice_volume": 1.0,
    "wake_word_enabled": True,
    "barge_in_enabled": False,
    "llm_timeout": 60,
    "debug_llm": False,
    "llm_reasoning_effort": "",
    # Mobile remote (phone -> PC). Off by default; turn on from the "Mobile" panel.
    "remote_enabled": False,
    "remote_port": 8766,
    "remote_token": "",
    "allow_outside_workspace": False,
    "max_tokens": 2048,
    "confirm_destructive": True,
    "remote_allow_dangerous": False,
    "process_timeout": 60,
    "run_code_trusted_minutes": 0,
    "encrypt_keys": OS == "Windows",
    "fallback_providers": [],
    "telegram_enabled": False,
    "telegram_bot_token": "",
    "telegram_allowed_chat_ids": [],
    "discord_enabled": False,
    "discord_bot_token": "",
    "discord_channel_ids": [],
    "discord_allowed_user_ids": [],
    "monthly_budget_usd": 0.0,
}

PRESETS = {
    "anthropic": {"model": "claude-3-5-sonnet-latest", "base_url": ""},
    "openai": {"model": "gpt-4o-mini", "base_url": "https://api.openai.com/v1"},
    "gemini": {"model": "gemini-3.5-flash-lite", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai"},
    "ollama": {"model": "llama3.2", "base_url": "http://localhost:11434/v1"},
}

DEFAULT_CHARACTERS = [
    {
        "id": "jarvis",
        "name": "Jarvis",
        "voice": "male",
        "prompt": "You are a calm, razor-sharp, slightly dry-witted AI butler living inside the user's PC. "
        "Polite, efficient, occasionally sarcastic in a friendly way. Address the user as 'sir' or 'ma'am' "
        "only if their name is unknown.",
    },
    {
        "id": "mentor",
        "name": "Mentor",
        "voice": "male",
        "prompt": "You are a wise, patient mentor. You encourage, ask one good question at a time, "
        "and give practical next steps.",
    },
    {
        "id": "bestfriend",
        "name": "Best Friend",
        "voice": "female",
        "prompt": "You are the user's warm, playful best friend. Casual, supportive, funny, genuinely curious "
        "about their day. You never pretend to be human if sincerely asked.",
    },
]

# Apps Nova is allowed to open. Edit data/config.json -> "apps" to add your own.
DEFAULT_APPS = {
    "Windows": {
        "notepad": ["notepad.exe"],
        "calculator": ["calc.exe"],
        "paint": ["mspaint.exe"],
        "file explorer": ["explorer.exe"],
        "task manager": ["taskmgr.exe"],
        "settings": ["cmd", "/c", "start", "", "ms-settings:"],
        "chrome": ["cmd", "/c", "start", "", "chrome"],
        "edge": ["cmd", "/c", "start", "", "msedge"],
        "spotify": ["cmd", "/c", "start", "", "spotify:"],
        "vscode": ["cmd", "/c", "start", "", "code"],
    },
    "Darwin": {
        "notes": ["open", "-a", "Notes"],
        "calculator": ["open", "-a", "Calculator"],
        "finder": ["open", "-a", "Finder"],
        "safari": ["open", "-a", "Safari"],
        "chrome": ["open", "-a", "Google Chrome"],
        "spotify": ["open", "-a", "Spotify"],
        "terminal": ["open", "-a", "Terminal"],
    },
    "Linux": {
        "calculator": ["gnome-calculator"],
        "files": ["xdg-open", str(Path.home())],
        "terminal": ["x-terminal-emulator"],
        "firefox": ["firefox"],
        "chrome": ["google-chrome"],
    },
}


# ----------------------------------------------------------------------------
# Storage helpers
# ----------------------------------------------------------------------------
def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, obj):
    with LOCK:
        path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def save_config(cfg):
    to_save = dict(cfg)
    encrypt_enabled = to_save.get("encrypt_keys", OS == "Windows")
    if encrypt_enabled and is_dpapi_available():
        for k in list(to_save.keys()):
            if k != "encrypt_keys" and isinstance(to_save[k], str) and to_save[k]:
                if is_secret_field(k):
                    if not to_save[k].startswith("dpapi:"):
                        to_save[k] = encrypt_dpapi(to_save[k])
    elif not encrypt_enabled:
        for k in list(to_save.keys()):
            if isinstance(to_save[k], str) and to_save[k].startswith("dpapi:"):
                to_save[k] = decrypt_dpapi(to_save[k])
    save_json(CONFIG_FILE, to_save)


def get_config():
    cfg = dict(DEFAULT_CONFIG)
    raw_saved = load_json(CONFIG_FILE, {})
    cfg.update(raw_saved)
    if "apps" not in cfg:
        cfg["apps"] = DEFAULT_APPS.get(OS, {})

    # Decrypt any DPAPI encrypted fields for in-memory use
    for k, v in list(cfg.items()):
        if isinstance(v, str) and v.startswith("dpapi:"):
            cfg[k] = decrypt_dpapi(v)

    # Automatic migration: if encrypt_keys is true and raw_saved contains plaintext keys, migrate to DPAPI on disk
    if cfg.get("encrypt_keys", OS == "Windows") and is_dpapi_available():
        needs_migration = False
        migrated = dict(raw_saved)
        for k, v in raw_saved.items():
            if k != "encrypt_keys" and isinstance(v, str) and v and not v.startswith("dpapi:"):
                if is_secret_field(k):
                    migrated[k] = encrypt_dpapi(v)
                    needs_migration = True
        if needs_migration:
            save_json(CONFIG_FILE, migrated)

    return cfg


def get_memory():
    return load_json(MEMORY_FILE, [])


def get_characters():
    chars = load_json(CHARS_FILE, None)
    if not chars:
        bundled_chars = BUNDLE_DIR / "data" / "characters.json"
        if bundled_chars.is_file():
            chars = load_json(bundled_chars, DEFAULT_CHARACTERS)
        else:
            chars = DEFAULT_CHARACTERS
        save_json(CHARS_FILE, chars)
    return chars


HISTORIES = {
    "developer": [],
    "cyber": [],
}
HISTORY = HISTORIES["developer"]  # short-term conversation backward compatibility alias


# ----------------------------------------------------------------------------
# LLM
# ----------------------------------------------------------------------------
class LLMError(Exception):
    pass


def http_post(url, headers, body, timeout=90):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:400]
        raise LLMError(f"API error {e.code}: {detail}")
    except Exception as e:
        raise LLMError(f"Could not reach the AI provider: {e}")


def _call_single_llm(cfg, system, messages):
    provider = cfg["provider"]
    key = cfg.get("api_key", "")
    if isinstance(key, str) and key.startswith("dpapi:"):
        key = decrypt_dpapi(key)
    timeout_cfg = int(cfg.get("llm_timeout", cfg.get("process_timeout", 60)) or 60)
    if provider == "anthropic":
        if not key:
            raise LLMError("No API key set. Open Settings and paste your key.")
        data = http_post(
            "https://api.anthropic.com/v1/messages",
            {
                "content-type": "application/json",
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
            {
                "model": cfg["model"],
                "max_tokens": cfg.get("max_tokens", 2048),
                "system": system,
                "messages": messages,
            },
            timeout=timeout_cfg,
        )
        return "".join(b.get("text", "") for b in data.get("content", []))
    # OpenAI-compatible (OpenAI, OpenRouter, Groq, Ollama, LM Studio ...)
    base = cfg["base_url"].rstrip("/")
    headers = {"content-type": "application/json"}
    if key:
        headers["authorization"] = f"Bearer {key}"
    elif "localhost" not in base and "127.0.0.1" not in base:
        raise LLMError("No API key set. Open Settings and paste your key.")

    sanitized_messages = list(messages)
    # Gemini: remove trailing assistant/model messages as required by API guidelines
    while sanitized_messages and sanitized_messages[-1].get("role") in ("assistant", "model"):
        sanitized_messages.pop()

    body = {
        "model": cfg["model"],
        "max_tokens": cfg.get("max_tokens", 2048),
        "messages": [{"role": "system", "content": system}] + sanitized_messages,
    }
    is_gemini = "generativelanguage.googleapis.com" in base or "gemini" in str(cfg.get("model", "")).lower()
    is_gemini_3 = is_gemini and any(v in str(cfg.get("model", "")).lower() for v in ("gemini-3", "gemini-3.5", "gemini-3.6", "gemini-3.7", "gemini-3.8"))
    if is_gemini:
        # Strip sampling parameters not recommended for Gemini 3.x models
        for param in ("temperature", "top_p", "top_k"):
            body.pop(param, None)
        # For Gemini 3.x models, do NOT send reasoning_effort unless user explicitly configures llm_reasoning_effort
        if cfg.get("llm_reasoning_effort"):
            body["reasoning_effort"] = str(cfg["llm_reasoning_effort"])
        elif not is_gemini_3:
            body["reasoning_effort"] = "low"
        body["max_tokens"] = cfg.get("max_tokens", 2048)

    initial_timeout = max(5, min(timeout_cfg, 90))
    retry_timeout = max(5, min(38, 99 - initial_timeout))

    if is_gemini and cfg.get("debug_llm") and sys.stdout:
        t_now = time.strftime("%H:%M:%S")
        last_role = sanitized_messages[-1].get("role") if sanitized_messages else "none"
        print(f"[{t_now}] [Gemini DIAGNOSE] model={body.get('model')}, reasoning_effort={body.get('reasoning_effort', 'none')}, params={list(body.keys())}, msg_count={len(sanitized_messages)}, trailing_role={last_role}, timeout={initial_timeout}s")

    try:
        t0 = time.time()
        data = http_post(base + "/chat/completions", headers, body, timeout=initial_timeout)
    except LLMError as e:
        elapsed = time.time() - t0
        # Retry without reasoning parameters only if reasoning_effort was sent
        if is_gemini and "reasoning_effort" in body and ("API error 400" in str(e) or "timed out" in str(e)):
            body.pop("reasoning_effort", None)
            if cfg.get("debug_llm") and sys.stdout:
                print(f"[Gemini DIAGNOSE] Retrying once without reasoning parameters (elapsed {elapsed:.1f}s, retry timeout {retry_timeout}s, total <= 99s)...")
            data = http_post(base + "/chat/completions", headers, body, timeout=retry_timeout)
        else:
            raise
    try:
        return data["choices"][0]["message"].get("content") or "Sorry, I got an empty answer. Please try again."
    except (KeyError, IndexError):
        raise LLMError(f"Unexpected reply from the AI provider: {str(data)[:300]}")


def call_llm_with_fallback(cfg, system, messages):
    """Executes LLM call with automated failover across configured fallback_providers."""
    if usage_tracker and cfg.get("monthly_budget_usd"):
        try:
            cap_val = float(cfg.get("monthly_budget_usd"))
            if cap_val > 0.0:
                b_status = usage_tracker.check_budget_status(cap_val)
                if b_status.get("exhausted"):
                    raise LLMError(f"Monthly budget limit reached (${b_status['spent_usd']:.2f} spent of ${b_status['cap_usd']:.2f} cap). Adjust monthly_budget_usd in Settings.")
        except LLMError:
            raise
        except Exception:
            pass

    t0 = time.time()
    fallbacks = cfg.get("fallback_providers") or []
    if not isinstance(fallbacks, list):
        fallbacks = [fallbacks]

    res = None
    try:
        res = _call_single_llm(cfg, system, messages)
    except LLMError as primary_err:
        if not fallbacks:
            raise primary_err

        last_err = primary_err
        current_prov = cfg.get("provider", "")
        for fb_prov in fallbacks:
            fb_name = str(fb_prov).strip().lower()
            if not fb_name or fb_name == current_prov:
                continue

            fb_cfg = dict(cfg)
            if fb_name == "anthropic":
                fb_cfg["provider"] = "anthropic"
                fb_cfg["base_url"] = ""
                fb_cfg["model"] = cfg.get("anthropic_model") or PRESETS["anthropic"]["model"]
                key = cfg.get("anthropic_api_key") or (cfg.get("api_key") if cfg.get("provider") == "anthropic" else "")
                fb_cfg["api_key"] = key
            elif fb_name == "gemini":
                fb_cfg["provider"] = "openai"
                fb_cfg["base_url"] = PRESETS["gemini"]["base_url"]
                fb_cfg["model"] = PRESETS["gemini"]["model"]
                key = cfg.get("gemini_api_key") or (cfg.get("api_key") if "generativelanguage" in cfg.get("base_url", "") else "")
                fb_cfg["api_key"] = key
            elif fb_name == "ollama":
                fb_cfg["provider"] = "openai"
                fb_cfg["base_url"] = PRESETS["ollama"]["base_url"]
                fb_cfg["model"] = PRESETS["ollama"]["model"]
                fb_cfg["api_key"] = ""
            elif fb_name == "openai":
                fb_cfg["provider"] = "openai"
                fb_cfg["base_url"] = PRESETS["openai"]["base_url"]
                fb_cfg["model"] = PRESETS["openai"]["model"]
                key = cfg.get("openai_api_key") or (cfg.get("api_key") if cfg.get("provider") == "openai" and "generativelanguage" not in cfg.get("base_url", "") else "")
                fb_cfg["api_key"] = key
            elif fb_name in PRESETS:
                fb_cfg["provider"] = PRESETS[fb_name]["provider"]
                fb_cfg["base_url"] = PRESETS[fb_name]["base_url"]
                fb_cfg["model"] = PRESETS[fb_name]["model"]
            else:
                continue

            try:
                if cfg.get("debug_llm") and sys.stdout:
                    print(f"[Nova Router] Primary LLM failed ({last_err}). Failing over to '{fb_name}'...")
                res = _call_single_llm(fb_cfg, system, messages)
                break
            except LLMError as fb_err:
                last_err = fb_err
                continue

        if res is None:
            raise last_err

    if usage_tracker and res:
        try:
            inp_chars = len(system) + sum(len(str(m.get("content", ""))) for m in messages)
            out_chars = len(res)
            inp_tokens = usage_tracker.estimate_tokens_from_text("x" * inp_chars)
            out_tokens = usage_tracker.estimate_tokens_from_text(res)
            usage_tracker.record_usage(
                provider=cfg.get("provider", "unknown"),
                model=cfg.get("model", "unknown"),
                input_tokens=inp_tokens,
                output_tokens=out_tokens,
                duration_sec=time.time() - t0,
            )
        except Exception:
            pass

    return res


def call_llm(cfg, system, messages):
    return call_llm_with_fallback(cfg, system, messages)


def call_llm_vision(cfg, prompt, base64_png):
    """Sends a base64 screenshot to multimodal vision LLMs (Anthropic, Gemini, OpenAI, Ollama)."""
    provider = cfg["provider"]
    key = cfg.get("api_key", "")
    if isinstance(key, str) and key.startswith("dpapi:"):
        key = decrypt_dpapi(key)
    system = "You are Nova AI Desktop Vision. Look carefully at the provided desktop screenshot and answer the user's question clearly, accurately, and concisely in their language."
    
    if provider == "anthropic":
        if not key:
            raise LLMError("No API key set. Open Settings and paste your key.")
        data = http_post(
            "https://api.anthropic.com/v1/messages",
            {
                "content-type": "application/json",
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
            {
                "model": cfg["model"] if "claude" in cfg["model"] else "claude-3-5-sonnet-latest",
                "max_tokens": 1000,
                "system": system,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": base64_png,
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt or "What is on my screen? Provide a clear summary and point out any errors or important content.",
                            },
                        ],
                    }
                ],
            },
        )
        return "".join(b.get("text", "") for b in data.get("content", []))

    # OpenAI-compatible / Gemini / Ollama
    base = cfg["base_url"].rstrip("/")
    headers = {"content-type": "application/json"}
    if key:
        headers["authorization"] = f"Bearer {key}"
    elif "localhost" not in base and "127.0.0.1" not in base:
        raise LLMError("No API key set. Open Settings and paste your key.")

    body = {
        "model": cfg["model"],
        "max_tokens": 1000,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt or "What is on my screen? Provide a clear summary and point out any errors or important content."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_png}"}}
                ],
            },
        ],
    }
    data = http_post(base + "/chat/completions", headers, body, timeout=60)
    try:
        return data["choices"][0]["message"].get("content") or "I could not analyze the image."
    except Exception:
        raise LLMError(f"Unexpected vision response from AI provider: {str(data)[:300]}")


SKILL_DOC = """
You have FULL CONTROL of the user's PC and can act as an autonomous CODING AGENT.
To use a skill, put a tag anywhere in your reply. Tags are executed by the server and removed before speaking to the user.
Always say a natural sentence in the user's language about what you are doing.
Do not put tool tags inside code blocks; write a tag only when you want it executed.

Available PC Control Skills:
  [[OPEN_APP: app_name]]                 Open any installed app or program (notepad, calculator, chrome, code, spotify, youtube, etc.)
  [[CLOSE_APP: process_name]]            Close/terminate an app (e.g. chrome, notepad, spotify, vlc)
  [[VOLUME: up | down | mute | unmute | 0-100]] Control Windows master volume or mute/unmute
  [[MEDIA: play | pause | next | prev]]  Control media playback (Spotify, YouTube, browser)
  [[PLAY: song or video name]]           Search YouTube and immediately play the song/video (e.g. [[PLAY: Shape of You]], [[PLAY: বাংলা গান]])
  [[OPEN_URL: url]]                      Open any website URL in browser (e.g. [[OPEN_URL: https://youtube.com]])
  [[SCREENSHOT]]                         Take a full desktop screenshot and save to Pictures
  [[SYSTEM: lock | sleep | minimize | empty_recycle_bin | stats | shutdown | restart | cancel_shutdown]]
                                         PC actions: lock screen, sleep, show desktop, empty trash, hardware stats (CPU/RAM/disk/battery)
  [[CMD: command]]                       Run any Windows command prompt command
  [[POWERSHELL: script]]                 Run any PowerShell command or script
  [[MOUSE_MOVE: x, y]]                   Move mouse cursor to (x, y) coordinates on screen
  [[MOUSE_CLICK: left | right | double | x, y]] Click mouse button (optionally at specified x, y)
  [[TYPE_KEYS: text]]                    Type text into currently focused application
  [[HOTKEY: ctrl+c | alt+tab | win+d]]   Dispatch system hotkey combination
  [[ACTIVE_WINDOW]]                      Inspect currently active foreground window title & app
  [[ORGANIZE: downloads | workspace | path]] Smartly categorize & sort files into Documents, Images, Code, etc.
  [[SMART_HOME: url | POST | json]]      Send HTTP request / webhook to local smart home / IoT device

Available Multimodal Desktop Vision:
  [[VISION: question]]                   Capture desktop screenshot and analyze with AI Vision ("What is on my screen?", "Fix this UI error")
  [[SCREEN_ANALYZE: question]]           Alias for VISION

Available Autonomous Coding & Scaffolding:
  [[WRITE_FILE: path | content]]         Create/overwrite any code or text file
  [[EDIT_FILE: path | search | replace]] Surgically replace a specific code snippet without overwriting entire file
  [[READ_FILE: path]]                    Read and inspect a file
  [[RUN_CODE: python/node/cmd | code]]   Execute Python code, Node.js, or run scripts and return terminal output
  [[CREATE_PROJECT: html-app/react/py | name]] Scaffold a complete new project in the workspace
  [[LIST_FILES: path]]                   List files and folders in directory
  [[GIT: command]]                       Run git commands (status, commit, add, diff, log, push)
  [[PLAN: title | step 1 | step 2]]      Coordinate and execute a multi-step execution plan sequentially
  [[GITHUB: owner/repo | issues/prs/readme]] Inspect GitHub repositories, issues, PRs, or README

Available Second Brain (SQLite Notes & Memory):
  [[NOTE: title | content]]              Save rich knowledge, documentation, or note to SQLite Second Brain
  [[SEARCH_NOTES: query]]                Semantic BM25 search over stored notes
  [[DELETE_NOTE: title_or_id]]           Delete a note from Second Brain
  [[REMEMBER: fact]]                     Save lasting memory fact about user
  [[FORGET: keyword]]                    Delete matching memories

Available Proactive Daily Briefing & Reminders:
  [[REMIND: 10m/1h/17:30 | message]]     Schedule a timer/reminder
  [[TIMER: 5m | message]]                Countdown timer
  [[BRIEFING]]                           Get morning daily briefing (weather, news, schedule, system stats)
  [[SCHEDULE_AUTO: every 1h | command]]  Schedule recurring automated background task (e.g. [[SCHEDULE_AUTO: every 1h | SYSTEM: stats]])
  [[LIST_AUTOMATIONS]]                   List active recurring background automations
  [[CANCEL_AUTOMATION: id]]              Cancel a recurring automation

Available Nova Browser Skills (Personal Private Browser & DOM Automation):
  [[BROWSER_OPEN: url or file]]          Open any website, newspaper, or local file in Nova Browser (Edge) with full control
  [[BROWSER_TABS]]                       List all open tabs in Nova Browser (URLs and titles)
  [[BROWSER_ACTIVATE: tab_id or search]] Switch/focus an open tab in Nova Browser
  [[BROWSER_CLOSE: tab_id or search]]    Close a tab in Nova Browser
  [[BROWSER_CLICK: selector_or_text]]    Click any button, link, or element on the active web page
  [[BROWSER_TYPE: selector | text]]      Type text into a search bar or input field
  [[BROWSER_SCROLL: up/down/top/bottom]] Scroll the active web page
  [[BROWSER_RESEARCH: query or url]]     Read and analyze article/page content for research in Nova Browser
  [[BROWSER_YOUTUBE: play [song] | pause | resume | search]] YouTube playback and tab management in Nova Browser
  [[BROWSER_WHATSAPP: phone_number | message]]     WhatsApp Web messaging (uses persistent login)
  [[BROWSER_TELEGRAM: username | message]]         Telegram Web messaging (uses persistent login)

Rules:
1. When asked to code, build, or fix something: write the code cleanly, test it with RUN_CODE, and use EDIT_FILE for surgical fixes.
2. If given a coding task with a project path, write to that path or the default workspace.
3. MULTILINGUAL: Speak in the EXACT language the user speaks (English, Bengali, Hindi, Urdu, Spanish, French, German, Arabic, etc.).
4. MUSIC & YOUTUBE: When asked to play a song, music, or video on YouTube (in ANY language, e.g. English 'play believer on youtube', Bengali 'গান চালাও', 'ইউটিউবে গান বাজাও', 'একটা গান প্লে করো'), ALWAYS use [[PLAY: song name]] or [[BROWSER_YOUTUBE: play | song name]] to search and directly play the video inside Nova Browser. When asked just to open YouTube, use [[PLAY: ]] or [[BROWSER_OPEN: https://www.youtube.com]].
5. BROWSING, NEWSPAPERS, FILES & RESEARCH: When asked to open any website, newspaper (e.g. Prothom Alo, Daily Star, BBC, etc.), browse the web, open a file, or research any topic, ALWAYS use [[BROWSER_OPEN: url or file]] or [[BROWSER_RESEARCH: query or url]] to open it in Nova Browser (Edge) so that you have full DOM control.
"""


DEV_SKILL_DOC = SKILL_DOC

CYBER_ALLOWED_TOOLS = {
    "NOTE", "SEARCH_NOTES", "READ_FILE", "LIST_FILES", "WRITE_FILE",
    "EDIT_FILE", "RUN_CODE", "BROWSER_RESEARCH", "BROWSER_OPEN",
    "TIMER", "REMIND", "BRIEFING", "VISION"
}

CYBER_TOOL_SPECS = {
    "NOTE": "[[NOTE: title | content]]              Save security research, CVE notes, or documentation to SQLite Second Brain",
    "SEARCH_NOTES": "[[SEARCH_NOTES: query]]                Semantic BM25 search over stored notes",
    "READ_FILE": "[[READ_FILE: path]]                    Read and inspect a file, log, or script",
    "LIST_FILES": "[[LIST_FILES: path]]                   List files and folders in directory",
    "WRITE_FILE": "[[WRITE_FILE: path | content]]         Create/overwrite any code, script, or exploit mitigation file",
    "EDIT_FILE": "[[EDIT_FILE: path | search | replace]] Surgically replace a specific code snippet without overwriting entire file",
    "RUN_CODE": "[[RUN_CODE: python/node/cmd | code]]   Execute Python code, Node.js, or run scripts and return terminal output",
    "BROWSER_RESEARCH": "[[BROWSER_RESEARCH: query or url]]     Read and analyze article/security advisory for research",
    "BROWSER_OPEN": "[[BROWSER_OPEN: url or file]]          Open any URL, documentation, or local report in Nova Browser (Edge) with full control",
    "TIMER": "[[TIMER: 5m | message]]                Countdown timer",
    "REMIND": "[[REMIND: 10m/1h/17:30 | message]]     Schedule a timer/reminder",
    "BRIEFING": "[[BRIEFING]]                           Daily security briefing and proactive alerts",
    "VISION": "[[VISION: question]]                   Capture desktop screenshot and analyze with AI Vision",
}

def build_cyber_skill_doc():
    lines = [
        "GUARDRAIL & RULES OF ENGAGEMENT:",
        "Defensive, educational, and authorized use only. Confirm written authorization before testing any system the user does not own. Do not produce working malware, ransomware, credential theft tools, or attack tooling against unauthorized targets. Focus on understanding, detection, prevention, and remediation.",
        "",
        "You are acting as an autonomous CYBERSECURITY INTELLIGENCE & CODING AGENT.",
        "To use a skill, put a tag anywhere in your reply. Tags are executed by the server and removed before speaking to the user.",
        "Always say a natural sentence in the user's language about what you are doing.",
        "Do not put tool tags inside code blocks; write a tag only when you want it executed.",
        "",
        "Available Cybersecurity & Defensive Skills:"
    ]
    for tool in sorted(CYBER_ALLOWED_TOOLS):
        lines.append(f"  {CYBER_TOOL_SPECS[tool]}")
    lines.extend([
        "",
        "Rules:",
        "1. SECURITY & ETHICS: Strictly support authorized, legal, and educational use only. Provide mitigations and defensive explanations.",
        "2. CODING & MITIGATIONS: When asked to write defensive scripts, remediate vulnerabilities, or build tools: write clean code with WRITE_FILE, test it with RUN_CODE, and use EDIT_FILE for surgical fixes.",
        "3. MULTILINGUAL: Speak in the EXACT language the user speaks (English, Bengali, Hindi, Urdu, Spanish, French, German, Arabic, etc.).",
        "4. CONCISE & SPOKEN: Keep spoken explanations technical, sharp, and voice-friendly (1-3 sentences) unless the user asks for deep technical walk-throughs."
    ])
    return "\n".join(lines)

CYBER_SKILL_DOC = build_cyber_skill_doc()


def build_system(cfg, char, mode="developer"):
    mem = get_memory()
    now = datetime.datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
    if mode == "cyber":
        parts = [
            "You are Nova Cyber, a cybersecurity intelligence assistant. You help with threat intelligence, vulnerability analysis, secure coding, network defense, incident response, malware analysis concepts, CTF practice, OSINT methodology, and authorized penetration testing. Explain clearly and technically, with step-by-step guidance and mitigations. Only support authorized, legal, and educational use.",
            "COMMUNICATION RULES:\n"
            "- MULTILINGUAL: You understand and fluently speak ANY language (English, Bengali, Hindi, Urdu, Spanish, French, German, Arabic, Chinese, Japanese, etc.). ALWAYS respond in the exact language the user speaks to you (e.g. if the user speaks in Bengali, reply in Bengali; if in Hindi, reply in Hindi).\n"
            "- VOICE-OPTIMIZED: Keep spoken responses short (1-3 natural sentences) unless asked for an in-depth explanation or technical step-by-step guidance. Avoid markdown code blocks in your spoken voice text; execute skills instead.\n"
            "- TOOL TAGS: Do not put tool tags inside code blocks; write a tag only when you want it executed.\n"
            "- CODING & SECURITY SCRIPTS: When the user asks you to write code, test an exploit mitigation, or build a tool, write the code using [[WRITE_FILE: path | content]] and test/run it with [[RUN_CODE: language | code]]. Follow instructions precisely.",
            f"Current local date/time: {now}. User's OS: {OS}. Default Workspace: {WORKSPACE}.",
        ]
    else:
        parts = [
            f"Your name is {char['name']}. {char['prompt']}",
        "You are an advanced voice-first AI character, full PC controller, and autonomous coding agent living inside the user's PC.",
        "COMMUNICATION RULES:\n"
        "- MULTILINGUAL: You understand and fluently speak ANY language (English, Bengali, Hindi, Urdu, Spanish, French, German, Arabic, Chinese, Japanese, etc.). ALWAYS respond in the exact language the user speaks to you (e.g. if the user speaks in Bengali, reply in Bengali; if in Hindi, reply in Hindi).\n"
        "- VOICE-OPTIMIZED: Keep spoken responses short (1-3 natural sentences) unless asked for an in-depth explanation. Avoid markdown code blocks in your spoken voice text; execute the skills instead.\n"
        "- TOOL TAGS: Do not put tool tags inside code blocks; write a tag only when you want it executed.\n"
        "- MUSIC & YOUTUBE: When asked to play a song, music, or video on YouTube (e.g. 'play a song on youtube', 'play believer', 'গান চালাও', 'ইউটিউবে গান বাজাও', 'একটা গান প্লে করো'), ALWAYS output [[PLAY: song_name]] or [[BROWSER_YOUTUBE: play | song_name]] to immediately play it inside Nova Browser.\n"
        "- BROWSING & RESEARCH: When asked to open any website, newspaper, or file (e.g. 'open newspaper', 'read news', 'খবরের কাগজ খোলো'), ALWAYS open it in Nova Browser using [[BROWSER_OPEN: url]] or [[BROWSER_RESEARCH: url]] so you retain full browser control.\n"
        "- CODING AGENT: When the user asks you to write code or build a project, write the code using [[WRITE_FILE: path | content]] and test/run it with [[RUN_CODE: language | code]]. Follow instructions precisely.",
        f"Current local date/time: {now}. User's OS: {OS}. Default Workspace: {WORKSPACE}.",
    ]
    if cfg.get("user_name"):
        parts.append(f"The user's name is {cfg['user_name']}.")
    user_lang = cfg.get("language", "en-US")
    if user_lang.startswith("bn") or "bengali" in user_lang.lower():
        parts.append("The user's configured primary language is Bengali (বাংলা). Whenever the user speaks in Bengali, greets you in Bengali, or asks in Bengali, you MUST respond in natural Bengali (বাংলা).")
    else:
        parts.append(f"The user's configured language is {user_lang}.")
    if mem:
        parts.append("Things you remember about the user:\n" + "\n".join(f"- {m}" for m in mem))
    active_win = get_active_window_info()
    if active_win and "not supported" not in active_win.lower():
        parts.append(f"Current Foreground Application Context: {active_win}")
    parts.append(CYBER_SKILL_DOC if mode == "cyber" else DEV_SKILL_DOC)
    return "\n\n".join(parts)


# ----------------------------------------------------------------------------
# Skills implementation
# ----------------------------------------------------------------------------
TAG_RE = re.compile(r"\[\[\s*([A-Z_]+)(?:\s*:\s*(.*?))?\s*\]\]", re.S)


def extract_tags(text):
    """
    Extracts tags like [[SKILL: arg]] or [[SKILL]] while gracefully handling
    nested brackets (e.g. [[1, 2], [3, 4]]) inside code snippets.
    Ignores tags inside ``` markdown code fences. Unclosed ``` treats rest as fenced.
    Tags in single `inline` backticks are NOT ignored.
    Returns list of (skill_name, arg, start_index, end_index).
    """
    if not text:
        return []

    fenced_spans = []
    fence_pos = 0
    while True:
        idx = text.find("```", fence_pos)
        if idx == -1:
            break
        close_idx = text.find("```", idx + 3)
        if close_idx == -1:
            fenced_spans.append((idx, len(text)))
            break
        else:
            fenced_spans.append((idx, close_idx + 3))
            fence_pos = close_idx + 3

    results = []
    i = 0
    n = len(text)
    while i < n:
        in_fence = False
        for f_start, f_end in fenced_spans:
            if f_start <= i < f_end:
                i = f_end
                in_fence = True
                break
        if in_fence:
            continue

        start = text.find('[[', i)
        if start == -1:
            break

        in_fence = False
        for f_start, f_end in fenced_spans:
            if f_start <= start < f_end:
                i = f_end
                in_fence = True
                break
        if in_fence:
            continue

        match = re.match(r'\[\[\s*([A-Z_]+)(?:\s*:\s*)?', text[start:])
        if not match:
            i = start + 2
            continue
        skill_name = match.group(1)
        content_start = start + match.end()
        has_colon = ':' in match.group(0)
        depth = 1
        pos = content_start
        matched_end = -1
        while pos < n:
            if text[pos:pos+2] == '[[':
                depth += 1
                pos += 2
            elif text[pos:pos+2] == ']]':
                depth -= 1
                if depth == 0:
                    matched_end = pos + 2
                    arg = text[content_start:pos].strip() if has_colon else ''
                    results.append((skill_name, arg, start, matched_end))
                    i = matched_end
                    break
                pos += 2
            else:
                pos += 1
        if matched_end == -1:
            i = start + 2
    return results


def filter_stream_tags(token_iterator):
    """
    Consumes a generator or iterable of string tokens from an LLM stream.
    Buffers bracket tokens [[ ... ]] so internal tags are never leaked to clients.
    Returns (clean_text_chunks, extracted_tags).
    """
    full_text = ""
    clean_chunks = []
    in_tag = False
    pending_buffer = ""

    for token in token_iterator:
        full_text += token
        pending_buffer += token

        while pending_buffer:
            if not in_tag:
                tag_start = pending_buffer.find("[[")
                if tag_start == -1:
                    if pending_buffer.endswith("["):
                        clean_chunks.append(pending_buffer[:-1])
                        pending_buffer = "["
                    else:
                        clean_chunks.append(pending_buffer)
                        pending_buffer = ""
                else:
                    pre = pending_buffer[:tag_start]
                    if pre:
                        clean_chunks.append(pre)
                    pending_buffer = pending_buffer[tag_start:]
                    in_tag = True
            else:
                tag_end = pending_buffer.find("]]")
                if tag_end == -1:
                    break
                else:
                    pending_buffer = pending_buffer[tag_end + 2:]
                    in_tag = False

    if pending_buffer and not in_tag:
        clean_chunks.append(pending_buffer)

    tags = extract_tags(full_text)
    return clean_chunks, tags



def strip_tags(text):
    """Removes only model-executed skill tags from raw response, preserving surrounding text, fenced examples, and unexecuted tags."""
    tags = extract_tags(text)
    if not tags:
        return (text or "").strip()
    out = []
    last = 0
    for _, _, start, end in tags:
        out.append(text[last:start])
        last = end
    out.append(text[last:])
    return "".join(out).strip()

VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3


def press_vk(code, times=1):
    if OS == "Windows" and ctypes:
        for _ in range(times):
            ctypes.windll.user32.keybd_event(code, 0, 0, 0)
            ctypes.windll.user32.keybd_event(code, 0, 2, 0)
            time.sleep(0.03)


def skill_mouse_move(arg):
    if OS != "Windows" or not ctypes:
        return "Mouse control is currently supported on Windows."
    parts = re.findall(r"\d+", arg)
    if len(parts) < 2:
        return "Refused: MOUSE_MOVE expects 'x, y' (e.g. 500, 300)."
    x, y = int(parts[0]), int(parts[1])
    try:
        max_x = ctypes.windll.user32.GetSystemMetrics(0)
        max_y = ctypes.windll.user32.GetSystemMetrics(1)
        cx = max(0, min(max_x - 1, x))
        cy = max(0, min(max_y - 1, y))
        ctypes.windll.user32.SetCursorPos(cx, cy)
        return f"Moved mouse cursor to ({cx}, {cy})."
    except Exception as e:
        return f"Mouse move failed: {e}"


def skill_mouse_click(arg):
    if OS != "Windows" or not ctypes:
        return "Mouse click is currently supported on Windows."
    raw = (arg or "").strip().lower()
    btn = "left"
    if "right" in raw:
        btn = "right"
    elif "middle" in raw:
        btn = "middle"
    elif "double" in raw:
        btn = "double"

    nums = re.findall(r"\d+", raw)
    if len(nums) >= 2:
        try:
            x, y = int(nums[0]), int(nums[1])
            ctypes.windll.user32.SetCursorPos(x, y)
            time.sleep(0.03)
        except Exception:
            pass

    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040

    try:
        if btn == "left":
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            return "Clicked left button."
        elif btn == "right":
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            return "Clicked right button."
        elif btn == "middle":
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_MIDDLEDOWN, 0, 0, 0, 0)
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_MIDDLEUP, 0, 0, 0, 0)
            return "Clicked middle button."
        elif btn == "double":
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            time.sleep(0.05)
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            return "Double clicked left button."
        return "Clicked left button."
    except Exception as e:
        return f"Mouse click failed: {e}"


def skill_type_keys(text):
    if not text:
        return "Refused: empty text to type."
    if OS == "Windows" and ctypes:
        try:
            KEYEVENTF_UNICODE = 0x0004
            KEYEVENTF_KEYUP = 0x0002
            for ch in text:
                code = ord(ch)
                if ch == "\n":
                    press_vk(0x0D)
                    continue
                ctypes.windll.user32.keybd_event(0, code, KEYEVENTF_UNICODE, 0)
                ctypes.windll.user32.keybd_event(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0)
                time.sleep(0.005)
            return f"Typed text ({len(text)} characters)."
        except Exception as e:
            return f"Type keys failed: {e}"
    return f"Typed text: {text[:40]}"


def skill_hotkey(keys_str):
    if OS != "Windows" or not ctypes:
        return "Hotkey execution is supported on Windows."
    keys = [k.strip().lower() for k in keys_str.replace("+", " ").split()]
    vk_map = {
        "ctrl": 0x11, "control": 0x11,
        "alt": 0x12,
        "shift": 0x10,
        "win": 0x5B, "windows": 0x5B,
        "enter": 0x0D, "return": 0x0D,
        "esc": 0x1B, "escape": 0x1B,
        "tab": 0x09,
        "space": 0x20,
        "backspace": 0x08,
        "delete": 0x2E, "del": 0x2E,
        "c": 0x43, "v": 0x56, "x": 0x58, "a": 0x41, "z": 0x5A, "y": 0x59, "s": 0x53, "f": 0x46,
        "d": 0x44, "t": 0x54, "w": 0x57, "r": 0x52, "p": 0x50,
        "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
        "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B
    }
    vks = []
    for k in keys:
        if k in vk_map:
            vks.append(vk_map[k])
        elif len(k) == 1 and k.isalpha():
            vks.append(ord(k.upper()))
        elif len(k) == 1 and k.isdigit():
            vks.append(ord(k))

    if not vks:
        return f"Refused: unknown keys '{keys_str}'."

    try:
        for code in vks:
            ctypes.windll.user32.keybd_event(code, 0, 0, 0)
        time.sleep(0.04)
        for code in reversed(vks):
            ctypes.windll.user32.keybd_event(code, 0, 2, 0)
        return f"Dispatched hotkey: {'+'.join(keys)}"
    except Exception as e:
        return f"Hotkey failed: {e}"


def get_active_window_info():
    if OS == "Windows" and ctypes:
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return "No active window detected."
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value.strip() or "Untitled Window"
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return f"Active Window: '{title}' (PID: {pid.value})"
        except Exception as e:
            return f"Could not get active window: {e}"
    return "Active window detection is supported on Windows."



# ----------------------------------------------------------------------------
# Sandbox, Process Tree & Confirmation Gate
# ----------------------------------------------------------------------------
PENDING_ACTIONS = {}
PENDING_LOCK = threading.Lock()
FAILS_LOCK = threading.Lock()
CONFIG_CONFIRM_TOKENS = {}
CONFIG_CONFIRM_LOCK = threading.Lock()

DESTRUCTIVE_CMD_PATTERNS = [
    re.compile(r"\bformat\b", re.I),
    re.compile(r"\bdel\b.*[/\\]s.*[a-z]:[\\/]", re.I),
    re.compile(r"\b(?:rd|rmdir)\b.*[/\\]s.*[a-z]:[\\/]", re.I),
    re.compile(r"\brm\s+-(?:r|rf|fr)\s+[/~]", re.I),
    re.compile(r"\bshutdown\b.*(?:/|-)[rs]", re.I),
    re.compile(r"\breg\s+delete\s+hklm", re.I),
    re.compile(r"[a-z]:\\windows", re.I),
    re.compile(r"[a-z]:\\program files", re.I),
    re.compile(r"/etc/|/usr/|/bin/|/sbin/", re.I),
]

def is_destructive_command(cmd_str: str) -> bool:
    c = (cmd_str or "").strip().lower()
    for pat in DESTRUCTIVE_CMD_PATTERNS:
        if pat.search(c):
            return True
    return False

def get_sanitized_subprocess_env(cwd=None):
    base_env = os.environ.copy()
    safe_keys = {
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL",
        "COMSPEC", "PATHEXT", "PYTHONPATH", "NODE_PATH", "SYSTEMDRIVE"
    }
    sanitized = {}
    for k, v in base_env.items():
        k_upper = k.upper()
        if any(bad in k_upper for bad in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH")):
            continue
        if k_upper in safe_keys:
            sanitized[k] = v
            
    ws_str = str((cwd or WORKSPACE).resolve())
    sanitized["HOME"] = ws_str
    sanitized["USERPROFILE"] = ws_str
    return sanitized

def run_sandboxed_process(cmd, shell=False, cwd=None, timeout=60, max_output=102400, extra_env=None):
    try:
        target_cwd = resolve_workspace_path(str(cwd or WORKSPACE))
    except Exception:
        target_cwd = WORKSPACE.resolve()
        
    env = get_sanitized_subprocess_env(target_cwd)
    if extra_env:
        env.update(extra_env)
    creationflags = 0
    if platform.system() == "Windows":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        
    proc = subprocess.Popen(
        cmd,
        shell=shell,
        cwd=str(target_cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
        creationflags=creationflags
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if platform.system() == "Windows":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            proc.kill()
        try:
            stdout, stderr = proc.communicate(timeout=2)
        except Exception:
            stdout, stderr = "", ""
        raise subprocess.TimeoutExpired(cmd, timeout, output=stdout, stderr=stderr)
        
    if stdout and len(stdout) > max_output:
        stdout = stdout[:max_output] + f"\n... [Output truncated at {max_output} chars]"
    if stderr and len(stderr) > max_output:
        stderr = stderr[:max_output] + f"\n... [Stderr truncated at {max_output} chars]"
    return proc.returncode, stdout, stderr

GIT_ALLOWED_SUBCOMMANDS = {
    "status", "diff", "log", "add", "commit", "branch", "checkout", "switch",
    "init", "show", "stash", "restore", "pull", "push", "clone", "remote", "fetch"
}

GIT_SUBCOMMAND_FLAGS = {
    "status": {"-s", "--short", "-b", "--branch", "-u", "--untracked-files", "--ignored"},
    "diff": {"--stat", "--name-only", "--name-status", "--cached", "--staged", "-p", "-u", "--color", "--no-color", "-w", "--ignore-all-space", "-b", "--ignore-space-change"},
    "log": {"-n", "--max-count", "--oneline", "--graph", "--decorate", "--stat", "--name-only", "--since", "--until", "--author", "-p", "--pretty"},
    "add": {"-A", "--all", "-u", "--update", "-f", "--force", "-n", "--dry-run", "--"},
    "commit": {"-m", "--message", "-a", "--all", "-v", "--verbose", "--amend", "--no-edit"},
    "branch": {"-a", "-r", "-v", "-d", "-D", "-m", "-M", "--show-current"},
    "checkout": {"-b", "-B", "-f", "--force", "--"},
    "switch": {"-c", "-C", "--create", "-d", "--detach"},
    "init": {"-b", "--initial-branch", "-q", "--quiet"},
    "show": {"--stat", "--name-only", "--oneline", "-s", "-p"},
    "stash": {"save", "list", "pop", "apply", "drop", "clear", "show"},
    "restore": {"-s", "--source", "-S", "--staged", "-W", "--worktree", "--"},
    "fetch": {"-p", "--prune", "-a", "--all", "-q", "--quiet", "-v", "--verbose", "--tags"},
    "pull": {"-u", "--set-upstream", "-f", "--force", "-v", "--verbose", "-q", "--quiet", "--tags", "--prune"},
    "push": {"-u", "--set-upstream", "-f", "--force", "-v", "--verbose", "-q", "--quiet", "--tags", "--prune"},
    "clone": {"-q", "--quiet", "-v", "--verbose", "--depth", "--single-branch", "-b", "--branch"},
    "remote": {"-v", "--verbose", "get-url", "show"},
}

UNCONDITIONAL_REJECT_FLAGS = {
    "--output", "-o", "--upload-pack", "--receive-pack", "--exec",
    "--no-index", "--ext-diff", "--paginate"
}

FLAGS_WITH_ARGS = {
    "-u", "--untracked-files",
    "-n", "--max-count", "--since", "--until", "--author", "--pretty",
    "-m", "--message",
    "-b", "-B", "--initial-branch",
    "-c", "-C", "--create",
    "-s", "--source",
    "--depth", "--branch",
}

LAST_RUN_CODE_APPROVED_TIME = 0.0
RUN_CODE_TRUST_LOCK = threading.Lock()

NO_CONFIRM_TOOLS = {
    "NOTE", "SEARCH_NOTES", "REMIND", "TIMER", "VOLUME", "MEDIA", "PLAY",
    "SCREENSHOT", "ACTIVE_WINDOW", "GET_WINDOW", "BRIEFING", "MORNING_BRIEFING",
    "LIST_AUTOMATIONS", "AUTOMATIONS", "CANCEL_AUTOMATION", "STOP_AUTOMATION",
    "BROWSER_CLOSE", "BROWSER_RESEARCH"
}

def check_tool_confirmation_required(cfg, name, arg, is_tainted=False, source="pc"):
    if not (cfg or {}).get("confirm_destructive", True):
        return False, ""
    name = unicodedata.normalize("NFKC", (name or "")).strip().upper()
    arg_clean = (arg or "").strip().lower()

    # ALWAYS_CONFIRM
    if name in ("BROWSER_WHATSAPP", "BROWSER_TELEGRAM"):
        return True, f"Browser messaging action '{name}' requires user approval."

    if name == "CLOSE_APP":
        return True, f"Closing application '{arg}' requires user approval."

    if name == "SYSTEM":
        if any(w in arg_clean for w in ("empty_recycle_bin", "empty_trash", "recycle", "shutdown", "restart", "sleep", "lock")):
            return True, f"System action '{arg_clean}' requires user approval."
        if any(w in arg_clean for w in ("stats", "info", "cpu", "ram", "battery", "specs", "minimize", "desktop")):
            if not is_tainted and source == "pc":
                return False, ""

    if name in ("SCHEDULE_AUTO", "AUTOMATE", "AUTORUN"):
        return True, "Scheduling recurring automated tasks requires user approval."

    if name in ("FORGET", "DELETE_NOTE"):
        return True, "Deleting a note or memory requires user approval."

    if name in ("SMART_HOME", "WEBHOOK", "IOT"):
        parts = [p.strip() for p in (arg or "").split("|", 2)]
        method = parts[1].upper() if len(parts) > 1 and parts[1] else "GET"
        if method in ("POST", "PUT", "DELETE", "PATCH"):
            return True, f"Smart home action with method '{method}' requires user approval."
        if not is_tainted and source == "pc":
            return False, ""

    if name in ("BROWSER_CLICK", "BROWSER_TYPE"):
        allowed_domains = ["google.", "bing.com", "duckduckgo.com", "wikipedia.org", "github.com", "stackoverflow.com"]
        tab_url = ""
        try:
            if nova_browser:
                tabs = nova_browser.list_tabs()
                page_tabs = [t for t in tabs if t.get("type") == "page"]
                if page_tabs:
                    tab_url = page_tabs[0].get("url", "").lower()
        except Exception:
            pass
        if not any(d in tab_url for d in allowed_domains) or is_tainted:
            return True, f"Browser interaction '{name}' on external website requires user approval."
        if not is_tainted and source == "pc":
            return False, ""

    if name == "RUN_CODE":
        trusted_mins = int((cfg or {}).get("run_code_trusted_minutes", 0) or 0)
        if trusted_mins > 0 and not is_tainted and source == "pc":
            with RUN_CODE_TRUST_LOCK:
                elapsed = time.time() - LAST_RUN_CODE_APPROVED_TIME
            if elapsed < trusted_mins * 60 and LAST_RUN_CODE_APPROVED_TIME > 0:
                return False, ""
        return True, "Code execution requires user approval (runs with your user permissions)."

    if name in ("CMD", "POWERSHELL"):
        return True, "Direct shell command execution requires user approval."

    if name == "GIT":
        parts = arg_clean.split()
        if parts and parts[0] in ("push", "pull", "clone", "remote"):
            return True, f"Git network action '{parts[0]}' requires user approval."
        if is_tainted:
            return True, "Executing 'GIT' after reading external untrusted content requires user approval."

    if name in ("ORGANIZE", "ORGANIZE_FILES", "ORGANIZE_FOLDER"):
        return True, "Moving or sorting files requires user approval."

    if is_tainted and name in ("WRITE_FILE", "EDIT_FILE", "CREATE_PROJECT", "TYPE_KEYS", "HOTKEY", "MOUSE_CLICK", "GIT"):
        return True, f"Executing '{name}' after reading external untrusted content requires user approval."

    # Deny-by-default rule:
    # NO_CONFIRM tools (untainted desktop only)
    if name in NO_CONFIRM_TOOLS:
        if source == "phone" and name not in {"NOTE", "SEARCH_NOTES", "REMIND", "TIMER", "VOLUME", "MEDIA", "PLAY", "BRIEFING", "LIST_AUTOMATIONS", "CANCEL_AUTOMATION"}:
            return True, f"Action '{name}' requires user confirmation."
        return False, ""

    # Any tool NOT in NO_CONFIRM requires confirmation by default!
    return True, f"Action '{name}' requires user confirmation."

def is_system_folder(path: Path) -> bool:
    try:
        resolved = path.resolve()
        s = str(resolved).lower()
        if platform.system() == "Windows":
            sys_root = os.environ.get("SystemRoot", r"C:\Windows").lower()
            prog_files = os.environ.get("ProgramFiles", r"C:\Program Files").lower()
            prog_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)").lower()
            blocked = [sys_root, prog_files, prog_files_x86, r"c:\windows", r"c:\program files", r"c:\program files (x86)"]
            for b in blocked:
                if b and (s == b or s.startswith(b.rstrip("\\") + "\\")):
                    return True
        else:
            blocked = ["/etc", "/usr", "/bin", "/sbin", "/sys", "/proc", "/dev"]
            for b in blocked:
                if b and (s == b or s.startswith(b.rstrip("/") + "/")):
                    return True
    except Exception:
        pass
    return False


def is_sensitive_nova_file(path: Path) -> bool:
    try:
        resolved = path.resolve()
        root_resolved = ROOT.resolve()
        data_resolved = (ROOT / "data").resolve()
        profile_resolved = (data_resolved / "nova_browser_profile").resolve()

        # Check data/config.json
        if resolved == (data_resolved / "config.json").resolve():
            return True
        # Check data/nova_brain.db
        if resolved == (data_resolved / "nova_brain.db").resolve():
            return True
        # Check data/nova_browser_profile/**
        try:
            if resolved == profile_resolved or resolved.is_relative_to(profile_resolved):
                return True
        except AttributeError:
            if resolved == profile_resolved or profile_resolved in resolved.parents:
                return True
        # Any file named config.json or .env inside Nova install folder
        try:
            if resolved == root_resolved or resolved.is_relative_to(root_resolved):
                name_lower = resolved.name.lower()
                if name_lower in ("config.json", ".env") or name_lower.startswith(".env."):
                    return True
        except AttributeError:
            if root_resolved in resolved.parents or resolved == root_resolved:
                name_lower = resolved.name.lower()
                if name_lower in ("config.json", ".env") or name_lower.startswith(".env."):
                    return True
    except Exception:
        pass
    return False


WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
}

def is_windows_reserved_name(raw: str) -> bool:
    if not raw:
        return False
    clean = str(raw).strip().strip('"\'')
    parts = re.split(r'[/\\]', clean)
    for part in parts:
        part_clean = part.rstrip(". ").upper()
        base = part_clean.split(".")[0].strip()
        if base in WINDOWS_RESERVED_NAMES:
            return True
    return False

def mask_secrets(text: str, cfg: dict = None) -> str:
    if not isinstance(text, str) or not text:
        return text

    # Mask known config secret values
    try:
        conf = cfg if cfg is not None else CONFIG
        if isinstance(conf, dict):
            for sec_key in SECRET_FIELDS:
                val = conf.get(sec_key)
                if val and isinstance(val, str) and len(val) >= 4:
                    text = text.replace(val, val[:4] + "****")
    except Exception:
        pass

    # Authorization: Bearer <token>
    text = re.sub(
        r'(?i)(Authorization:\s*(?:Bearer\s+)?)([^\s,;\'"]+)',
        lambda m: m.group(1) + (m.group(2)[:4] + "****" if len(m.group(2)) > 4 else "****"),
        text
    )

    # Bearer <token>
    text = re.sub(
        r'(?i)(\bBearer\s+)([A-Za-z0-9_\-\.]{8,})',
        lambda m: m.group(1) + m.group(2)[:4] + "****",
        text
    )

    # key=..., token=..., secret=..., password=..., api_key=...
    text = re.sub(
        r'(?i)(\b(?:api[_-]?key|token|secret|password|access[_-]?token)\s*[:=]\s*[\'"]?)([^\s,;\'"&]{4,})([\'"]?)',
        lambda m: m.group(1) + m.group(2)[:4] + "****" + m.group(3),
        text
    )

    # sk- prefixed keys: e.g. sk-1234567890abcdef
    text = re.sub(
        r'\bsk-[a-zA-Z0-9_\-]{8,}\b',
        lambda m: m.group(0)[:7] + "****",
        text
    )

    # Long hex strings (32-128 hex chars)
    text = re.sub(
        r'\b[0-9a-fA-F]{32,128}\b',
        lambda m: m.group(0)[:4] + "****",
        text
    )

    return text

def mask_telemetry(val, cfg=None):
    if isinstance(val, str):
        return mask_secrets(val, cfg)
    elif isinstance(val, dict):
        return {k: mask_telemetry(v, cfg) for k, v in val.items()}
    elif isinstance(val, list):
        return [mask_telemetry(x, cfg) for x in val]
    return val


def resolve_workspace_path(raw_path, cfg=None):
    raw_path = (raw_path or "").strip().strip('"').strip("'")
    if is_windows_reserved_name(raw_path):
        raise ValueError(f"Reserved Windows device name: '{raw_path}'")

    ws_resolved = WORKSPACE.resolve()
    if not raw_path:
        return ws_resolved

    p = Path(raw_path)
    if is_windows_reserved_name(str(p)):
        raise ValueError(f"Reserved Windows device name: '{raw_path}'")

    if not p.is_absolute():
        clean_rel = raw_path.lstrip("/\\")
        p = WORKSPACE / clean_rel

    resolved = p.resolve()
    if is_windows_reserved_name(str(resolved)):
        raise ValueError(f"Reserved Windows device name: '{raw_path}'")

    if is_sensitive_nova_file(resolved):
        raise PermissionError("Access denied: access to sensitive Nova configuration or data files is blocked.")

    is_inside = False
    try:
        is_inside = resolved.is_relative_to(ws_resolved)
    except AttributeError:
        try:
            resolved.relative_to(ws_resolved)
            is_inside = True
        except ValueError:
            is_inside = False

    if is_inside:
        return resolved

    if cfg is None:
        cfg = {}

    if cfg.get("allow_outside_workspace", False):
        if is_system_folder(resolved):
            raise PermissionError("Path is outside the Nova workspace.")
        return resolved

    raise PermissionError("Path is outside the Nova workspace.")


def open_any_app(raw_arg, cfg):
    key = raw_arg.strip().lower()
    if key in ("youtube", "youtube.com"):
        if nova_browser:
            return nova_browser.youtube_action("open", "")
        return open_url("https://www.youtube.com")

    if key in ("browser", "nova browser", "web browser", "internet", "edge", "chrome"):
        if nova_browser:
            res = nova_browser.open_or_activate("https://www.google.com")
            return res.get("message", "Opened Nova Browser")

    apps = {k.lower(): v for k, v in (cfg.get("apps") or {}).items()}
    if key in apps:
        subprocess.Popen(apps[key], shell=False)
        return f"Opened {key}"
    if key.endswith(".exe") and key[:-4] in apps:
        subprocess.Popen(apps[key[:-4]], shell=False)
        return f"Opened {key[:-4]}"
    
    # Common system app shortcuts
    alias = {
        "cmd": ["cmd.exe"],
        "command prompt": ["cmd.exe"],
        "powershell": ["powershell.exe"],
        "terminal": ["wt.exe"] if OS == "Windows" else ["x-terminal-emulator"],
        "control panel": ["control.exe"],
        "word": ["winword.exe"],
        "excel": ["excel.exe"],
        "discord": ["cmd", "/c", "start", "", "discord:"],
        "telegram": ["cmd", "/c", "start", "", "telegram:"],
        "whatsapp": ["cmd", "/c", "start", "", "whatsapp:"],
        "steam": ["cmd", "/c", "start", "", "steam:"],
    }
    if key in alias:
        try:
            subprocess.Popen(alias[key], shell=False)
            return f"Opened {key}"
        except Exception:
            pass

    if OS == "Windows":
        try:
            os.startfile(raw_arg)
            return f"Opened {raw_arg}"
        except Exception:
            try:
                subprocess.Popen(["cmd", "/c", "start", "", raw_arg], shell=False)
                return f"Started {raw_arg}"
            except Exception as e:
                return f"Could not open '{raw_arg}': {e}"
    elif OS == "Darwin":
        subprocess.Popen(["open", "-a", raw_arg])
        return f"Opened {raw_arg}"
    else:
        subprocess.Popen(["xdg-open", raw_arg])
        return f"Opened {raw_arg}"


def close_app(name):
    clean = name.strip().replace('"', '').replace("'", "")
    if OS == "Windows":
        # Try taskkill with .exe
        target = clean if clean.lower().endswith(".exe") else f"{clean}.exe"
        res = subprocess.run(["taskkill", "/f", "/im", target], capture_output=True, text=True)
        if res.returncode == 0:
            return f"Closed {clean}"
        # Case insensitive powershell fallback
        ps = f"Get-Process | Where-Object {{ $_.ProcessName -like '*{clean}*' }} | Stop-Process -Force"
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
        return f"Sent close command for {clean}"
    elif OS == "Darwin" or OS == "Linux":
        subprocess.run(["pkill", "-f", clean], capture_output=True)
        return f"Closed {clean}"
    return f"Closed {clean}"


def control_volume(arg):
    arg = (arg or "").strip().lower()
    if OS != "Windows":
        return "Volume control is currently tuned for Windows."
    if "up" in arg or "increase" in arg or "louder" in arg:
        press_vk(VK_VOLUME_UP, 6)
        return "Volume increased"
    elif "down" in arg or "decrease" in arg or "lower" in arg:
        press_vk(VK_VOLUME_DOWN, 6)
        return "Volume decreased"
    elif "unmute" in arg:
        press_vk(VK_VOLUME_MUTE, 1)
        return "Unmuted volume"
    elif "mute" in arg:
        press_vk(VK_VOLUME_MUTE, 1)
        return "Muted volume"
    
    m = re.search(r"(\d+)", arg)
    if m:
        pct = max(0, min(100, int(m.group(1))))
        press_vk(VK_VOLUME_DOWN, 50)
        press_vk(VK_VOLUME_UP, pct // 2)
        return f"Volume set to ~{pct}%"
    return "Volume adjusted"


def control_media(arg):
    arg = (arg or "").strip().lower()
    if OS == "Windows":
        if "next" in arg or "skip" in arg:
            press_vk(VK_MEDIA_NEXT_TRACK)
            return "Skipped to next track"
        elif "prev" in arg or "previous" in arg or "back" in arg:
            press_vk(VK_MEDIA_PREV_TRACK)
            return "Returned to previous track"
        elif "stop" in arg:
            press_vk(VK_MEDIA_STOP)
            return "Stopped playback"
        else:
            press_vk(VK_MEDIA_PLAY_PAUSE)
            return "Toggled media play/pause"
    return "Media control triggered"


def _capture_desktop_png(target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if OS == "Windows":
        env = os.environ.copy()
        env["SCREEN_PATH"] = str(target)
        ps_code = """
        Add-Type -AssemblyName System.Windows.Forms,System.Drawing
        $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
        $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
        $bmp.Save($env:SCREEN_PATH)
        $g.Dispose()
        $bmp.Dispose()
        """
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_code], env=env, capture_output=True, text=True, timeout=10)
        except Exception:
            pass
    elif OS == "Darwin":
        try:
            subprocess.run(["screencapture", "-x", str(target)], timeout=10)
        except Exception:
            pass
    else:
        try:
            subprocess.run(["import", "-window", "root", str(target)], timeout=10)
        except Exception:
            pass
    return target if target.exists() else None


def skill_screenshot():
    try:
        save_dir = WORKSPACE / "screenshots"
        save_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        target = save_dir / f"screenshot_{stamp}.png"
        captured = _capture_desktop_png(target)
        if captured and captured.exists():
            return f"Screenshot saved to {captured}"
        return "Could not capture screenshot."
    except Exception as e:
        return f"Screenshot failed: {e}"


def get_system_stats():
    lines = []
    lines.append(f"OS: {platform.system()} {platform.release()} ({platform.machine()})")
    cores = os.cpu_count() or 1
    cpu_percent = ""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).LoadPercentage"], capture_output=True, text=True, timeout=4)
        if r.stdout.strip().isdigit():
            cpu_percent = f" ({r.stdout.strip()}% load)"
    except Exception:
        pass
    lines.append(f"CPU: {cores} cores{cpu_percent}")

    if OS == "Windows" and ctypes:
        try:
            class MEM(ctypes.Structure):
                _fields_ = [('l', ctypes.c_ulong), ('load', ctypes.c_ulong), ('tot_p', ctypes.c_ulonglong), ('av_p', ctypes.c_ulonglong), ('tot_pg', ctypes.c_ulonglong), ('av_pg', ctypes.c_ulonglong), ('tot_v', ctypes.c_ulonglong), ('av_v', ctypes.c_ulonglong), ('ext', ctypes.c_ulonglong)]
            m = MEM()
            m.l = ctypes.sizeof(MEM)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            tot_gb = round(m.tot_p / (1024**3), 1)
            free_gb = round(m.av_p / (1024**3), 1)
            used_gb = round(tot_gb - free_gb, 1)
            lines.append(f"RAM: {used_gb} GB used / {tot_gb} GB total ({m.load}% in use)")
        except Exception:
            pass

    try:
        root_path = "C:\\" if OS == "Windows" else "/"
        total, used, free = shutil.disk_usage(root_path)
        lines.append(f"Disk ({root_path}): {free // (1024**3)} GB free / {total // (1024**3)} GB total")
    except Exception:
        pass

    if OS == "Windows" and ctypes:
        try:
            class SPS(ctypes.Structure):
                _fields_ = [('ACLineStatus', ctypes.c_byte), ('BatteryFlag', ctypes.c_byte), ('BatteryLifePercent', ctypes.c_byte), ('SystemStatusFlag', ctypes.c_byte), ('BatteryLifeTime', ctypes.c_ulong), ('BatteryFullLifeTime', ctypes.c_ulong)]
            s = SPS()
            ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s))
            if 0 <= s.BatteryLifePercent <= 100:
                pwr = "Plugged in" if s.ACLineStatus == 1 else "On Battery"
                lines.append(f"Battery: {s.BatteryLifePercent}% ({pwr})")
            else:
                lines.append("Power: AC Connected (Desktop PC)")
        except Exception:
            pass
    return "\n".join(lines)


def control_system(arg):
    arg = (arg or "").strip().lower()
    if "lock" in arg:
        if OS == "Windows" and ctypes:
            ctypes.windll.user32.LockWorkStation()
            return "Workstation locked"
        elif OS == "Darwin":
            subprocess.run(["pmset", "displaysleepnow"])
            return "Screen locked"
    elif "minimize" in arg or "desktop" in arg:
        if OS == "Windows" and ctypes:
            ctypes.windll.user32.keybd_event(0x5B, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0x44, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0x44, 0, 2, 0)
            ctypes.windll.user32.keybd_event(0x5B, 0, 2, 0)
            return "Minimized all windows (Desktop shown)"
    elif "empty_recycle_bin" in arg or "empty_trash" in arg or "recycle" in arg:
        if OS == "Windows" and ctypes:
            try:
                ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 7)
                return "Recycle bin emptied"
            except Exception as e:
                return f"Could not empty recycle bin: {e}"
    elif "sleep" in arg:
        if OS == "Windows":
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
            return "System going to sleep"
    elif "shutdown" in arg:
        if "cancel" in arg or "abort" in arg:
            subprocess.run(["shutdown", "/a"], capture_output=True)
            return "Shutdown cancelled"
        else:
            subprocess.run(["shutdown", "/s", "/t", "60", "/c", "Nova AI scheduled shutdown in 60 seconds"], capture_output=True)
            return "Scheduled shutdown in 60 seconds. Say 'cancel shutdown' to abort."
    elif "restart" in arg or "reboot" in arg:
        subprocess.run(["shutdown", "/r", "/t", "60", "/c", "Nova AI scheduled restart in 60 seconds"], capture_output=True)
        return "Scheduled restart in 60 seconds. Say 'cancel shutdown' to abort."
    elif "stats" in arg or "info" in arg or "cpu" in arg or "ram" in arg or "battery" in arg or "specs" in arg:
        return get_system_stats()
    return f"Executed system action {arg}"


def skill_write_file(arg, cfg=None):
    parts = arg.split("|", 1)
    if len(parts) < 2:
        return "Refused: WRITE_FILE expects 'path | file_content'."
    raw_path, content = parts[0].strip(), parts[1]
    if content.startswith("\r\n"):
        content = content[2:]
    elif content.startswith("\n") or content.startswith(" "):
        content = content[1:]
    # Unescape escaped newlines if LLM returned single-line escaped string
    if "\n" not in content and "\\n" in content:
        content = content.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
    try:
        target = resolve_workspace_path(raw_path, cfg=cfg)
    except (PermissionError, ValueError) as e:
        return str(e) or "Path is outside the Nova workspace."
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Created file {target.name} at {target} ({len(content)} characters, {len(content.splitlines())} lines)."


def skill_edit_file(arg, cfg=None):
    parts = arg.split("|", 2)
    if len(parts) < 3:
        return "Refused: EDIT_FILE expects 'path | search_target | replacement'."
    raw_path, target_str, replacement = parts[0].strip(), parts[1].strip(), parts[2]
    if replacement.startswith("\r\n"):
        replacement = replacement[2:]
    elif replacement.startswith("\n") or replacement.startswith(" "):
        replacement = replacement[1:]

    try:
        target_file = resolve_workspace_path(raw_path, cfg=cfg)
    except (PermissionError, ValueError) as e:
        return str(e) or "Path is outside the Nova workspace."
    if not target_file.exists():
        return f"File not found: {target_file}"
    content = target_file.read_text(encoding="utf-8")
    if target_str not in content:
        if target_str.strip() in content:
            target_str = target_str.strip()
        else:
            return f"Search target not found in {target_file.name}. Could not apply edit."

    new_content = content.replace(target_str, replacement, 1)
    target_file.write_text(new_content, encoding="utf-8")
    return f"Successfully edited {target_file.name} (replaced {len(target_str)} chars with {len(replacement)} chars)."


def skill_create_project(arg, cfg=None):
    parts = [p.strip() for p in arg.split("|", 1)]
    template = parts[0].lower() if parts else "html-app"
    name = parts[1] if len(parts) > 1 else f"project_{int(time.time())}"
    try:
        dest = resolve_workspace_path(name, cfg=cfg)
    except (PermissionError, ValueError) as e:
        return str(e) or "Path is outside the Nova workspace." 
    dest.mkdir(parents=True, exist_ok=True)
    if "react" in template:
        (dest / "index.html").write_text(f"<!doctype html><html><head><title>{name}</title></head><body><div id='root'></div><script type='module' src='/src/main.jsx'></script></body></html>", encoding="utf-8")
        src = dest / "src"
        src.mkdir(exist_ok=True)
        (src / "main.jsx").write_text(f"import React from 'react';\nimport ReactDOM from 'react-dom/client';\n\nReactDOM.createRoot(document.getElementById('root')).render(<h1>Hello from {name}!</h1>);\n", encoding="utf-8")
        (dest / "package.json").write_text(json.dumps({"name": name, "version": "1.0.0", "scripts": {"dev": "vite"}}, indent=2), encoding="utf-8")
        return f"Created project '{name}' with React template at {dest}."
    elif "py" in template:
        (dest / "main.py").write_text(f'"""\nCLI Project: {name}\n"""\n\ndef main():\n    print("Running {name}...")\n\nif __name__ == "__main__":\n    main()\n', encoding="utf-8")
        (dest / "requirements.txt").write_text("", encoding="utf-8")
        (dest / "README.md").write_text(f"# {name}\n\nRun with `python main.py`\n", encoding="utf-8")
        return f"Created project '{name}' with Python CLI template at {dest}."
    else:  # html-app
        (dest / "index.html").write_text(f'<!doctype html>\n<html lang="en">\n<head>\n  <meta charset="utf-8">\n  <title>{name}</title>\n  <link rel="stylesheet" href="style.css">\n</head>\n<body>\n  <main>\n    <h1>Welcome to {name}</h1>\n    <p>Built with Nova AI.</p>\n  </main>\n  <script src="app.js"></script>\n</body>\n</html>', encoding="utf-8")
        (dest / "style.css").write_text("body { font-family: system-ui, sans-serif; background: #0b0f19; color: #fff; margin: 0; padding: 2rem; }\nh1 { color: #38bdf8; }", encoding="utf-8")
        (dest / "app.js").write_text(f'console.log("App {name} loaded.");', encoding="utf-8")
        return f"Created project '{name}' with modern HTML5/CSS/JS template at {dest}."


def skill_screen_analyze(question=""):
    try:
        import base64
        cfg = get_config()
        save_dir = WORKSPACE / "screenshots"
        save_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        target = save_dir / f"vision_{stamp}.png"
        captured = _capture_desktop_png(target)
        if not captured or not captured.exists():
            return "Could not capture screenshot for vision analysis."

        raw_bytes = target.read_bytes()
        b64_img = base64.b64encode(raw_bytes).decode("ascii")
        prompt = question.strip() if question.strip() else "What is currently visible on my screen? Provide a concise summary or identify any errors/relevant items."
        res = call_llm_vision(cfg, prompt, b64_img)
        return f"[Screen Vision Analysis]:\n{res}"
    except Exception as e:
        return f"Vision analysis failed: {e}"


def skill_read_file(raw_path, cfg=None):
    try:
        target = resolve_workspace_path(raw_path.strip(), cfg=cfg)
    except (PermissionError, ValueError) as e:
        return str(e) or "Path is outside the Nova workspace."
    if not target.exists():
        return f"File not found: {target}"
    if target.is_dir():
        return f"{target} is a directory. Use LIST_FILES instead."
    text = target.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) > 200:
        return f"File {target.name} ({len(lines)} lines):\n" + "\n".join(lines[:200]) + f"\n... [Truncated: {len(lines) - 200} more lines]"
    return f"File {target.name}:\n{text}"


def skill_list_files(raw_path, cfg=None):
    try:
        target = resolve_workspace_path(raw_path.strip() if raw_path.strip() else str(WORKSPACE), cfg=cfg)
    except (PermissionError, ValueError) as e:
        return str(e) or "Path is outside the Nova workspace." 
    if not target.exists():
        return f"Directory does not exist: {target}"
    items = []
    try:
        for it in sorted(target.iterdir()):
            if is_sensitive_nova_file(it):
                continue
            kind = "[DIR] " if it.is_dir() else "[FILE]"
            size = f"{it.stat().st_size} bytes" if it.is_file() else ""
            items.append(f"{kind} {it.name:24} {size}")
        return f"Contents of {target}:\n" + ("\n".join(items) if items else "(empty directory)")
    except Exception as e:
        return f"Error listing files: {e}"


def skill_organize_folder(target_path="", cfg=None):
    raw = (target_path or "").strip().strip('"').strip("'")
    if not raw or raw.lower() in ("downloads", "download"):
        target_dir = Path.home() / "Downloads"
    elif raw.lower() in ("workspace", "work"):
        target_dir = WORKSPACE
    else:
        try:
            target_dir = resolve_workspace_path(raw, cfg=cfg)
        except PermissionError:
            p = Path(raw).resolve()
            if p.is_dir() and not is_system_folder(p):
                target_dir = p
            else:
                return "Path is outside the Nova workspace." 

    if not target_dir.exists() or not target_dir.is_dir():
        return f"Directory not found: {target_dir}"

    categories = {
        "Documents": {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".txt", ".csv", ".rtf", ".odt"},
        "Images": {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp", ".ico"},
        "Code": {".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".json", ".xml", ".sh", ".bat", ".ps1", ".sql", ".cpp", ".c", ".java"},
        "Installers": {".exe", ".msi", ".dmg", ".pkg", ".iso"},
        "Archives": {".zip", ".tar", ".gz", ".7z", ".rar"},
        "Media": {".mp3", ".wav", ".mp4", ".mkv", ".mov", ".avi", ".flac"}
    }
    moved_count = 0
    summary = []
    try:
        for item in list(target_dir.iterdir()):
            if item.is_file() and not item.name.startswith((".", "~")):
                ext = item.suffix.lower()
                dest_cat = None
                for cat, exts in categories.items():
                    if ext in exts:
                        dest_cat = cat
                        break
                if dest_cat:
                    cat_folder = target_dir / dest_cat
                    cat_folder.mkdir(exist_ok=True)
                    dest_file = cat_folder / item.name
                    if not dest_file.exists():
                        shutil.move(str(item), str(dest_file))
                        moved_count += 1
                        summary.append(f"{item.name} -> {dest_cat}/")

        if moved_count == 0:
            return f"Directory {target_dir.name} is already well organized. No files needed moving."
        return f"Organized {moved_count} file(s) in {target_dir.name}:\n" + "\n".join(summary[:15]) + (f"\n... and {moved_count - 15} more" if moved_count > 15 else "")
    except Exception as e:
        return f"Organize folder error: {e}"


def skill_run_code(arg, cfg=None):
    parts = arg.split("|", 1)
    if len(parts) < 2:
        lang = "python"
        code = arg.strip()
    else:
        lang = parts[0].strip().lower()
        code = parts[1].strip()
    
    timeout = max(1, min(300, int((cfg or {}).get("process_timeout", 60))))
    is_inline = "\n" in code or ("print(" in code or "def " in code or "class " in code or "console.log" in code)
    if is_inline:
        ext = ".py" if "py" in lang else ".js" if "node" in lang or "js" in lang else ".ps1" if "ps" in lang else ".bat"
        run_file = WORKSPACE / f"_run_temp{ext}"
        run_file.write_text(code, encoding="utf-8")
        if "py" in lang:
            cmd = ["python", str(run_file)]
        elif "node" in lang or "js" in lang:
            cmd = ["node", str(run_file)]
        elif "ps" in lang:
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(run_file)]
        else:
            cmd = ["cmd", "/c", str(run_file)]
    else:
        trimmed = code.strip().strip('"').strip("'")
        if trimmed.endswith(".py"):
            try:
                target_file = resolve_workspace_path(trimmed, cfg=cfg)
            except (PermissionError, ValueError):
                return "Path is outside the Nova workspace."
            cmd = ["python", str(target_file)]
        elif trimmed.endswith(".js"):
            try:
                target_file = resolve_workspace_path(trimmed, cfg=cfg)
            except (PermissionError, ValueError):
                return "Path is outside the Nova workspace."
            cmd = ["node", str(target_file)]
        elif trimmed.endswith(".ps1"):
            try:
                target_file = resolve_workspace_path(trimmed, cfg=cfg)
            except (PermissionError, ValueError):
                return "Path is outside the Nova workspace."
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(target_file)]
        elif trimmed.startswith(("python ", "py ", "node ", "pip ", "npm ", "git ", "cmd ", "powershell ")):
            cmd = code
        elif "py" in lang and not trimmed.startswith("python"):
            try:
                target_file = resolve_workspace_path(trimmed, cfg=cfg)
            except (PermissionError, ValueError):
                return "Path is outside the Nova workspace."
            cmd = ["python", str(target_file)]
        else:
            cmd = code

    try:
        t0 = time.time()
        retcode, out, err = run_sandboxed_process(cmd, shell=isinstance(cmd, str), cwd=WORKSPACE, timeout=timeout)
        dur = round(time.time() - t0, 2)
        out = (out or "").strip()
        err = (err or "").strip()
        result_lines = [f"Exit code: {retcode} (in {dur}s)"]
        if out:
            result_lines.append(f"STDOUT:\n{out[:2500]}")
        if err:
            result_lines.append(f"STDERR:\n{err[:2500]}")
        if not out and not err:
            result_lines.append("(Process completed successfully with no console output)")
        return "\n".join(result_lines)
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout} seconds."
    except Exception as e:
        return f"Execution error: {e}"


def skill_cmd(command, cfg=None):
    if is_destructive_command(command):
        return "Refused: blocked destructive system pattern detected."
    timeout = max(1, min(300, int((cfg or {}).get("process_timeout", 45))))
    try:
        retcode, out, err = run_sandboxed_process(command, shell=True, cwd=WORKSPACE, timeout=timeout)
        res_str = f"Exit code {retcode}"
        if out: res_str += f"\nOutput:\n{out[:2500]}"
        if err: res_str += f"\nErrors:\n{err[:2000]}"
        return res_str
    except subprocess.TimeoutExpired:
        return f"CMD timed out after {timeout} seconds."
    except Exception as e:
        return f"CMD error: {e}"


def skill_powershell(script, cfg=None):
    if is_destructive_command(script):
        return "Refused: blocked destructive system pattern detected."
    timeout = max(1, min(300, int((cfg or {}).get("process_timeout", 45))))
    try:
        cmd = ["powershell", "-NoProfile", "-Command", script]
        retcode, out, err = run_sandboxed_process(cmd, shell=False, cwd=WORKSPACE, timeout=timeout)
        res_str = f"Exit code {retcode}"
        if out: res_str += f"\nOutput:\n{out[:2500]}"
        if err: res_str += f"\nErrors:\n{err[:2000]}"
        return res_str
    except subprocess.TimeoutExpired:
        return f"PowerShell timed out after {timeout} seconds."
    except Exception as e:
        return f"PowerShell error: {e}"


def skill_git(arg, cfg=None):
    raw_arg = (arg or "").strip()
    if not raw_arg:
        return "Refused: GIT requires a subcommand."

    # Check for shell operators
    if any(op in raw_arg for op in ("&", "|", ";", ">", "<", "`", "$(")):
        return "Refused: shell operators are not permitted in git commands."

    try:
        tokens = shlex.split(raw_arg)
    except Exception as e:
        return f"Refused: invalid git command syntax ({e})."

    if not tokens:
        return "Refused: empty git arguments."

    # 1. Check unconditional reject flags anywhere in tokens
    for tok in tokens:
        tok_lower = tok.lower()
        for bad in UNCONDITIONAL_REJECT_FLAGS:
            if tok == bad or tok_lower == bad or tok_lower.startswith(bad + "=") or tok_lower.startswith(bad):
                return f"Git flag '{tok}' is disallowed for security."
        if tok in ("-C", "--exec-path") or tok_lower.startswith(("-C", "--work-tree", "--git-dir", "--exec-path")):
            return f"Git flag '{tok}' is disallowed for security."

    # 2. Find the subcommand (first token not starting with -)
    subcmd = None
    subcmd_idx = -1
    skip_arg = False
    for i, tok in enumerate(tokens):
        if skip_arg:
            skip_arg = False
            continue
        if tok in ("-c", "-C", "--exec-path"):
            return f"Git flag '{tok}' is disallowed for security."
        if not tok.startswith("-"):
            subcmd = tok.lower()
            subcmd_idx = i
            break
        if tok == "-C":
            skip_arg = True

    if not subcmd or subcmd not in GIT_ALLOWED_SUBCOMMANDS:
        return f"Refused: git subcommand '{subcmd or ''}' is not permitted."

    # Reject any global flags before the subcommand
    for tok in tokens[:subcmd_idx]:
        return f"Git flag '{tok}' is not permitted for subcommand '{subcmd}' (disallowed for security)."

    allowed_flags = GIT_SUBCOMMAND_FLAGS.get(subcmd, set())
    skip_next = False

    for i in range(subcmd_idx + 1, len(tokens)):
        tok = tokens[i]
        if skip_next:
            skip_next = False
            continue

        tok_lower = tok.lower()
        # Check unconditional rejects
        for bad in UNCONDITIONAL_REJECT_FLAGS:
            if tok == bad or tok_lower == bad or tok_lower.startswith(bad + "=") or tok_lower.startswith(bad):
                return f"Git flag '{tok}' is not permitted for subcommand '{subcmd}' (disallowed for security)."

        # Reject config or directory escapes
        if tok in ("-C", "--exec-path") or tok_lower.startswith(("-C", "--work-tree", "--git-dir", "--exec-path")):
            return f"Git flag '{tok}' is not permitted for subcommand '{subcmd}' (disallowed for security)."

        if tok.startswith("-c") and subcmd != "switch":
            return f"Git flag '{tok}' is not permitted for subcommand '{subcmd}' (disallowed for security)."

        if tok.startswith("-"):
            flag_name = tok.split("=", 1)[0]
            if flag_name not in allowed_flags:
                # Check fused short flags like -m"msg" or -n5
                if len(tok) > 2 and tok[:2] in allowed_flags and tok[:2] in FLAGS_WITH_ARGS:
                    pass
                else:
                    return f"Git flag '{tok}' is not permitted for subcommand '{subcmd}' (disallowed for security)."
            else:
                if "=" not in tok and flag_name in FLAGS_WITH_ARGS:
                    skip_next = True
        else:
            # Positional argument
            if subcmd in ("clone", "remote", "push", "pull"):
                if "://" in tok or tok.startswith(("git@", "ext::", "file:")):
                    if not tok.startswith(("https://", "http://", "ssh://", "git@")):
                        return f"Refused: git URL '{tok}' is not permitted. Only https://, http://, ssh://, or git@ URLs are allowed."
            if subcmd == "remote":
                if tok.lower() not in ("-v", "--verbose", "get-url", "show"):
                    return f"Refused: git remote modifying command '{tok}' is disallowed."
            elif subcmd == "stash":
                if tok.lower() not in ("save", "list", "pop", "apply", "drop", "clear", "show"):
                    return f"Git flag '{tok}' is not permitted for subcommand 'stash' (disallowed for security)."
            elif subcmd in ("add", "checkout", "restore", "diff", "log"):
                if "/" in tok or "\\" in tok or (len(tok) >= 2 and tok[1] == ":") or tok.startswith("."):
                    try:
                        resolve_workspace_path(tok, cfg=cfg)
                    except PermissionError:
                        return "Path is outside the Nova workspace."

    try:
        empty_dev = "NUL" if OS == "Windows" else "/dev/null"
        safe_configs = [
            "-c", "core.hooksPath=",
            "-c", "core.fsmonitor=false",
            "-c", "protocol.ext.allow=never",
        ]
        cmd = ["git"] + safe_configs + tokens
        git_env = {
            "GIT_CONFIG_GLOBAL": empty_dev,
            "GIT_CONFIG_SYSTEM": empty_dev,
            "GIT_TERMINAL_PROMPT": "0",
        }
        retcode, out, err = run_sandboxed_process(cmd, shell=False, cwd=WORKSPACE, timeout=30, extra_env=git_env)
        return (out or err or f"Git completed with code {retcode}")[:2500]
    except subprocess.TimeoutExpired:
        return "Git command timed out after 30 seconds."
    except Exception as e:
        return f"Git error: {e}"

class SmartHomeRedirectBlocked(Exception):
    pass

class SmartHomeRedirectBlocker(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SmartHomeRedirectBlocked("Refused: smart home redirects are blocked for security.")
    def http_error_301(self, req, fp, code, msg, headers):
        raise SmartHomeRedirectBlocked("Refused: smart home redirects are blocked for security.")
    def http_error_302(self, req, fp, code, msg, headers):
        raise SmartHomeRedirectBlocked("Refused: smart home redirects are blocked for security.")
    def http_error_303(self, req, fp, code, msg, headers):
        raise SmartHomeRedirectBlocked("Refused: smart home redirects are blocked for security.")
    def http_error_307(self, req, fp, code, msg, headers):
        raise SmartHomeRedirectBlocked("Refused: smart home redirects are blocked for security.")
    def http_error_308(self, req, fp, code, msg, headers):
        raise SmartHomeRedirectBlocked("Refused: smart home redirects are blocked for security.")

SMART_HOME_ALLOWED_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
]
LINK_LOCAL_NET = ipaddress.ip_network("169.254.0.0/16")

def is_allowed_smart_home_host(hostname, cfg=None):
    if not hostname:
        return False, "Missing hostname."

    cfg = cfg or {}
    configured_hosts = {h.strip().lower() for h in (cfg.get("smart_home_hosts") or []) if isinstance(h, str)}
    is_explicit = hostname.lower() in configured_hosts

    try:
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        resolved_ips = list({ai[4][0] for ai in addr_info})
    except Exception as e:
        return False, f"Failed to resolve hostname '{hostname}': {e}"

    if not resolved_ips:
        return False, f"Could not resolve any IP address for '{hostname}'."

    for ip_str in resolved_ips:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False, f"Invalid resolved IP '{ip_str}'."

        if (ip.version == 4 and ip in LINK_LOCAL_NET) or ip.is_link_local:
            return False, f"Link-local and cloud metadata addresses (169.254.0.0/16) are blocked for security: {ip_str}."

        if is_explicit:
            continue

        if ip.version == 4:
            if not any(ip in net for net in SMART_HOME_ALLOWED_NETS):
                return False, f"Host '{hostname}' resolved to {ip_str}, which is not an allowed private LAN address (10/8, 172.16/12, 192.168/16, 127/8)."
        elif ip.version == 6:
            if not (ip.is_loopback or ip.is_private):
                return False, f"Host '{hostname}' resolved to {ip_str}, which is not an allowed private IPv6 address."

    return True, "OK"

def skill_smart_home(arg):
    parts = [p.strip() for p in (arg or "").split("|", 2)]
    if not parts or not parts[0]:
        return "Refused: SMART_HOME expects 'url | optional_method | optional_json_payload'."
    url = parts[0]
    method = parts[1].upper() if len(parts) > 1 and parts[1] else "GET"
    payload_str = parts[2] if len(parts) > 2 else ""

    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme and parsed.scheme.lower() not in ("http", "https"):
        return f"Refused: SMART_HOME only supports http and https schemes (got '{parsed.scheme}')."
    if not parsed.scheme:
        url = "http://" + url
        parsed = urllib.parse.urlsplit(url)

    if parsed.scheme.lower() not in ("http", "https"):
        return f"Refused: SMART_HOME only supports http and https schemes (got '{parsed.scheme}')."

    hostname = parsed.hostname
    if not hostname:
        return "Refused: SMART_HOME expects a valid URL with hostname."

    cfg = get_config()
    allowed, reason = is_allowed_smart_home_host(hostname, cfg)
    if not allowed:
        return f"Refused: {reason}"

    headers = {"Content-Type": "application/json", "User-Agent": "NovaAI-SmartHome/1.0"}
    ha_token = cfg.get("smart_home_token")
    if ha_token:
        headers["Authorization"] = f"Bearer {ha_token}"

    data_bytes = payload_str.encode("utf-8") if payload_str else None
    if method in ("POST", "PUT", "PATCH") and data_bytes is None:
        data_bytes = b"{}"

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        opener = urllib.request.build_opener(SmartHomeRedirectBlocker)
        with opener.open(req, timeout=5) as resp:
            resp_data = resp.read().decode("utf-8", errors="replace")[:600]
            return f"Smart Home request to {url} succeeded ({resp.status}): {resp_data or 'OK'}"
    except SmartHomeRedirectBlocked:
        return "Refused: smart home redirects are blocked for security."
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308) or "redirect" in str(e).lower():
            return "Refused: smart home redirects are blocked for security."
        return f"Smart Home request failed: {e}"
    except Exception as e:
        if "redirect" in str(e).lower():
            return "Refused: smart home redirects are blocked for security."
        return f"Smart Home request failed: {e}"



def open_url(url):
    url = (url or "").strip().strip('"').strip("'")
    if not url:
        return "Refused: empty URL or file path."

    # If it's a local file (e.g. newspaper article, html file, pdf, text file)
    resolved_file = None
    if os.path.exists(url):
        resolved_file = Path(url).resolve()
    elif (ROOT / url).exists():
        resolved_file = (ROOT / url).resolve()
    elif (WORKSPACE / url).exists():
        resolved_file = (WORKSPACE / url).resolve()
    elif url.startswith("file:///"):
        pass

    if resolved_file:
        url = resolved_file.as_uri()
    elif not re.match(r"^(https?|file):", url, re.I):
        if "." in url and not url.startswith("/") and " " not in url:
            url = "https://" + url
        else:
            url = f"https://www.google.com/search?q={urllib.parse.quote_plus(url)}"

    # Always use Nova Browser (Edge with CDP control)
    if nova_browser:
        try:
            res = nova_browser.open_or_activate(url)
            return res.get("message") or f"Opened {url} in Nova Browser"
        except Exception as e:
            print(f"[Nova Browser] Error opening {url}: {e}")

    try:
        if OS == "Windows":
            try:
                os.startfile(url)
            except Exception:
                subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)
        else:
            webbrowser.open(url)
        return f"Opened {url}"
    except Exception as e:
        webbrowser.open(url)
        return f"Opened {url}"


def run_skill(cfg, name, arg, source="pc", is_confirmed=False, mode="developer"):
    try:
        name = name.strip().upper()
        raw_arg = (arg or "").strip()

        if mode == "cyber" and name not in CYBER_ALLOWED_TOOLS:
            return "Not available in Cyber Mode"

        SAFE_REMOTE_TOOLS = {
            "NOTE", "SEARCH_NOTES", "REMIND", "TIMER", "VOLUME", "MEDIA", "PLAY",
            "BRIEFING", "LIST_AUTOMATIONS", "CANCEL_AUTOMATION"
        }
        if source == "phone" and not (cfg or {}).get("remote_allow_dangerous", False):
            if name not in SAFE_REMOTE_TOOLS:
                return f"Blocked: Tool '{name}' is disabled on mobile remote for security. Set 'remote_allow_dangerous': true to allow." 
        if name == "OPEN_APP":
            return open_any_app(raw_arg, cfg)
        if name == "CLOSE_APP":
            return close_app(raw_arg)
        if name == "VOLUME":
            return control_volume(raw_arg)
        if name == "MEDIA":
            return control_media(raw_arg)
        if name == "SCREENSHOT":
            return skill_screenshot()
        if name == "SYSTEM":
            return control_system(raw_arg)
        if name == "CMD":
            return skill_cmd(raw_arg, cfg=cfg)
        if name == "POWERSHELL":
            return skill_powershell(raw_arg, cfg=cfg)
        if name == "WRITE_FILE":
            return skill_write_file(raw_arg, cfg=cfg)
        if name == "EDIT_FILE":
            return skill_edit_file(raw_arg, cfg=cfg)
        if name == "CREATE_PROJECT":
            return skill_create_project(raw_arg, cfg=cfg)
        if name == "READ_FILE":
            return skill_read_file(raw_arg, cfg=cfg)
        if name == "RUN_CODE":
            return skill_run_code(raw_arg, cfg=cfg)
        if name == "LIST_FILES":
            return skill_list_files(raw_arg, cfg=cfg)
        if name == "PLAN":
            if not plan_mode:
                return "Plan Mode coordinator not available."
            parsed = plan_mode.parse_plan_tag(raw_arg)
            if not parsed.get("steps"):
                return f"Plan '{parsed.get('title', 'Execution Plan')}' has no steps."
            batch_res = plan_mode.execute_plan_batch(parsed, cfg=cfg)
            if batch_res.get("ok"):
                completed_count = len(batch_res.get("completed", []))
                return f"Plan '{parsed['title']}' executed successfully ({completed_count} steps completed)."
            else:
                return f"Plan '{parsed['title']}' aborted at step '{batch_res.get('failed_step')}': {batch_res.get('error')}"
        if name in ("ORGANIZE", "ORGANIZE_FILES", "ORGANIZE_FOLDER"):
            return skill_organize_folder(raw_arg, cfg=cfg)
        if name == "GIT":
            return skill_git(raw_arg, cfg=cfg)
        if name == "GITHUB":
            if not integrations or "github" not in integrations.REGISTRY:
                return "GitHub integration connector not available."
            return integrations.REGISTRY["github"].run(cfg, raw_arg)
        if name == "MOUSE_MOVE":
            return skill_mouse_move(raw_arg)
        if name == "MOUSE_CLICK":
            return skill_mouse_click(raw_arg)
        if name == "TYPE_KEYS":
            return skill_type_keys(raw_arg)
        if name == "HOTKEY":
            return skill_hotkey(raw_arg)
        if name in ("ACTIVE_WINDOW", "GET_WINDOW"):
            return get_active_window_info()
        if name in ("VISION", "SCREEN_ANALYZE"):
            return skill_screen_analyze(raw_arg)
        if name == "NOTE":
            if not memory_engine:
                return "Memory engine not available."
            parts = [p.strip() for p in raw_arg.split("|", 1)]
            title = parts[0] if parts else "Note"
            content = parts[1] if len(parts) > 1 else ""
            nid = memory_engine.save_note(title, content)
            return f"Saved note '{title}' to Second Brain (ID #{nid})."
        if name == "SEARCH_NOTES":
            if not memory_engine:
                return "Memory engine not available."
            res = memory_engine.search_notes(raw_arg)
            if not res:
                return f"No notes found matching '{raw_arg}'."
            lines = [f"- [{n['title']}]: {n['content'][:140]}" for n in res]
            return f"Found {len(res)} note(s):\n" + "\n".join(lines)
        if name == "DELETE_NOTE":
            if not memory_engine:
                return "Memory engine not available."
            ok = memory_engine.delete_note(raw_arg)
            return f"Deleted note '{raw_arg}'." if ok else f"Note '{raw_arg}' not found."
        if name in ("REMIND", "REMINDER"):
            if not scheduler_engine:
                return "Scheduler not available."
            parts = [p.strip() for p in raw_arg.split("|")]
            action = None
            if len(parts) >= 3:
                spec = parts[0]
                msg = parts[1]
                action = "|".join(parts[2:]).strip()
            elif len(parts) == 2:
                spec = parts[0]
                second = parts[1]
                tool_prefixes = ("SYSTEM:", "CMD:", "POWERSHELL:", "WRITE_FILE:", "EDIT_FILE:", "RUN_CODE:", "NOTE:", "GIT:", "READ_FILE:", "LIST_FILES:")
                if second.startswith("[[") or any(second.upper().startswith(p) for p in tool_prefixes):
                    action = second
                    msg = "Reminder"
                else:
                    msg = second
            else:
                val = parts[0] if parts else "5m"
                if re.match(r"^(?:in\s+)?(?:\d+(?:\.\d+)?\s*(?:s|m|h|min|sec|hour|mins|minutes|hours?)|(?:\d{1,2}:\d{2}))(?:\s*(?:am|pm))?$", val, re.I):
                    spec = val
                    msg = "Reminder"
                else:
                    spec = "5m"
                    msg = val
            tid = scheduler_engine.SCHEDULER.add_timer(spec, msg, mode=mode, action=action)
            return f"Scheduled reminder in {spec}: '{msg}' (Timer #{tid})."
        if name == "TIMER":
            if not scheduler_engine:
                return "Scheduler not available."
            parts = [p.strip() for p in raw_arg.split("|")]
            action = None
            if len(parts) >= 3:
                spec = parts[0]
                msg = parts[1]
                action = "|".join(parts[2:]).strip()
            elif len(parts) == 2:
                spec = parts[0]
                second = parts[1]
                tool_prefixes = ("SYSTEM:", "CMD:", "POWERSHELL:", "WRITE_FILE:", "EDIT_FILE:", "RUN_CODE:", "NOTE:", "GIT:", "READ_FILE:", "LIST_FILES:")
                if second.startswith("[[") or any(second.upper().startswith(p) for p in tool_prefixes):
                    action = second
                    msg = "Timer finished!"
                else:
                    msg = second
            else:
                val = parts[0] if parts else "5m"
                if re.match(r"^(?:in\s+)?(?:\d+(?:\.\d+)?\s*(?:s|m|h|min|sec|hour|mins|minutes|hours?)|(?:\d{1,2}:\d{2}))(?:\s*(?:am|pm))?$", val, re.I):
                    spec = val
                    msg = "Timer finished!"
                else:
                    spec = "5m"
                    msg = val
            tid = scheduler_engine.SCHEDULER.add_timer(spec, msg, mode=mode, action=action)
            return f"Timer set for {spec} (Timer #{tid})."
        if name in ("SCHEDULE_AUTO", "AUTOMATE", "AUTORUN"):
            if not scheduler_engine:
                return "Scheduler not available."
            parts = [p.strip() for p in raw_arg.split("|", 1)]
            spec = parts[0] if parts else "every 1h"
            action = parts[1] if len(parts) > 1 else "SYSTEM: stats"
            aid = scheduler_engine.SCHEDULER.add_recurring_task(spec, action, action, mode=mode)
            return f"Scheduled recurring automation (ID #{aid}): '{action}' on schedule '{spec}'."
        if name in ("LIST_AUTOMATIONS", "AUTOMATIONS"):
            if not scheduler_engine:
                return "Scheduler not available."
            recs = scheduler_engine.SCHEDULER.list_recurring()
            if not recs:
                return "No recurring automations currently active."
            lines = [f"- [ID #{r['id']}] {r['spec']}: {r['label']} (next in {r['remaining_seconds']}s)" for r in recs]
            return "Active Recurring Automations:\n" + "\n".join(lines)
        if name in ("CANCEL_AUTOMATION", "STOP_AUTOMATION"):
            if not scheduler_engine:
                return "Scheduler not available."
            scheduler_engine.SCHEDULER.cancel_recurring(raw_arg)
            return f"Cancelled automation '{raw_arg}'."
        if name in ("SMART_HOME", "WEBHOOK", "IOT"):
            return skill_smart_home(raw_arg)
        if name in ("BRIEFING", "MORNING_BRIEFING"):
            if not scheduler_engine:
                return "Scheduler not available."
            return scheduler_engine.SCHEDULER.get_morning_briefing_summary()
        if name == "BROWSER_CLICK":
            if not nova_browser:
                return "Nova Browser module not available."
            return nova_browser.click_element(raw_arg)
        if name == "BROWSER_TYPE":
            if not nova_browser:
                return "Nova Browser module not available."
            parts = [p.strip() for p in raw_arg.split("|", 1)]
            if len(parts) > 1:
                sel = parts[0]
                txt = parts[1]
            else:
                sel = "input, textarea"
                txt = parts[0] if parts else ""
            return nova_browser.type_in_element(sel, txt)
        if name == "BROWSER_SCROLL":
            if not nova_browser:
                return "Nova Browser module not available."
            return nova_browser.scroll_page(raw_arg)
        if name in ("OPEN_URL", "OPEN_FILE", "VIEW_FILE"):
            return open_url(raw_arg)
        if name == "SEARCH":
            return open_url("https://www.google.com/search?q=" + urllib.parse.quote_plus(raw_arg))
        if name == "PLAY":
            clean_song = raw_arg.strip().lstrip("|").strip()
            if nova_browser:
                return nova_browser.youtube_action("play", clean_song)
            return open_url("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(clean_song))
        if name == "REMEMBER":
            if not raw_arg:
                return "Refused: empty fact."
            mem = get_memory()
            if raw_arg not in mem:
                mem.append(raw_arg)
                save_json(MEMORY_FILE, mem[-200:])
            return "ok"
        if name == "FORGET":
            if not raw_arg:
                return "Refused: empty keyword for forget."
            mem = [m for m in get_memory() if raw_arg.lower() not in m.lower()]
            save_json(MEMORY_FILE, mem)
            return "ok"
        if name == "BROWSER_OPEN":
            if not nova_browser:
                return "Nova Browser module not available."
            res = nova_browser.open_or_activate(raw_arg)
            return res.get("message", "ok")
        if name == "BROWSER_TABS":
            if not nova_browser:
                return "Nova Browser module not available."
            tabs = nova_browser.list_tabs()
            if not tabs:
                return "Nova Browser has no open tabs."
            lines = [f"{i+1}. [{t.get('id')[:6]}] {t.get('title', 'Untitled')} - {t.get('url')}" for i, t in enumerate(tabs)]
            return "Open tabs in Nova Browser:\n" + "\n".join(lines)
        if name == "BROWSER_ACTIVATE":
            if not nova_browser:
                return "Nova Browser module not available."
            tabs = nova_browser.list_tabs()
            target = nova_browser.find_tab_in_list(tabs, raw_arg)
            if target:
                nova_browser.activate_tab(target["id"])
                return f"Activated tab: {target.get('title')} ({target.get('url')})"
            return f"No open tab found matching '{raw_arg}'."
        if name == "BROWSER_CLOSE":
            if not nova_browser:
                return "Nova Browser module not available."
            tabs = nova_browser.list_tabs()
            target = nova_browser.find_tab_in_list(tabs, raw_arg)
            if target:
                nova_browser.close_tab(target["id"])
                return f"Closed tab: {target.get('title')}"
            return f"No open tab found matching '{raw_arg}'."
        if name == "BROWSER_RESEARCH":
            if not nova_browser:
                return "Nova Browser module not available."
            data = nova_browser.read_page_content(raw_arg)
            if "error" in data:
                return f"Research error: {data['error']}"
            return f"Page: {data.get('title')} ({data.get('url')})\n\nContent:\n{data.get('content')}"
        if name == "BROWSER_YOUTUBE":
            if not nova_browser:
                return "Nova Browser module not available."
            raw_clean = raw_arg.strip()
            if "|" in raw_clean:
                parts = [p.strip() for p in raw_clean.split("|", 1)]
                action = parts[0] or "play"
                query = parts[1] if len(parts) > 1 else ""
            else:
                parts = raw_clean.split(" ", 1)
                first_word = parts[0].lower() if parts else ""
                if first_word in ["play", "pause", "resume", "stop", "search", "open"]:
                    action = first_word
                    query = parts[1].strip() if len(parts) > 1 else ""
                else:
                    action = "play"
                    query = raw_clean
            return nova_browser.youtube_action(action, query)
        if name == "BROWSER_WHATSAPP":
            if not nova_browser:
                return "Nova Browser module not available."
            parts = [p.strip() for p in raw_arg.split("|", 1)]
            contact = parts[0] if parts else ""
            msg = parts[1] if len(parts) > 1 else ""
            return nova_browser.whatsapp_action("send", contact, msg)
        if name == "BROWSER_TELEGRAM":
            if not nova_browser:
                return "Nova Browser module not available."
            parts = [p.strip() for p in raw_arg.split("|", 1)]
            chat_name = parts[0] if parts else ""
            msg = parts[1] if len(parts) > 1 else ""
            return nova_browser.telegram_action("send", chat_name, msg)
    except Exception as e:
        return f"Skill failed: {e}"
    return "unknown skill"


# ----------------------------------------------------------------------------
# Agent activity tracker: lets the UI show whether the agent is working,
# what it is doing right now, and how long it has been running.
# ----------------------------------------------------------------------------
ACTIVITY = {"jobs": {}, "next": 0, "history": [], "total_runs": 0}


def act_start(source, text):
    with LOCK:
        ACTIVITY["next"] += 1
        jid = ACTIVITY["next"]
        now = time.time()
        ACTIVITY["jobs"][jid] = {
            "id": jid, "source": source, "task": mask_secrets((text or "")[:120]),
            "phase": "thinking", "detail": "Waiting for the AI model",
            "started": now, "phase_started": now, "steps": [],
        }
        return jid


def act_phase(jid, phase, detail=""):
    with LOCK:
        job = ACTIVITY["jobs"].get(jid)
        if job:
            job["phase"] = phase
            job["detail"] = mask_secrets((detail or "")[:160])
            job["phase_started"] = time.time()


def act_step(jid, name, arg, secs):
    with LOCK:
        job = ACTIVITY["jobs"].get(jid)
        if job:
            first = mask_secrets((arg or "").strip().split("\n")[0][:60])
            job["steps"].append({"skill": name, "arg": first, "secs": round(secs, 2)})
            del job["steps"][:-30]


def act_end(jid, ok=True, error=""):
    with LOCK:
        job = ACTIVITY["jobs"].pop(jid, None)
        if not job:
            return
        ACTIVITY["total_runs"] += 1
        ACTIVITY["history"].append({
            "id": jid, "source": job["source"], "task": mask_secrets(job["task"]),
            "secs": round(time.time() - job["started"], 2),
            "steps": len(job["steps"]), "ok": ok, "error": mask_secrets((error or "")[:160]),
            "finished": time.time(),
        })
        del ACTIVITY["history"][:-10]


def activity_state():
    now = time.time()
    with LOCK:
        jobs = [
            {
                "id": j["id"], "source": j["source"], "task": mask_secrets(j["task"]),
                "phase": j["phase"], "detail": mask_secrets(j["detail"]),
                "elapsed": round(now - j["started"], 1),
                "phase_elapsed": round(now - j["phase_started"], 1),
                "steps": list(j["steps"]),
            }
            for j in ACTIVITY["jobs"].values()
        ]
        return {
            "busy": bool(jobs), "jobs": jobs, "now": now,
            "total_runs": ACTIVITY["total_runs"],
            "last": ACTIVITY["history"][-1] if ACTIVITY["history"] else None,
            "history": list(ACTIVITY["history"]),
        }


TAINT_SOURCE_TOOLS = {
    "BRIEFING", "MORNING_BRIEFING",
    "BROWSER_RESEARCH", "BROWSER_OPEN", "BROWSER_TABS",
    "VISION", "SCREEN_ANALYZE",
    "READ_FILE", "SEARCH_NOTES",
    "ACTIVE_WINDOW", "GET_WINDOW",
    "LIST_FILES"
}

def execute_model_tags(tags, cfg, jid=None, mode="developer", source="pc", is_tainted=False, is_healing=False):
    """
    Unified function that executes model-emitted tags.
    Every tool call passes through check_tool_confirmation_required().
    Used by both normal turns and self-healing turns so gating and taint never diverge.
    """
    actions = []
    feedback_items = []
    pending_info = None

    for name, arg, _, _ in tags:
        clean_name = unicodedata.normalize("NFKC", (name or "")).strip().upper()
        if clean_name in TAINT_SOURCE_TOOLS:
            is_tainted = True

        needs_confirm, reason = check_tool_confirmation_required(cfg, clean_name, arg, is_tainted=is_tainted, source=source)
        if needs_confirm:
            action_id = secrets.token_hex(8)
            preview_str = arg or ""
            if len(preview_str) > 20000:
                more_chars = len(preview_str) - 20000
                preview_str = preview_str[:20000] + f"\n... [truncated, {more_chars} more characters]"

            with PENDING_LOCK:
                if len(PENDING_ACTIONS) >= 20:
                    oldest_id = next(iter(PENDING_ACTIONS))
                    PENDING_ACTIONS.pop(oldest_id, None)
                PENDING_ACTIONS[action_id] = {
                    "id": action_id,
                    "name": clean_name,
                    "arg": arg,
                    "mode": mode,
                    "source": source,
                    "expires_at": time.time() + 120,
                    "created_at": time.time(),
                    "reason": reason,
                    "is_tainted": is_tainted,
                    "preview": preview_str,
                }
            g_verdict = "NONE"
            if guardian_agent:
                try:
                    is_safe, g_reason = guardian_agent.review_command_safety(cfg, clean_name, arg)
                    g_verdict = "SAFE" if is_safe else "DANGEROUS"
                except Exception:
                    g_verdict = "DANGEROUS"

            prompt_text = f"[{g_verdict}] {reason}" if g_verdict != "NONE" else (reason or f"Confirm: {clean_name}?")
            pending_info = {
                "id": action_id,
                "action": clean_name,
                "preview": preview_str,
                "prompt": prompt_text,
                "guardian": g_verdict,
            }
            actions.append({"skill": clean_name, "arg": arg, "result": f"Awaiting confirmation: {prompt_text}"})
            if audit_logger:
                audit_logger.log_audit_event(
                    channel=source,
                    tool=clean_name,
                    preview=arg or "",
                    guardian_verdict=g_verdict,
                    status="AWAITING_CONFIRMATION",
                    cfg=cfg,
                )
            break

        act_phase(jid, "running", f"{'HEAL: ' if is_healing else ''}{clean_name}: {(arg or '').strip().splitlines()[0][:70] if (arg or '').strip() else ''}")
        _t0 = time.time()
        res = run_skill(cfg, clean_name, arg, source=source, mode=mode)
        act_step(jid, f"{'HEAL_' if is_healing else ''}{clean_name}", arg, time.time() - _t0)
        actions.append({"skill": clean_name, "arg": arg, "result": res})
        if audit_logger:
            audit_logger.log_audit_event(
                channel=source,
                tool=clean_name,
                preview=arg or "",
                guardian_verdict="NONE",
                status="EXECUTED",
                cfg=cfg,
            )
        if res and any(err_pat in res for err_pat in ("STDERR:", "Traceback (most recent call last)", "Exit code:", "Error:", "failed:")):
            is_tainted = True
        if clean_name in ("RUN_CODE", "READ_FILE", "CMD", "POWERSHELL", "GIT", "LIST_FILES", "EDIT_FILE", "WRITE_FILE") or (clean_name == "SYSTEM" and "stats" in (arg or "").lower()):
            feedback_items.append(f"[{clean_name} Output]:\n{res}")

    return {
        "actions": actions,
        "feedback_items": feedback_items,
        "pending_info": pending_info,
        "is_tainted": is_tainted,
    }


def chat(user_text, source="pc", mode="developer", is_automation=False, automation_token=None):
    if is_automation or source == "scheduler":
        source = "scheduler"
        is_automation = True
    mode = "cyber" if mode == "cyber" else "developer"
    jid = act_start(source, user_text)
    try:
        result = _chat_inner(user_text, source, jid, mode=mode, is_automation=is_automation)
        act_end(jid, ok=True)
        return result
    except Exception as e:
        act_end(jid, ok=False, error=f"{type(e).__name__}: {e}")
        raise


def _chat_inner(user_text, source, jid, mode="developer", is_automation=False):
    mode = "cyber" if mode == "cyber" else "developer"
    cfg = get_config()
    chars = get_characters()
    char = next((c for c in chars if c["id"] == cfg["character"]), chars[0])
    user_msg = {"role": "user", "content": user_text}
    hist = HISTORIES.get(mode, HISTORIES["developer"])

    user_lower = (user_text or "").strip().lower()
    APPROVE_WORDS = {"yes", "confirm", "proceed", "allow", "approve", "haan", "thik ache", "y", "sure", "do it"}
    DENY_WORDS = {"no", "cancel", "deny", "stop", "dont", "don't", "na", "cancel it", "reject"}

    user_words = user_lower.split()
    is_short_utterance = 1 <= len(user_words) <= 3
    is_approve_word = user_lower in APPROVE_WORDS and is_short_utterance
    is_deny_word = user_lower in DENY_WORDS and is_short_utterance

    now_t = time.time()
    with PENDING_LOCK:
        expired = [k for k, v in PENDING_ACTIONS.items() if v.get("expires_at", 0) < now_t]
        for k in expired:
            PENDING_ACTIONS.pop(k, None)

        pending_for_mode = [p for p in PENDING_ACTIONS.values() if p.get("mode") == mode]

        if (is_approve_word or is_deny_word) and len(pending_for_mode) == 1:
            pending = pending_for_mode[0]
            # If tainted, scheduler, or mobile, conversational approval is strictly blocked; require desktop UI Allow button
            if pending.get("is_tainted") or pending.get("source") in ("phone", "scheduler"):
                reply = "This action requires your confirmation via the desktop Allow button."
                with LOCK:
                    hist.append(user_msg)
                    hist.append({"role": "assistant", "content": reply})
                if source != "pc":
                    add_event(source=source, text=user_text, reply=reply, actions=[])
                return {"reply": reply, "actions": []}

            # (b) source check
            same_source = (pending.get("source") == source)
            # (c) created within 60s
            under_60s = (now_t - pending.get("created_at", now_t) <= 60)
            # (a) last assistant message was confirmation prompt
            last_is_prompt = False
            with LOCK:
                if hist:
                    for msg in reversed(hist):
                        if msg.get("role") == "assistant":
                            content = msg.get("content", "")
                            if "[Action Requires Confirmation:" in content or pending.get("name") in content:
                                last_is_prompt = True
                            break

            if same_source and under_60s and last_is_prompt:

                if is_approve_word:
                    PENDING_ACTIONS.pop(pending["id"], None)
                    if pending.get("name") == "RUN_CODE":
                        with RUN_CODE_TRUST_LOCK:
                            LAST_RUN_CODE_APPROVED_TIME = time.time()
                    res = run_skill(cfg, pending["name"], pending["arg"], source=source, is_confirmed=True, mode=pending.get("mode", mode))
                    reply = f"Approved and executed {pending['name']}.\n{res}"
                    with LOCK:
                        hist.append(user_msg)
                        hist.append({"role": "assistant", "content": reply})
                    if source != "pc":
                        add_event(source=source, text=user_text, reply=reply, actions=[{"skill": pending["name"], "arg": pending["arg"], "result": res}])
                    return {"reply": reply, "actions": [{"skill": pending["name"], "arg": pending["arg"], "result": res}]}
                elif is_deny_word:
                    PENDING_ACTIONS.pop(pending["id"], None)
                    reply = f"Action {pending['name']} was cancelled."
                    with LOCK:
                        hist.append(user_msg)
                        hist.append({"role": "assistant", "content": reply})
                    if source != "pc":
                        add_event(source=source, text=user_text, reply=reply, actions=[])
                    return {"reply": reply, "actions": []}

    with LOCK:
        hist.append(user_msg)
        del hist[:-20]
        while hist and hist[0]["role"] != "user":
            hist.pop(0)
        # Ensure alternating roles if previous retries left consecutive user messages
        sanitized = []
        for msg in hist:
            if sanitized and sanitized[-1]["role"] == msg["role"]:
                if msg["role"] == "user":
                    sanitized[-1] = {"role": "user", "content": sanitized[-1]["content"] + "\n" + msg["content"]}
                else:
                    sanitized[-1] = msg
            else:
                sanitized.append(dict(msg))
        messages_to_send = list(sanitized)

    sys_prompt = build_system(cfg, char, mode=mode)
    if skills_engine:
        try:
            skill_prompt = skills_engine.build_skill_prompt(mode, user_text)
            if skill_prompt:
                sys_prompt += skill_prompt
        except Exception:
            pass
    try:
        act_phase(jid, "thinking", "Waiting for the AI model")
        raw = call_llm(cfg, sys_prompt, messages_to_send)
    except Exception:
        with LOCK:
            # Roll back last user message on failure so history is not poisoned
            if hist and hist[-1] == user_msg:
                hist.pop()
        raise

    parsed_tags = extract_tags(raw)
    is_tainted = (source != "pc") or is_automation or (source == "scheduler")

    tag_result = execute_model_tags(parsed_tags, cfg, jid=jid, mode=mode, source=source, is_tainted=is_tainted, is_healing=False)
    actions = list(tag_result["actions"])
    feedback_items = list(tag_result["feedback_items"])
    is_tainted = tag_result["is_tainted"] or is_tainted
    pending_info = tag_result["pending_info"]

    # Autonomous Self-Healing Loop for coding & command errors
    healing_attempts = 0
    conversation_chain = list(messages_to_send)
    while healing_attempts < 2 and not pending_info:
        has_error = any(
            ("Exit code: 0" not in item and "Exit code 0" not in item and "Exit code" in item) or
            ("STDERR:" in item and "warning" not in item.lower() and len(item.strip()) > 15) or
            ("Traceback (most recent call last)" in item)
            for item in feedback_items
        )
        if not has_error:
            break
        healing_attempts += 1
        act_phase(jid, "healing", f"Self-healing code attempt {healing_attempts}/2")
        heal_prompt = (
            "The execution encountered an error:\n"
            + "\n".join(feedback_items)
            + "\nPlease analyze the cause of the failure. Use [[EDIT_FILE: path | search | replace]] or [[WRITE_FILE: path | content]] to fix the code, and re-test with [[RUN_CODE: language | code]]."
        )
        try:
            conversation_chain.append({"role": "assistant", "content": raw})
            conversation_chain.append({"role": "user", "content": heal_prompt})
            heal_raw = call_llm(cfg, sys_prompt, conversation_chain)
            raw = heal_raw
            heal_tags = extract_tags(heal_raw)
            heal_result = execute_model_tags(heal_tags, cfg, jid=jid, mode=mode, source=source, is_tainted=is_tainted, is_healing=True)
            actions.extend(heal_result["actions"])
            is_tainted = heal_result["is_tainted"] or is_tainted
            if heal_result["pending_info"]:
                pending_info = heal_result["pending_info"]
                break
            feedback_items = list(heal_result["feedback_items"])
        except Exception:
            break

    final_reply = strip_tags(raw)
    if feedback_items and len(feedback_items) <= 3:
        try:
            obs_prompt = (
                "Here is the execution output of the requested action:\n"
                + "\n".join(feedback_items)
                + "\nIn 1-2 natural spoken sentences in the user's language, summarize the outcome or result clearly. Do not use tags or markdown."
            )
            follow_up_messages = conversation_chain + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": obs_prompt}
            ]
            act_phase(jid, "summarizing", "Writing the result summary")
            obs_reply = call_llm(cfg, sys_prompt, follow_up_messages)
            cleaned_obs = strip_tags(obs_reply)
            if cleaned_obs:
                final_reply = cleaned_obs
        except Exception:
            pass

    reply = final_reply or "Done."
    if pending_info and not any(w in reply.lower() for w in ("confirm", "approve", "permission")):
        reply = (reply + f"\n\n[Action Requires Confirmation: {pending_info['prompt']}]").strip()

    with LOCK:
        hist.append({"role": "assistant", "content": reply})
    if source != "pc":
        # lets the PC screen show (and speak) what was asked from the phone
        add_event(source=source, text=user_text, reply=reply, actions=actions)
    res_dict = {"reply": reply, "actions": actions}
    if pending_info:
        res_dict["pending"] = pending_info
    return res_dict


# ----------------------------------------------------------------------------
# Mobile remote: phone -> PC. Separate opt-in listener, protected by a secret token.
# The main UI server always stays on 127.0.0.1; only the small remote surface
# (phone page + 2 token-checked endpoints) is ever reachable from your Wi-Fi.
# ----------------------------------------------------------------------------
EVENTS = []
EVENT_ID = [0]
REMOTE = {"srv": None, "error": "", "last_seen": 0.0}
FAILS = {}  # client ip -> [wrong attempts, window start]


def add_event(**kw):
    with LOCK:
        EVENT_ID[0] += 1
        masked_kw = {k: mask_telemetry(v) for k, v in kw.items()}
        ev = {"id": EVENT_ID[0], "t": time.time(), **masked_kw}
        EVENTS.append(ev)
        del EVENTS[:-50]
        return ev


def lan_ips():
    """Best guess at this PC's address on your Wi-Fi/LAN (most likely first)."""
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # no packet is actually sent
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    ips = [i for i in ips if not i.startswith(("127.", "169.254."))]

    def private(i):
        return i.startswith(("192.168.", "10.")) or re.match(r"^172\.(1[6-9]|2\d|3[01])\.", i)

    return sorted(ips, key=lambda i: 0 if private(i) else 1)


def remote_state(reveal=True):
    cfg = get_config()
    port = int(cfg.get("remote_port", 8766))
    token = cfg.get("remote_token", "")
    ago = (time.time() - REMOTE["last_seen"]) if REMOTE["last_seen"] else None
    cert = cfg.get("remote_cert")
    key = cfg.get("remote_key")
    proto = "https" if (cert and key and Path(cert).is_file() and Path(key).is_file()) else "http"
    return {
        "enabled": bool(cfg.get("remote_enabled")),
        "active": REMOTE["srv"] is not None,
        "error": REMOTE["error"],
        "port": port,
        "urls": [f"{proto}://{ip}:{port}/?t={token}" for ip in lan_ips()] if (reveal and token) else [],
        "seconds_since_phone": ago,
    }


def start_remote():
    cfg = get_config()
    port = int(cfg.get("remote_port", 8766))
    REMOTE["error"] = ""
    try:
        srv = SilentThreadingHTTPServer(("0.0.0.0", port), RemoteHandler)
        cert = cfg.get("remote_cert")
        key = cfg.get("remote_key")
        if cert and key and Path(cert).is_file() and Path(key).is_file():
            import ssl
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))
            srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    except OSError as e:
        REMOTE["error"] = f"Could not open port {port} ({e}). Close whatever uses it, or change remote_port in data/config.json."
        return
    except Exception as e:
        REMOTE["error"] = f"Could not initialize remote server: {e}"
        return
    REMOTE["srv"] = srv
    threading.Thread(target=srv.serve_forever, daemon=True).start()


def stop_remote():
    srv = REMOTE.get("srv")
    if srv:
        REMOTE["srv"] = None
        srv.shutdown()
        srv.server_close()


def set_remote(enabled):
    cfg = load_json(CONFIG_FILE, {})
    cfg["remote_enabled"] = bool(enabled)
    if enabled and not cfg.get("remote_token"):
        cfg["remote_token"] = secrets.token_urlsafe(32)
    save_config(cfg)
    stop_remote()
    if enabled:
        start_remote()


def regenerate_token():
    cfg = load_json(CONFIG_FILE, {})
    cfg["remote_token"] = secrets.token_urlsafe(32)  # old QR codes stop working at once
    save_config(cfg)
    FAILS.clear()


# ----------------------------------------------------------------------------
# News (public RSS)
# ----------------------------------------------------------------------------
NEWS_CACHE = {"t": 0, "items": []}


def get_news():
    import time

    if time.time() - NEWS_CACHE["t"] < 600 and NEWS_CACHE["items"]:
        return NEWS_CACHE["items"]
    items = []
    try:
        req = urllib.request.Request(
            "https://feeds.bbci.co.uk/news/world/rss.xml", headers={"User-Agent": "NovaAI/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            root = ET.fromstring(r.read())
        for it in root.iter("item"):
            items.append({"title": it.findtext("title", ""), "link": it.findtext("link", "")})
            if len(items) >= 12:
                break
    except Exception:
        pass
    if items:
        NEWS_CACHE.update(t=time.time(), items=items)
    return items


# ----------------------------------------------------------------------------
# HTTP server
# ----------------------------------------------------------------------------
class SilentThreadingHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that suppresses noisy client disconnection tracebacks."""
    def get_request(self):
        sock, addr = super().get_request()
        try:
            sock.settimeout(30.0)
        except Exception:
            pass
        return sock, addr

    def handle_error(self, request, client_address):
        ex = sys.exc_info()[1]
        if isinstance(ex, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, TimeoutError, socket.timeout)):
            return
        super().handle_error(request, client_address)


class BaseHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 30

    def log_message(self, *a):
        pass

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, TimeoutError, socket.timeout):
            pass

    def _send(self, code, body, ctype="application/json"):
        try:
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            elif isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            self.close_connection = True

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
            if n > 10 * 1024 * 1024:
                self._send(413, {"error": "Payload Too Large: exceeds 10MB limit"})
                return None
            raw = self.rfile.read(n) or b"{}"
            data = json.loads(raw)
            def _check_depth(obj, depth=0):
                if depth > 50:
                    raise ValueError("JSON depth limit exceeded")
                if isinstance(obj, dict):
                    for v in obj.values():
                        _check_depth(v, depth + 1)
                elif isinstance(obj, list):
                    for v in obj:
                        _check_depth(v, depth + 1)
            _check_depth(data)
            return data
        except ValueError as e:
            if "depth" in str(e).lower():
                self._send(400, {"error": "JSON depth limit exceeded"})
                return None
            return {}
        except Exception:
            return {}

    DEFAULT_PORT = 8765

    def _local_only(self):
        return check_local_request(self, expected_port=getattr(self, "DEFAULT_PORT", 8765))


def check_local_request(req, expected_port=8765):
    # Block other websites from talking to the local API (CSRF / DNS-rebinding)
    raw_host = (req.headers.get("Host") or "").strip()
    if not raw_host:
        return False

    if ":" not in raw_host:
        return False

    if raw_host.startswith("["):
        end_bracket = raw_host.find("]")
        if end_bracket == -1:
            return False
        host = raw_host[1:end_bracket]
        port_part = raw_host[end_bracket + 1 :]
        if not port_part.startswith(":"):
            return False
        port_str = port_part[1:]
    else:
        parts = raw_host.split(":")
        if len(parts) != 2:
            return False
        host, port_str = parts[0], parts[1]

    if host.lower() not in ("127.0.0.1", "localhost"):
        return False

    if hasattr(req, "server") and hasattr(req.server, "server_address") and isinstance(req.server.server_address, tuple) and len(req.server.server_address) > 1 and isinstance(req.server.server_address[1], int):
        expected_port = req.server.server_address[1]

    try:
        port = int(port_str)
    except ValueError:
        return False

    if port != expected_port:
        return False

    sec_fetch_site = req.headers.get("Sec-Fetch-Site")
    if sec_fetch_site and sec_fetch_site.strip().lower() == "cross-site":
        return False

    origin = req.headers.get("Origin")
    if origin:
        parsed_origin = urllib.parse.urlparse(origin)
        if parsed_origin.hostname not in ("127.0.0.1", "localhost"):
            return False
        if parsed_origin.port is not None and parsed_origin.port != expected_port:
            return False

    referer = req.headers.get("Referer")
    if referer and not origin:
        parsed_ref = urllib.parse.urlparse(referer)
        if parsed_ref.hostname not in ("127.0.0.1", "localhost"):
            return False
        if parsed_ref.port is not None and parsed_ref.port != expected_port:
            return False

    # On state-changing routes (POST/DELETE), require Origin, Referer, or Sec-Fetch-Site if present or local command
    cmd = getattr(req, "command", "") or (req.requestline.split()[0] if hasattr(req, "requestline") and req.requestline else "")
    if cmd in ("POST", "DELETE"):
        if not origin and not referer and not sec_fetch_site:
            # Disallow blind ambient POSTs with no origin context
            return False

    return True


class Handler(BaseHandler):
    DEFAULT_PORT = 8765

    def _local_only(self):
        return check_local_request(self, expected_port=getattr(self, "DEFAULT_PORT", 8765))

    def do_GET(self):
        if not self._local_only():
            return self._send(403, {"error": "forbidden"})
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/state":
            cfg = get_config()
            safe = {k: v for k, v in cfg.items() if k in SAFE_STATE_FIELDS}
            safe["has_key"] = bool(cfg.get("api_key"))
            safe["api_key_set"] = bool(cfg.get("api_key"))
            for sec in sorted(SECRET_FIELDS):
                safe[f"{sec}_set"] = bool(cfg.get(sec))
            return self._send(
                200,
                {
                    "config": safe,
                    "characters": get_characters(),
                    "memory": get_memory(),
                    "presets": PRESETS,
                    "os": OS,
                    "workspace": str(WORKSPACE),
                },
            )
        if path == "/api/news":
            return self._send(200, get_news())
        if path == "/api/remote":
            return self._send(200, remote_state())
        if path == "/api/activity":
            return self._send(200, activity_state())
        if path == "/api/browser/status":
            if not nova_browser:
                return self._send(200, {"available": False, "running": False, "tabs": []})
            running = nova_browser.is_cdp_available(timeout=0.3)
            tabs = nova_browser.list_tabs() if running else []
            return self._send(200, {
                "available": True,
                "running": running,
                "profile": str(nova_browser.get_profile_dir()),
                "tabs": tabs
            })
        if path == "/api/events":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try:
                after = int((q.get("after") or ["0"])[0])
            except ValueError:
                after = 0
            with LOCK:
                return self._send(200, {"last": EVENT_ID[0], "events": [e for e in EVENTS if e["id"] > after]})
        if path == "/api/notifications":
            items = scheduler_engine.SCHEDULER.get_pending_notifications() if scheduler_engine else []
            return self._send(200, {"notifications": items})
        if path == "/api/timers":
            timers = scheduler_engine.SCHEDULER.list_timers() if scheduler_engine else []
            return self._send(200, {"timers": timers})
        if path == "/api/automations":
            recs = scheduler_engine.SCHEDULER.list_recurring() if scheduler_engine else []
            return self._send(200, {"automations": recs})
        if path == "/api/skills":
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            mode = qs.get("mode", ["developer"])[0]
            if not skills_engine:
                return self._send(200, {"mode": mode, "skills": []})
            skills = skills_engine.load_skills(mode)
            out = [{"name": s.name, "description": s.description, "triggers": s.triggers} for s in skills]
            return self._send(200, {"mode": mode, "skills": out})
        if path == "/api/notes":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("q", [""])[0]
            if not memory_engine:
                return self._send(200, {"notes": []})
            if q:
                notes = memory_engine.search_notes(q)
            else:
                notes = memory_engine.list_notes()
            return self._send(200, {"notes": notes})
        if path == "/api/audit":
            if not audit_logger:
                return self._send(200, {"events": []})
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try:
                limit = int((qs.get("limit") or ["50"])[0])
            except ValueError:
                limit = 50
            return self._send(200, {"events": audit_logger.get_recent_audit_events(limit=limit)})
        if path in ("/api/metrics/usage", "/api/usage"):
            if not usage_tracker:
                return self._send(200, {"summary": {}, "budget": {}})
            cfg = get_config()
            cap = cfg.get("monthly_budget_usd")
            cap_float = float(cap) if cap else None
            return self._send(200, {
                "summary": usage_tracker.get_usage_summary(),
                "budget": usage_tracker.check_budget_status(cap_float),
            })
        if path in ("/api/health", "/api/diagnostics"):
            if not diagnostics:
                return self._send(200, {"overall_status": "healthy", "checks": []})
            cfg = get_config()
            return self._send(200, diagnostics.run_diagnostics(cfg))
        if path == "/api/github":
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            repo = (qs.get("repo") or [""])[0].strip()
            action = (qs.get("action") or ["info"])[0].strip()
            file_path = (qs.get("path") or [""])[0].strip()
            if not repo:
                return self._send(400, {"ok": False, "error": "Missing 'repo' parameter"})
            action_arg = f"file:{file_path}" if (action == "file" and file_path) else action
            cfg = get_config()
            gh = integrations.get_integration("github") if integrations else None
            if not gh:
                return self._send(500, {"ok": False, "error": "GitHub connector not available"})
            try:
                result_str = gh.run(cfg, f"{repo} | {action_arg}")
                return self._send(200, {"ok": True, "repo": repo, "action": action_arg, "result": result_str})
            except Exception as e:
                return self._send(500, {"ok": False, "error": f"GitHub connector error: {str(e)}"})
        if path == "/api/chat/stream":
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            msg = (qs.get("message") or qs.get("text") or [""])[0].strip()
            mode = (qs.get("mode") or ["developer"])[0].strip()
            source = (qs.get("source") or ["pc"])[0].strip()
            if not msg:
                return self._send(400, {"error": "empty message"})
            if len(msg) > 30000:
                return self._send(413, {"error": "Message exceeds maximum allowed length of 30,000 characters."})
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            res = chat(msg, mode=mode, source=source)
            reply = res.get("reply", "")
            actions = res.get("actions", [])

            chunk_size = 64
            for i in range(0, max(1, len(reply)), chunk_size):
                chunk = reply[i:i + chunk_size]
                if chunk:
                    ev = json.dumps({"type": "chunk", "text": chunk})
                    self.wfile.write(f"data: {ev}\n\n".encode("utf-8"))
                    self.wfile.flush()

            for act in actions:
                ev = json.dumps({"type": "action", **act})
                self.wfile.write(f"data: {ev}\n\n".encode("utf-8"))
                self.wfile.flush()

            done_ev = json.dumps({"type": "done", "reply": reply, "actions": actions})
            self.wfile.write(f"data: {done_ev}\n\n".encode("utf-8"))
            self.wfile.flush()
            return
        # static
        if path == "/favicon.ico":
            fav = (WEB / "favicon.ico").resolve()
            if fav.is_file():
                return self._send(200, fav.read_bytes(), "image/x-icon")
            svg_icon = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="45" fill="#02060d" stroke="#37d6ff" stroke-width="6"/><circle cx="50" cy="50" r="20" fill="#37d6ff"/></svg>"""
            return self._send(200, svg_icon, "image/svg+xml")
        if path == "/":
            path = "/index.html"
        f = (WEB / path.lstrip("/")).resolve()
        if WEB.resolve() not in f.parents or not f.is_file():
            return self._send(404, {"error": "not found"})
        ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        self._send(200, f.read_bytes(), ctype)

    def do_DELETE(self):
        if not self._local_only():
            return self._send(403, {"error": "forbidden"})
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/notes":
            if not memory_engine:
                return self._send(500, {"error": "memory_engine not available"})
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            del_id = qs.get("id", [""])[0] or qs.get("title", [""])[0]
            if not del_id:
                body = self._body()
                if body is None:
                    return
                del_id = body.get("id") or body.get("title", "")
            if not del_id:
                return self._send(400, {"error": "Missing note id or title to delete"})
            ok = memory_engine.delete_note(del_id)
            return self._send(200, {"ok": ok})
        if path == "/api/timers":
            if not scheduler_engine:
                return self._send(500, {"error": "scheduler_engine not available"})
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            del_id = qs.get("id", [""])[0]
            if not del_id:
                body = self._body()
                if body is None:
                    return
                del_id = body.get("id")
            if del_id is None or del_id == "":
                return self._send(400, {"error": "Missing timer id to delete"})
            ok = scheduler_engine.SCHEDULER.cancel_timer(del_id)
            if not ok:
                return self._send(404, {"error": "Timer not found"})
            return self._send(200, {"ok": True})
        if path == "/api/automations":
            if not scheduler_engine:
                return self._send(500, {"error": "scheduler_engine not available"})
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            del_id = qs.get("id", [""])[0]
            if not del_id:
                body = self._body()
                if body is None:
                    return
                del_id = body.get("id")
            if del_id is None or del_id == "":
                return self._send(400, {"error": "Missing automation id to delete"})
            ok = scheduler_engine.SCHEDULER.cancel_recurring(del_id)
            if not ok:
                return self._send(404, {"error": "Automation not found"})
            return self._send(200, {"ok": True})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._local_only():
            return self._send(403, {"error": "forbidden"})
        path = urllib.parse.urlparse(self.path).path
        body = self._body()
        if body is None:
            return
        try:
            if path == "/api/confirm":
                action_id = body.get("id")
                approve = bool(body.get("approve"))
                with PENDING_LOCK:
                    pending = PENDING_ACTIONS.pop(action_id, None)
                if not pending:
                    return self._send(404, {"ok": False, "error": "Pending action not found or expired"})
                if pending.get("expires_at", 0) < time.time():
                    return self._send(400, {"ok": False, "error": "Pending action expired"})
                cfg = get_config()
                if not approve:
                    if audit_logger:
                        audit_logger.log_audit_event(
                            channel=pending.get("source", "pc"),
                            tool=pending["name"],
                            preview=pending.get("arg", ""),
                            guardian_verdict="NONE",
                            status="DENIED",
                            cfg=cfg,
                        )
                    return self._send(200, {"ok": True, "approved": False, "action": pending["name"]})
                if pending.get("name") == "RUN_CODE":
                    with RUN_CODE_TRUST_LOCK:
                        LAST_RUN_CODE_APPROVED_TIME = time.time()
                res = run_skill(cfg, pending["name"], pending["arg"], source=pending.get("source", "pc"), is_confirmed=True, mode=pending.get("mode", "developer"))
                if audit_logger:
                    audit_logger.log_audit_event(
                        channel=pending.get("source", "pc"),
                        tool=pending["name"],
                        preview=pending.get("arg", ""),
                        guardian_verdict="NONE",
                        status="APPROVED",
                        cfg=cfg,
                    )
                return self._send(200, {"ok": True, "approved": True, "action": pending["name"], "result": res})
            if path == "/api/notifications/clear":
                if scheduler_engine:
                    scheduler_engine.SCHEDULER.clear_notifications()
                return self._send(200, {"ok": True})
            if path == "/api/github":
                repo = (body.get("repo") or "").strip()
                action = (body.get("action") or "info").strip()
                file_path = (body.get("path") or "").strip()
                if not repo:
                    return self._send(400, {"ok": False, "error": "Missing 'repo' parameter"})
                action_arg = f"file:{file_path}" if (action == "file" and file_path) else action
                cfg = get_config()
                gh = integrations.get_integration("github") if integrations else None
                if not gh:
                    return self._send(500, {"ok": False, "error": "GitHub connector not available"})
                try:
                    result_str = gh.run(cfg, f"{repo} | {action_arg}")
                    return self._send(200, {"ok": True, "repo": repo, "action": action_arg, "result": result_str})
                except Exception as e:
                    return self._send(500, {"ok": False, "error": f"GitHub connector error: {str(e)}"})
            if path == "/api/exit":
                self._send(200, {"ok": True})
                threading.Thread(target=lambda: (time.sleep(0.5), os._exit(0)), daemon=True).start()
                return
            if path == "/api/chat":
                text = (body.get("message") or "").strip()
                if not text:
                    return self._send(400, {"error": "empty"})
                if len(text) > 30000:
                    return self._send(413, {"error": "Message exceeds maximum allowed length of 30,000 characters."})
                mode = body.get("mode") or "developer"
                source = body.get("source") or "pc"
                is_auto = bool(body.get("is_automation"))
                tok = body.get("automation_token")
                if is_auto or source == "scheduler":
                    if scheduler_engine and hasattr(scheduler_engine.SCHEDULER, "validate_and_consume_automation_token"):
                        if not scheduler_engine.SCHEDULER.validate_and_consume_automation_token(tok):
                            return self._send(403, {"error": "Invalid or expired automation token."})
                    source = "scheduler"
                    is_auto = True
                return self._send(200, chat(text, mode=mode, source=source, is_automation=is_auto))
            if path == "/api/chat/stream":
                msg = (body.get("message") or body.get("text") or "").strip()
                mode = body.get("mode") or "developer"
                source = body.get("source") or "pc"
                if not msg:
                    return self._send(400, {"error": "empty message"})
                if len(msg) > 30000:
                    return self._send(413, {"error": "Message exceeds maximum allowed length of 30,000 characters."})
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                res = chat(msg, mode=mode, source=source)
                reply = res.get("reply", "")
                actions = res.get("actions", [])

                chunk_size = 64
                for i in range(0, max(1, len(reply)), chunk_size):
                    chunk = reply[i:i + chunk_size]
                    if chunk:
                        ev = json.dumps({"type": "chunk", "text": chunk})
                        self.wfile.write(f"data: {ev}\n\n".encode("utf-8"))
                        self.wfile.flush()

                for act in actions:
                    ev = json.dumps({"type": "action", **act})
                    self.wfile.write(f"data: {ev}\n\n".encode("utf-8"))
                    self.wfile.flush()

                done_ev = json.dumps({"type": "done", "reply": reply, "actions": actions})
                self.wfile.write(f"data: {done_ev}\n\n".encode("utf-8"))
                self.wfile.flush()
                return
            if path == "/api/config":
                VALID_CONFIG_KEYS = {
                    "provider", "model", "base_url", "api_key", "clear_key",
                    "character", "user_name", "language",
                    "voice_rate", "voice_pitch", "voice_volume",
                    "wake_word_enabled", "barge_in_enabled",
                    "port", "remote_enabled", "remote_port",
                    "remote_cert", "remote_allow_dangerous",
                    "allow_outside_workspace", "confirm_destructive",
                    "process_timeout", "max_tokens", "apps",
                    "run_code_trusted_minutes", "encrypt_keys",
                    "confirm_token", "source", "smart_home_hosts", "llm_timeout",
                    "debug_llm", "llm_reasoning_effort", "fallback_providers",
                    "telegram_enabled", "telegram_allowed_chat_ids"
                } | SECRET_FIELDS | {f"clear_{sec}" for sec in SECRET_FIELDS}
                # Reject unknown keys
                for k in body:
                    if k not in VALID_CONFIG_KEYS:
                        return self._send(400, {"ok": False, "error": f"Unknown configuration key: {k}"})

                # Validate numeric types before confirmation gating
                if "run_code_trusted_minutes" in body:
                    try:
                        int(body["run_code_trusted_minutes"])
                    except (ValueError, TypeError):
                        return self._send(400, {"ok": False, "error": "run_code_trusted_minutes must be an integer >= 0"})
                if "port" in body:
                    try:
                        int(body["port"])
                    except (ValueError, TypeError):
                        return self._send(400, {"ok": False, "error": "port must be an integer"})
                if "remote_port" in body:
                    try:
                        int(body["remote_port"])
                    except (ValueError, TypeError):
                        return self._send(400, {"ok": False, "error": "remote_port must be an integer"})
                if "llm_timeout" in body:
                    try:
                        int(body["llm_timeout"])
                    except (ValueError, TypeError):
                        return self._send(400, {"ok": False, "error": "llm_timeout must be an integer"})

                SENSITIVE_CONFIG_KEYS = {
                    "confirm_destructive",
                    "allow_outside_workspace",
                    "remote_allow_dangerous",
                    "run_code_trusted_minutes",
                    "remote_cert",
                    "remote_key",
                    "encrypt_keys",
                }
                keys_to_confirm = [k for k in body if k in SENSITIVE_CONFIG_KEYS]
                if keys_to_confirm:
                    if body.get("source") == "phone":
                        return self._send(403, {"ok": False, "error": "Modifying security settings is not allowed from mobile remote."})
                    confirm_token = body.get("confirm_token")
                    now_t = time.time()
                    token_valid = False
                    with CONFIG_CONFIRM_LOCK:
                        if confirm_token and confirm_token in CONFIG_CONFIRM_TOKENS:
                            if CONFIG_CONFIRM_TOKENS[confirm_token] > now_t:
                                token_valid = True
                            CONFIG_CONFIRM_TOKENS.pop(confirm_token, None)
                    if not token_valid:
                        new_tok = secrets.token_hex(16)
                        with CONFIG_CONFIRM_LOCK:
                            CONFIG_CONFIRM_TOKENS[new_tok] = now_t + 120
                        return self._send(200, {
                            "need_confirm": True,
                            "token": new_tok,
                            "keys": keys_to_confirm,
                            "prompt": f"Modifying security settings ({', '.join(keys_to_confirm)}) requires confirmation."
                        })

                cfg = load_json(CONFIG_FILE, {})
                for k in ("provider", "model", "base_url", "user_name", "language", "character", "llm_reasoning_effort"):
                    if k in body:
                        cfg[k] = str(body[k])
                for k in ("wake_word_enabled", "barge_in_enabled", "allow_outside_workspace", "confirm_destructive", "remote_enabled", "remote_allow_dangerous", "encrypt_keys", "debug_llm", "telegram_enabled"):
                    if k in body:
                        cfg[k] = bool(body[k])
                if "telegram_allowed_chat_ids" in body:
                    t_ids = body["telegram_allowed_chat_ids"]
                    if isinstance(t_ids, list):
                        cfg["telegram_allowed_chat_ids"] = [str(x) for x in t_ids]
                if "fallback_providers" in body:
                    fps = body["fallback_providers"]
                    if isinstance(fps, list):
                        cfg["fallback_providers"] = [str(x) for x in fps if isinstance(x, str)]
                
                # Numeric validations with strict bounds
                if "run_code_trusted_minutes" in body:
                    try:
                        v = int(body["run_code_trusted_minutes"])
                        cfg["run_code_trusted_minutes"] = max(0, min(1440, v))
                    except (ValueError, TypeError):
                        return self._send(400, {"ok": False, "error": "run_code_trusted_minutes must be an integer >= 0"})
                
                # Numeric validations with strict bounds
                if "voice_rate" in body:
                    try:
                        v = float(body["voice_rate"])
                        cfg["voice_rate"] = max(0.5, min(2.0, v))
                    except (ValueError, TypeError):
                        return self._send(400, {"ok": False, "error": "voice_rate must be a number between 0.5 and 2.0"})

                if "voice_pitch" in body:
                    try:
                        v = float(body["voice_pitch"])
                        cfg["voice_pitch"] = max(0.0, min(2.0, v))
                    except (ValueError, TypeError):
                        return self._send(400, {"ok": False, "error": "voice_pitch must be a number between 0.0 and 2.0"})

                if "voice_volume" in body:
                    try:
                        v = float(body["voice_volume"])
                        cfg["voice_volume"] = max(0.0, min(1.0, v))
                    except (ValueError, TypeError):
                        return self._send(400, {"ok": False, "error": "voice_volume must be a number between 0.0 and 1.0"})

                if "process_timeout" in body:
                    try:
                        v = int(body["process_timeout"])
                        cfg["process_timeout"] = max(1, min(300, v))
                    except (ValueError, TypeError):
                        return self._send(400, {"ok": False, "error": "process_timeout must be an integer between 1 and 300"})

                if "llm_timeout" in body:
                    try:
                        v = int(body["llm_timeout"])
                        cfg["llm_timeout"] = max(5, min(120, v))
                    except (ValueError, TypeError):
                        return self._send(400, {"ok": False, "error": "llm_timeout must be an integer between 5 and 120"})

                if "max_tokens" in body:
                    try:
                        val = int(body["max_tokens"])
                        if not (256 <= val <= 8192):
                            return self._send(400, {"ok": False, "error": "max_tokens must be between 256 and 8192"})
                        cfg["max_tokens"] = val
                    except (ValueError, TypeError):
                        return self._send(400, {"ok": False, "error": "max_tokens must be an integer between 256 and 8192"})

                if "apps" in body and isinstance(body["apps"], dict):
                    cfg["apps"] = body["apps"]
                elif "apps" not in cfg:
                    cfg["apps"] = DEFAULT_APPS.get(OS, {})

                if "smart_home_hosts" in body and isinstance(body["smart_home_hosts"], list):
                    cfg["smart_home_hosts"] = [str(h).strip() for h in body["smart_home_hosts"] if h]

                for sec in SECRET_FIELDS:
                    if sec in body and body[sec] is not None:
                        val = str(body[sec]).strip()
                        if val:
                            cfg[sec] = val
                    if body.get(f"clear_{sec}"):
                        cfg[sec] = ""
                if body.get("clear_key"):
                    cfg["api_key"] = ""
                save_config(cfg)
                return self._send(200, {"ok": True})
            if path == "/api/memory/add":
                mem = get_memory()
                if body.get("text"):
                    mem.append(body["text"].strip())
                    save_json(MEMORY_FILE, mem)
                return self._send(200, mem)
            if path == "/api/memory/delete":
                mem = get_memory()
                try:
                    i = int(body.get("index", -1))
                except (TypeError, ValueError):
                    i = -1
                if 0 <= i < len(mem):
                    mem.pop(i)
                    save_json(MEMORY_FILE, mem)
                return self._send(200, mem)
            if path == "/api/characters":
                chars = body.get("characters", [])
                clean = []
                for c in chars:
                    if c.get("name") and c.get("prompt"):
                        clean.append(
                            {
                                "id": c.get("id") or re.sub(r"\W+", "", c["name"].lower()) or "custom",
                                "name": c["name"][:40],
                                "voice": c.get("voice", "male"),
                                "prompt": c["prompt"][:2000],
                            }
                        )
                if clean:
                    save_json(CHARS_FILE, clean)
                return self._send(200, get_characters())
            if path == "/api/reset":
                reset_mode = body.get("mode") if isinstance(body, dict) else None
                with LOCK:
                    if reset_mode in HISTORIES:
                        HISTORIES[reset_mode].clear()
                    else:
                        HISTORIES["developer"].clear()
                        HISTORIES["cyber"].clear()
                return self._send(200, {"ok": True})
            if path == "/api/workspace/open":
                WORKSPACE.mkdir(exist_ok=True)
                if OS == "Windows":
                    os.startfile(str(WORKSPACE))
                elif OS == "Darwin":
                    subprocess.Popen(["open", str(WORKSPACE)])
                else:
                    subprocess.Popen(["xdg-open", str(WORKSPACE)])
                return self._send(200, {"ok": True, "path": str(WORKSPACE)})
            if path == "/api/remote/enable":
                set_remote(bool(body.get("enabled")))
                return self._send(200, remote_state())
            if path == "/api/remote/regenerate":
                regenerate_token()
                return self._send(200, remote_state())
            if path == "/api/browser/launch":
                if not nova_browser:
                    return self._send(500, {"error": "nova_browser module not available"})
                try:
                    res = nova_browser.launch_browser(body.get("url") or "about:blank")
                    if isinstance(res, dict):
                        return self._send(200, res)
                    return self._send(200, {"ok": bool(res), "running": nova_browser.is_cdp_available()})
                except Exception as e:
                    return self._send(200, {"ok": False, "error": str(e)})
            if path == "/api/browser/open":
                if not nova_browser:
                    return self._send(200, {"ok": False, "error": "nova_browser module not available"})
                try:
                    res = nova_browser.open_or_activate(body.get("url", ""))
                    return self._send(200, res)
                except Exception as e:
                    return self._send(200, {"ok": False, "error": str(e)})
            if path == "/api/browser/activate":
                if not nova_browser:
                    return self._send(200, {"ok": False, "error": "nova_browser module not available"})
                try:
                    ok = nova_browser.activate_tab(body.get("tab_id", ""))
                    return self._send(200, {"ok": ok})
                except Exception as e:
                    return self._send(200, {"ok": False, "error": str(e)})
            if path == "/api/browser/close":
                if not nova_browser:
                    return self._send(200, {"ok": False, "error": "nova_browser module not available"})
                try:
                    ok = nova_browser.close_tab(body.get("tab_id", ""))
                    return self._send(200, {"ok": ok})
                except Exception as e:
                    return self._send(200, {"ok": False, "error": str(e)})
            if path == "/api/timers/add":
                if not scheduler_engine:
                    return self._send(500, {"error": "scheduler_engine not available"})
                action = body.get("action")
                tid = scheduler_engine.SCHEDULER.add_timer(body.get("spec", "5m"), body.get("message", "Timer"), mode=body.get("mode", "developer"), action=action)
                return self._send(200, {"ok": True, "id": tid})
            if path == "/api/timers/cancel":
                if not scheduler_engine:
                    return self._send(500, {"error": "scheduler_engine not available"})
                try:
                    tid = int(body.get("id") or 0)
                except (TypeError, ValueError):
                    tid = 0
                scheduler_engine.SCHEDULER.cancel_timer(tid)
                return self._send(200, {"ok": True})
            if path == "/api/automations/add":
                if not scheduler_engine:
                    return self._send(500, {"error": "scheduler_engine not available"})
                aid = scheduler_engine.SCHEDULER.add_recurring_task(body.get("spec", "every 1h"), body.get("action", ""), body.get("label", ""), mode=body.get("mode", "developer"))
                return self._send(200, {"ok": True, "id": aid})
            if path == "/api/automations/cancel":
                if not scheduler_engine:
                    return self._send(500, {"error": "scheduler_engine not available"})
                scheduler_engine.SCHEDULER.cancel_recurring(body.get("id"))
                return self._send(200, {"ok": True})
            if path in ("/api/notes", "/api/notes/save"):
                if not memory_engine:
                    return self._send(500, {"error": "memory_engine not available"})
                nid = memory_engine.save_note(body.get("title", ""), body.get("content", ""), body.get("category", "general"))
                return self._send(200, {"ok": True, "id": nid})
            if path in ("/api/notes/delete",):
                if not memory_engine:
                    return self._send(500, {"error": "memory_engine not available"})
                del_id = body.get("id")
                if del_id is None or del_id == "":
                    del_id = body.get("title", "")
                ok = memory_engine.delete_note(del_id)
                return self._send(200, {"ok": ok})
            if path == "/api/vision/analyze":
                res = skill_screen_analyze(body.get("question", ""))
                return self._send(200, {"analysis": res})
            if path == "/api/browser/interact":
                if not nova_browser:
                    return self._send(200, {"ok": False, "error": "nova_browser not available"})
                try:
                    act = body.get("action")
                    val = body.get("value", "")
                    if act == "click":
                        res = nova_browser.click_element(val)
                    elif act == "type":
                        sel = body.get("selector", "")
                        res = nova_browser.type_in_element(sel, val)
                    elif act == "scroll":
                        res = nova_browser.scroll_page(val)
                    else:
                        res = "unknown action"
                    return self._send(200, {"result": res})
                except Exception as e:
                    return self._send(200, {"ok": False, "error": str(e)})
        except LLMError as e:
            return self._send(200, {"error": str(e)})
        except Exception as e:
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})
        self._send(404, {"error": "not found"})


class RemoteHandler(BaseHandler):
    """What a phone on your Wi-Fi can reach. Nothing else from Nova is exposed here."""

    DEFAULT_PORT = 8766

    def _local_only(self):
        return check_local_request(self, expected_port=getattr(self, "DEFAULT_PORT", 8766))

    STATIC = {
        "/": "remote.html",
        "/remote.html": "remote.html",
        "/remote.js": "remote.js",
        "/remote.css": "remote.css",
    }

    def _auth(self):
        if not get_config().get("remote_enabled"):
            self._send(403, {"error": "Mobile remote is turned off on the PC."})
            return False
        ip = self.client_address[0]
        now = time.time()
        with FAILS_LOCK:
            rec = FAILS.get(ip)
            if rec and now - rec[1] > 900:
                FAILS.pop(ip, None)
                rec = None
            if rec and rec[0] >= 5:
                self._send(429, {"error": "Too many wrong attempts. Locked out for 15 minutes."})
                return False
        tok = (self.headers.get("X-Nova-Token") or "").encode("utf-8")
        real = (get_config().get("remote_token") or "").encode("utf-8")
        if real and hmac.compare_digest(tok, real):
            with FAILS_LOCK:
                FAILS.pop(ip, None)
            REMOTE["last_seen"] = now
            return True
        with FAILS_LOCK:
            r = FAILS.setdefault(ip, [0, now])
            r[0] += 1
        self._send(401, {"error": "Not paired. Scan the QR code on your PC again."})
        return False

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/favicon.ico":
            svg_icon = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="45" fill="#02060d" stroke="#37d6ff" stroke-width="6"/><circle cx="50" cy="50" r="20" fill="#37d6ff"/></svg>"""
            return self._send(200, svg_icon, "image/svg+xml")
        name = self.STATIC.get(path)
        if name:
            if not get_config().get("remote_enabled"):
                return self._send(403, "Mobile remote is turned off on the PC.", "text/plain; charset=utf-8")
            f = WEB / name
            ctype = mimetypes.guess_type(str(f))[0] or "text/plain"
            return self._send(200, f.read_bytes(), ctype + "; charset=utf-8" if ctype.startswith("text/") or "javascript" in ctype else ctype)
        if path == "/api/remote/info":
            if not self._auth():
                return
            cfg = get_config()
            chars = get_characters()
            char = next((c for c in chars if c["id"] == cfg["character"]), chars[0])
            return self._send(
                200,
                {
                    "name": char["name"],
                    "user": cfg.get("user_name", ""),
                    "apps": sorted((cfg.get("apps") or {}).keys())[:12],
                    "has_key": bool(cfg.get("api_key")),
                    "language": cfg.get("language", "en-US"),
                },
            )
        self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/remote/chat":
            if not self._auth():
                return
            body = self._body()
            if body is None:
                return
            text = (body.get("message") or "").strip()[:1000]
            if not text:
                return self._send(400, {"error": "empty"})
            mode = body.get("mode") or "developer"
            try:
                return self._send(200, chat(text, source="phone", mode=mode))
            except LLMError as e:
                return self._send(200, {"error": str(e)})
            except Exception as e:
                return self._send(500, {"error": f"{type(e).__name__}: {e}"})
        self._send(404, {"error": "not found"})


def open_browser(url):
    """Open Nova AI in Edge or Chrome for full Web Speech API compatibility."""
    if OS == "Windows":
        candidates = [
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
        for exe in candidates:
            if os.path.isfile(exe):
                try:
                    subprocess.Popen([exe, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                except Exception:
                    pass
    webbrowser.open(url)


def main():
    cfg = get_config()
    port = int(cfg.get("port", 8765))
    if scheduler_engine:
        scheduler_engine.SCHEDULER.start()
    SilentThreadingHTTPServer.allow_reuse_address = True
    try:
        srv = SilentThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        if sys.stdout:
            print(f"Port {port} is busy. Nova may already be running: http://127.0.0.1:{port}")
        open_browser(f"http://127.0.0.1:{port}")
        return
    url = f"http://127.0.0.1:{port}"
    if sys.stdout:
        print(f"\n  NOVA AI is running at {url}\n  Use Chrome or Edge for voice. Press Ctrl+C to stop.\n")
    if cfg.get("remote_enabled"):
        start_remote()
        st = remote_state()
        if sys.stdout:
            if st["active"]:
                print("  Mobile remote is ON (same Wi-Fi). Open the Mobile panel in Nova to scan the QR code.\n")
            elif st["error"]:
                print("  " + st["error"] + "\n")
    if cfg.get("telegram_enabled") and telegram_gateway:
        try:
            telegram_gateway.start_telegram_daemon(cfg, chat)
            if sys.stdout:
                print("  Telegram Gateway is ON. Polling for remote commands.\n")
        except Exception as e:
            if sys.stdout:
                print(f"  [Telegram Gateway] Error: {e}\n")
    if cfg.get("discord_enabled") and discord_gateway:
        try:
            discord_gateway.start_discord_daemon(cfg, chat)
            if sys.stdout:
                print("  Discord Gateway is ON. Polling for remote messages.\n")
        except Exception as e:
            if sys.stdout:
                print(f"  [Discord Gateway] Error: {e}\n")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: open_browser(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nBye.")


if __name__ == "__main__":
    main()