#!/usr/bin/env python3
"""
Nova AI - Agentic Coding Skills Engine
Pure Python standard library (no pip packages).

Dynamically loads, parses, and matches mode-specific engineering skills
from skills/developer/*.md and skills/cyber/*.md into Nova's system prompts.
"""

import os
import re
import sys
import threading
from pathlib import Path

def get_bundled_skills_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "skills"
    elif getattr(sys, "frozen", False):
        exe_skills = Path(sys.executable).resolve().parent / "skills"
        if exe_skills.exists():
            return exe_skills
        return Path(sys.executable).resolve().parent / "skills"
    return Path(__file__).resolve().parent / "skills"

def get_user_skills_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent
    return base / "data" / "user_skills"

ROOT = Path(sys._MEIPASS) if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS") else (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent)
SKILLS_DIR = get_bundled_skills_dir()
USER_SKILLS_DIR = get_user_skills_dir()

# Attempt to reuse tokenizer from memory_engine if present, else fallback
try:
    from memory_engine import _tokenize
except Exception:
    def _tokenize(text: str):
        if not text:
            return []
        words = re.findall(r"[a-zA-Z0-9_\u0900-\u097F\u0980-\u09FF\u0600-\u06FF\u4E00-\u9FFF]+", text.lower())
        return [w for w in words if len(w) > 1]


class Skill:
    """Represents a loaded engineering skill with frontmatter and procedure content."""
    def __init__(self, name: str, description: str, triggers: list, content: str, filepath: Path, mtime: float):
        self.name = name
        self.description = description
        self.triggers = triggers
        self.content = content
        self.filepath = filepath
        self.mtime = mtime

    def to_dict(self):
        return {
            "name": self.name,
            "description": self.description,
            "triggers": self.triggers,
            "filepath": str(self.filepath),
        }

    def __repr__(self):
        return f"<Skill name={self.name!r} triggers={len(self.triggers)}>"


_SKILLS_CACHE = {
    "developer": {"mtime": 0.0, "files": set(), "skills": []},
    "cyber": {"mtime": 0.0, "files": set(), "skills": []},
}
_CACHE_LOCK = threading.Lock()


def parse_skill_file(filepath: Path) -> Skill:
    """Parse YAML-like frontmatter between triple dashes (---) and Markdown body."""
    raw = filepath.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, re.DOTALL)
    stat = filepath.stat()
    if not m:
        name = filepath.stem
        return Skill(name=name, description="", triggers=[], content=raw.strip(), filepath=filepath, mtime=stat.st_mtime)

    fm_text, content = m.group(1), m.group(2).strip()
    fm = {}
    for line in fm_text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip().lower()] = v.strip()

    name = fm.get("name", filepath.stem)
    description = fm.get("description", "")
    raw_triggers = fm.get("triggers", "")
    triggers = [t.strip().lower() for t in raw_triggers.split(",") if t.strip()]

    return Skill(
        name=name,
        description=description,
        triggers=triggers,
        content=content,
        filepath=filepath,
        mtime=stat.st_mtime
    )


def invalidate_cache():
    """Clear in-memory cached skills for all modes."""
    with _CACHE_LOCK:
        _SKILLS_CACHE["developer"] = {"mtime": 0.0, "files": set(), "skills": [], "file_sigs": set()}
        _SKILLS_CACHE["cyber"] = {"mtime": 0.0, "files": set(), "skills": [], "file_sigs": set()}

def install_user_skill(mode: str, name: str, content: str, description: str = "", triggers: list = None) -> Path:
    """Installs or updates a user skill in the writable user_skills directory."""
    mode = "cyber" if mode == "cyber" else "developer"
    dest_dir = get_user_skills_dir() / mode
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{name}.md" if not name.endswith(".md") else name
    dest_file = dest_dir / filename

    if not re.match(r"^---\s*\n.*?\n---\s*\n", content, re.DOTALL):
        fm_lines = [f"name: {name}"]
        if description:
            fm_lines.append(f"description: {description}")
        if triggers:
            if isinstance(triggers, list):
                fm_lines.append(f"triggers: {', '.join(triggers)}")
            else:
                fm_lines.append(f"triggers: {triggers}")
        content = f"---\n{chr(10).join(fm_lines)}\n---\n{content.strip()}\n"

    dest_file.write_text(content, encoding="utf-8")
    invalidate_cache()
    return dest_file

def load_skills(mode: str) -> list:
    """
    Reads bundled skills from sys._MEIPASS / skills / <mode> (or project skills/<mode>/)
    and user-installed skills from data/user_skills/<mode>/ next to the executable.
    Never reads or touches the other mode's directory.
    Caches results and automatically reloads if file modification times change.
    """
    mode = "cyber" if mode == "cyber" else "developer"
    bundled_dir = get_bundled_skills_dir() / mode
    user_dir = get_user_skills_dir() / mode

    bundled_files = sorted(bundled_dir.glob("*.md")) if bundled_dir.exists() else []
    user_files = sorted(user_dir.glob("*.md")) if user_dir.exists() else []
    all_files = bundled_files + user_files

    if not all_files:
        return []

    file_sigs = {(str(f.resolve()), f.stat().st_mtime) for f in all_files if f.exists()}
    current_filenames = {f.name for f in all_files}
    max_mtime = max((f.stat().st_mtime for f in all_files), default=0.0)

    with _CACHE_LOCK:
        cache = _SKILLS_CACHE.get(mode, {})
        if (
            cache.get("skills")
            and cache.get("file_sigs") == file_sigs
        ):
            return list(cache["skills"])

        skills_by_name = {}
        for f in bundled_files:
            try:
                skill = parse_skill_file(f)
                skills_by_name[skill.name] = skill
            except Exception:
                pass

        for f in user_files:
            try:
                skill = parse_skill_file(f)
                skills_by_name[skill.name] = skill
            except Exception:
                pass

        loaded = list(skills_by_name.values())
        _SKILLS_CACHE[mode] = {
            "skills": loaded,
            "mtime": max_mtime,
            "files": current_filenames,
            "file_sigs": file_sigs,
        }
        return list(loaded)


def select_skills(mode: str, message: str, limit: int = 2) -> list:
    """
    Ranks skills by trigger matches and semantic keyword relevance against the user message.
    Returns up to `limit` matching skills. Returns [] if no skills match.
    """
    if not message or not message.strip():
        return []

    skills = load_skills(mode)
    if not skills:
        return []

    msg_lower = message.lower().strip()
    msg_tokens = set(_tokenize(msg_lower))
    if not msg_tokens and not msg_lower:
        return []

    scored_skills = []

    for skill in skills:
        score = 0.0

        # 1. Trigger phrase & keyword matching
        for trigger in skill.triggers:
            trig_lower = trigger.lower().strip()
            if not trig_lower:
                continue

            # Direct substring match in message
            if trig_lower in msg_lower:
                # Multi-word triggers carry higher precision
                if " " in trig_lower:
                    score += 15.0
                else:
                    score += 8.0

            # Token overlap
            trig_tokens = set(_tokenize(trig_lower))
            overlap = trig_tokens & msg_tokens
            if overlap:
                score += len(overlap) * 3.5

        # 2. Description and skill name matching
        desc_tokens = set(_tokenize(skill.description))
        name_tokens = set(_tokenize(skill.name))

        name_overlap = name_tokens & msg_tokens
        if name_overlap:
            score += len(name_overlap) * 4.0

        desc_overlap = desc_tokens & msg_tokens
        if desc_overlap:
            score += len(desc_overlap) * 1.5

        if score > 0:
            scored_skills.append((score, skill))

    # Sort descending by score, tie-break by skill name for deterministic results
    scored_skills.sort(key=lambda item: (-item[0], item[1].name))

    return [skill for _, skill in scored_skills[:limit]]


def build_skill_prompt(mode: str, message: str) -> str:
    """
    Selects relevant skills for the user message and builds a formatted prompt block
    to append to the active system prompt. Returns an empty string if nothing matches.
    """
    matched = select_skills(mode, message, limit=2)
    if not matched:
        return ""

    blocks = [
        "\n\n--- ACTIVE ENGINEERING SKILLS (FOLLOW THESE PROCEDURES FOR THIS TURN) ---",
        "The user's request matches the following engineering procedure(s). Follow their step-by-step guidance rigorously:"
    ]

    for s in matched:
        blocks.append(f"\n### SKILL: {s.name.upper()}\n*{s.description}*\n\nProcedure:\n{s.content}")

    blocks.append("\n--- END ACTIVE ENGINEERING SKILLS ---\n")
    return "\n".join(blocks)
