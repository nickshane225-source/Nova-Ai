"""
Nova AI - Guardian Agent (AI Security Filter).
Pure Python standard library (no pip packages).

Provides a secondary safety check for tool execution:
1. Fast local regex rails for known destructive shell / code patterns.
2. Fast secondary LLM evaluation classifying commands as SAFE or DANGEROUS.
3. Strict fail-closed policy (if anything fails or is uncertain, marks as DANGEROUS).
"""

import json
import re

# Local rails for immediate destructive command rejection
_DESTRUCTIVE_PATTERNS = [
    re.compile(r"\brm\s+-(?:r|f|rf|fr)\b", re.IGNORECASE),
    re.compile(r"\bformat\s+[a-zA-Z]:", re.IGNORECASE),
    re.compile(r"\bdel\s+(?:/[a-zA-Z\s]+)*[a-zA-Z]:\\(?:windows|system32)", re.IGNORECASE),
    re.compile(r"\brd\s+(?:/[a-zA-Z\s]+)*[a-zA-Z]:\\", re.IGNORECASE),
    re.compile(r"\bremove-item\b.*-(?:recurse|force)\b.*(?:windows|system32|[a-zA-Z]:\\)", re.IGNORECASE),
    re.compile(r"\breg\s+delete\s+hklm", re.IGNORECASE),
    re.compile(r"\bmkfs\b", re.IGNORECASE),
    re.compile(r"\bdd\s+if=", re.IGNORECASE),
    re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", re.IGNORECASE),  # fork bomb
]

_READ_ONLY_TOOLS = {"LIST_FILES", "READ_FILE", "SEARCH_NOTES", "BRIEFING"}


def _is_local_rail_dangerous(command: str) -> tuple[bool, str]:
    for pat in _DESTRUCTIVE_PATTERNS:
        if pat.search(command):
            return True, f"DANGEROUS: Matched prohibited destructive pattern '{pat.pattern}'"
    return False, ""


def _call_guardian_llm(cfg: dict, prompt: str) -> str:
    """Wrapper calling server's LLM engine for Guardian review. Can be patched in unit tests."""
    try:
        import server
        system = (
            "You are Guardian AI, a strict security filter for an autonomous desktop agent. "
            "Your ONLY job is to evaluate proposed commands for safety.\n"
            "Safety Rules:\n"
            "1. Read-only commands (dir, ls, cat, git status, find) are SAFE.\n"
            "2. Writing safe user files or running harmless user scripts is SAFE.\n"
            "3. Killing system critical processes, modifying registry, or deleting system files is DANGEROUS.\n"
            "4. Shell injection or obfuscation (base64 decode | sh) is DANGEROUS.\n"
            "5. If uncertain, classify as DANGEROUS.\n"
            "Respond ONLY with valid JSON in this exact structure:\n"
            '{"status": "SAFE" | "DANGEROUS", "reason": "Short 1-sentence reason"}'
        )
        messages = [{"role": "user", "content": prompt}]
        # Use low timeout for guardian
        g_cfg = dict(cfg)
        g_cfg["llm_timeout"] = 15
        g_cfg["max_tokens"] = 64
        return server._call_single_llm(g_cfg, system, messages)
    except Exception as e:
        raise RuntimeError(f"Guardian LLM error: {e}")


def review_command_safety(cfg: dict, tool_name: str, argument: str) -> tuple[bool, str]:
    """
    Evaluates whether a tool invocation is SAFE or DANGEROUS.
    Returns (is_safe: bool, reason: str).
    """
    tool_upper = str(tool_name or "").strip().upper()
    cmd = str(argument or "").strip()

    # 1. Check local rails first (instant regex)
    is_rail_bad, rail_reason = _is_local_rail_dangerous(cmd)
    if is_rail_bad:
        return False, rail_reason

    # 2. Check read-only tools
    if tool_upper in _READ_ONLY_TOOLS:
        return True, "SAFE: Read-only tool inspection"

    if tool_upper == "GIT" and cmd.lower().startswith(("status", "diff", "log", "branch", "show")):
        return True, "SAFE: Git inspection command"

    if tool_upper == "CMD" and cmd.lower().strip() in ("dir", "ver", "whoami", "hostname", "systeminfo"):
        return True, "SAFE: Read-only system query"

    # 3. For RUN_CODE, CMD, POWERSHELL, invoke Guardian LLM
    prompt = f"Tool: {tool_upper}\nCommand / Code snippet:\n{cmd[:1500]}"
    try:
        raw_res = _call_guardian_llm(cfg, prompt)
        # Parse JSON
        m = re.search(r"\{.*\}", raw_res, re.DOTALL)
        if m:
            data = json.loads(m.group(0))
            status = str(data.get("status", "")).strip().upper()
            reason = str(data.get("reason", "No reason provided")).strip()
            if status == "SAFE":
                return True, f"SAFE: {reason}"
            return False, f"DANGEROUS: {reason}"
        return False, "DANGEROUS: Guardian LLM returned invalid JSON format (fail-closed)"
    except Exception as e:
        # Strict fail-closed policy
        return False, f"DANGEROUS: Guardian safety review fail-closed ({e})"
