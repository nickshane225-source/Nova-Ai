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

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent

SKILLS_DIR = ROOT / "skills"

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


def load_skills(mode: str) -> list:
    """
    Reads only skills/<mode>/ and returns parsed skills.
    Never reads or touches the other mode's directory.
    Caches results and automatically reloads if file modification times change.
    """
    mode = "cyber" if mode == "cyber" else "developer"
    target_dir = SKILLS_DIR / mode
    if not target_dir.exists():
        return []

    files = sorted(target_dir.glob("*.md"))
    current_filenames = {f.name for f in files}
    max_mtime = max((f.stat().st_mtime for f in files), default=0.0)

    with _CACHE_LOCK:
        cache = _SKILLS_CACHE[mode]
        # Invalidate cache if files changed, added, removed, or mtime updated
        if (
            cache["skills"]
            and cache["mtime"] >= max_mtime
            and cache["files"] == current_filenames
        ):
            return list(cache["skills"])

        loaded = []
        for f in files:
            try:
                skill = parse_skill_file(f)
                loaded.append(skill)
            except Exception:
                pass

        cache["skills"] = loaded
        cache["mtime"] = max_mtime
        cache["files"] = current_filenames
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
