import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent


class TestNoSecretsInRepo(unittest.TestCase):
    """
    Security Regression Test:
    Scans all tracked files in git for contiguous API keys, bot tokens,
    and sensitive credential patterns:
    - Google Gemini AI Studio (AQ.)
    - Google Cloud API Key (AIza)
    - OpenAI / Anthropic secret keys (sk-)
    - GitHub Personal Access Tokens (ghp_, github_pat_)
    - Telegram bot tokens (digits:alphanumeric)
    - Discord bot tokens
    """

    PATTERNS = [
        ("AQ_KEY", re.compile(r"\bAQ\.[A-Za-z0-9_.-]{30,}\b")),
        ("AIZA_KEY", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
        ("SK_KEY", re.compile(r"\bsk-[a-zA-Z0-9_-]{30,}\b")),
        ("GHP_KEY", re.compile(r"\b(?:ghp_[a-zA-Z0-9]{30,}|github_pat_[a-zA-Z0-9_]{30,})\b")),
        ("TELEGRAM_BOT_TOKEN", re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{35,}\b")),
        ("DISCORD_BOT_TOKEN", re.compile(r"\b[MN][A-Za-z\d]{23,28}\.[\w-]{6}\.[\w-]{27,40}\b")),
    ]

    def test_no_secrets_in_tracked_files(self):
        try:
            tracked_output = subprocess.check_output(
                ["git", "ls-files"], cwd=ROOT_DIR, text=True, encoding="utf-8"
            )
            tracked_files = [line.strip() for line in tracked_output.splitlines() if line.strip()]
        except Exception:
            tracked_files = [
                str(p.relative_to(ROOT_DIR))
                for p in ROOT_DIR.rglob("*")
                if p.is_file() and not any(part.startswith(".") for part in p.parts)
            ]

        this_file_name = Path(__file__).name
        scan_extensions = (
            ".py", ".js", ".html", ".md", ".json", ".bat", ".sh", ".css", ".txt", ".yml", ".yaml"
        )

        matches = []
        for rel_path in tracked_files:
            if rel_path == this_file_name or rel_path.endswith(f"/{this_file_name}"):
                continue
            if not rel_path.endswith(scan_extensions):
                continue

            full_path = ROOT_DIR / rel_path
            if not full_path.exists():
                continue

            try:
                content = full_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            for line_no, line in enumerate(content.splitlines(), start=1):
                for name, pat in self.PATTERNS:
                    found = pat.findall(line)
                    if found:
                        for secret in found:
                            matches.append(
                                f"{rel_path}:{line_no} [{name}] matched pattern of length {len(secret)}"
                            )

        self.assertEqual(
            len(matches),
            0,
            f"Found {len(matches)} potential secrets in tracked files:\n" + "\n".join(matches),
        )


if __name__ == "__main__":
    unittest.main()
