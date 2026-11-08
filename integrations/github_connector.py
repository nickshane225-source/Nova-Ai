"""
GitHub Integration Connector for Nova AI.
Inspired by PocketPaw's GitHub tools, skills installer, and repo inspector.
Zero third-party pip dependencies - Python standard library only (urllib, json, zipfile, subprocess).
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict

from integrations import BaseIntegration

WORKSPACE_DIR = Path(__file__).resolve().parent.parent / "workspace"
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    SKILLS_DIR = Path(sys._MEIPASS) / "skills"
else:
    SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


class GitHubConnector(BaseIntegration):
    name = "github"
    description = "Inspect, clone, and analyze GitHub repositories, issues, PRs, file trees, and install skills."

    def run(self, cfg: Dict[str, Any], raw_arg: str) -> str:
        raw_arg = (raw_arg or "").strip()
        if not raw_arg:
            return "Usage: [[GITHUB: owner/repo | issues/prs/readme/tree/clone/install-skills/file:<path>]]"

        parts = [p.strip() for p in raw_arg.split("|", 1)]
        repo = parts[0].strip().strip("/").replace("https://github.com/", "")
        action = parts[1].strip() if len(parts) > 1 and parts[1].strip() else "info"

        repo_parts = repo.split("/")
        if len(repo_parts) != 2:
            return f"Invalid repository format '{repo}'. Expected 'owner/repo' (e.g. pocketpaw/pocketpaw)."
        owner, repo_name = repo_parts[0], repo_parts[1]
        import re
        if not re.match(r"^[a-zA-Z0-9_.-]+$", owner) or not re.match(r"^[a-zA-Z0-9_.-]+$", repo_name):
            return f"Invalid characters in repository name '{repo}'."
        if owner in (".", "..") or repo_name in (".", ".."):
            return "Path traversal in repository name is prohibited."

        WINDOWS_RESERVED = {
            "CON", "PRN", "AUX", "NUL",
            "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
            "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
        }
        if owner.upper() in WINDOWS_RESERVED or repo_name.upper() in WINDOWS_RESERVED:
            return "Refused: Repository name contains Windows reserved device name."

        token = (cfg or {}).get("github_token") or os.environ.get("GITHUB_TOKEN") or ""
        headers = {
            "User-Agent": "NovaAI-GitHubConnector/1.0",
            "Accept": "application/vnd.github.v3+json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        # Action 1: Clone repo to workspace
        if action.lower() == "clone":
            return self.clone_repo(repo, token)

        # Action 2: Install skills from repo
        if action.lower() in ("install-skills", "install_skills", "skills"):
            return self.install_skills_from_repo(repo, token)

        # Action 3: Inspect specific file
        if action.lower().startswith("file:"):
            file_path = action[5:].strip()
            return self.get_file_content(repo, file_path, headers)

        # Action 4: File tree
        if action.lower() == "tree":
            return self.get_repo_tree(repo, headers)

        # Action 5: Issues, PRs, README, or Info
        if action.lower() in ("issue", "issues"):
            url = f"https://api.github.com/repos/{repo}/issues?per_page=10&state=all"
        elif action.lower() in ("pr", "prs", "pulls"):
            url = f"https://api.github.com/repos/{repo}/pulls?per_page=10&state=all"
        elif action.lower() in ("readme", "read"):
            url = f"https://api.github.com/repos/{repo}/readme"
        else:
            url = f"https://api.github.com/repos/{repo}"

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return f"GitHub Error: Repository or resource '{repo}' not found (404)."
            if e.code == 403:
                return f"GitHub Error: Rate limit exceeded or access forbidden (403). Set 'github_token' in config."
            return f"GitHub API error: {e}"
        except Exception as e:
            return f"Failed to connect to GitHub API: {e}"

        # Format output cleanly
        if isinstance(data, list):
            if not data:
                return f"No {action} found in {repo}."
            lines = [f"Found {len(data)} {action} for {repo}:"]
            for item in data[:10]:
                num = item.get("number", "?")
                title = item.get("title", "No Title")
                state = item.get("state", "unknown")
                lines.append(f"- Issue #{num} [{state.upper()}]: {title}")
            return "\n".join(lines)

        if isinstance(data, dict):
            if "content" in data and data.get("encoding") == "base64":
                try:
                    decoded = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                    return f"README for {repo}:\n\n{decoded[:3000]}"
                except Exception:
                    pass
            full_name = data.get("full_name", repo)
            desc = data.get("description", "No description provided.")
            stars = data.get("stargazers_count", 0)
            forks = data.get("forks_count", 0)
            lang = data.get("language", "Not specified")
            return f"GitHub Repo: {full_name}\nDescription: {desc}\nLanguage: {lang} | Stars: ⭐ {stars} | Forks: 🍴 {forks}"

        return str(data)[:1000]

    def get_repo_tree(self, repo: str, headers: dict) -> str:
        """Fetches top-level and recursive files from the repository."""
        try:
            info_req = urllib.request.Request(f"https://api.github.com/repos/{repo}", headers=headers)
            with urllib.request.urlopen(info_req, timeout=15) as resp:
                repo_info = json.loads(resp.read().decode("utf-8"))
            default_branch = repo_info.get("default_branch", "main")
            
            tree_url = f"https://api.github.com/repos/{repo}/git/trees/{default_branch}?recursive=1"
            tree_req = urllib.request.Request(tree_url, headers=headers)
            with urllib.request.urlopen(tree_req, timeout=15) as resp:
                tree_data = json.loads(resp.read().decode("utf-8"))
            
            items = tree_data.get("tree", [])
            if not items:
                return f"Tree is empty for {repo}."
            
            lines = [f"📁 File Tree for {repo} (branch: {default_branch}, total items: {len(items)}):"]
            for item in items[:40]:
                path = item.get("path", "")
                itype = "📁" if item.get("type") == "tree" else "📄"
                lines.append(f"  {itype} {path}")
            if len(items) > 40:
                lines.append(f"  ... and {len(items) - 40} more files.")
            return "\n".join(lines)
        except Exception as e:
            return f"Failed to fetch repository tree: {e}"

    def get_file_content(self, repo: str, path: str, headers: dict) -> str:
        """Fetches raw or base64-decoded file content from GitHub repository."""
        path = (path or "").strip()
        if not path:
            return "Please specify a valid file path (e.g. [[GITHUB: owner/repo | file:path/to/file.py]])."
        clean_path = urllib.parse.quote(path.strip("/"))
        url = f"https://api.github.com/repos/{repo}/contents/{clean_path}"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("encoding") == "base64" and "content" in data:
                content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                return f"File: {path} ({repo})\n\n{content[:4000]}"
            return f"Unable to display file format for {path}."
        except Exception as e:
            return f"Failed to retrieve file '{path}': {e}"

    def clone_repo(self, repo: str, token: str = "") -> str:
        """Clones or downloads repository into Nova AI's workspace directory."""
        repo_name = repo.split("/")[-1]
        target_dir = (WORKSPACE_DIR / repo_name).resolve()
        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            target_dir.relative_to(WORKSPACE_DIR.resolve())
        except ValueError:
            return "Refused: Repository path attempts to escape workspace directory."

        auth_url = f"https://github.com/{repo}.git"
        if token:
            auth_url = f"https://x-access-token:{token}@github.com/{repo}.git"

        try:
            if target_dir.exists():
                return f"Repository '{repo}' already exists in workspace: {target_dir}"
            
            p = subprocess.run(
                ["git", "clone", "--depth=1", auth_url, str(target_dir)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if p.returncode == 0:
                return f"Successfully cloned '{repo}' into workspace: {target_dir}"
        except Exception:
            pass

        try:
            zip_url = f"https://api.github.com/repos/{repo}/zipball"
            headers = {"User-Agent": "NovaAI-GitHubConnector/1.0"}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            
            req = urllib.request.Request(zip_url, headers=headers)
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tf:
                temp_zip = Path(tf.name)
            
            with urllib.request.urlopen(req, timeout=60) as resp:
                with open(temp_zip, "wb") as f:
                    shutil.copyfileobj(resp, f)

            target_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(temp_zip, "r") as zf:
                root_prefix = zf.namelist()[0].split("/")[0] + "/"
                for member in zf.infolist():
                    if member.filename.startswith(root_prefix) and len(member.filename) > len(root_prefix):
                        rel_path = member.filename[len(root_prefix):]
                        dest_file = (target_dir / rel_path).resolve()
                        # Zip-Slip Guard
                        try:
                            dest_file.relative_to(target_dir.resolve())
                        except ValueError:
                            continue
                        if member.is_dir():
                            dest_file.mkdir(parents=True, exist_ok=True)
                        else:
                            dest_file.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(member) as src, open(dest_file, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                        if member.is_dir():
                            dest_file.mkdir(parents=True, exist_ok=True)
                        else:
                            dest_file.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(member) as src, open(dest_file, "wb") as dst:
                                shutil.copyfileobj(src, dst)
            
            temp_zip.unlink(missing_ok=True)
            return f"Successfully downloaded and extracted '{repo}' to workspace: {target_dir}"
        except Exception as e:
            return f"Failed to clone/download repository '{repo}': {e}"

    def install_skills_from_repo(self, repo: str, token: str = "") -> str:
        """Finds SKILL.md files in repository and installs them into Nova AI skills catalog."""
        try:
            import skills_engine
            dev_skills_dir = skills_engine.get_user_skills_dir() / "developer"
        except Exception:
            dev_skills_dir = SKILLS_DIR / "developer"
        dev_skills_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            auth_url = f"https://github.com/{repo}.git"
            if token:
                auth_url = f"https://x-access-token:{token}@github.com/{repo}.git"

            cloned = False
            try:
                p = subprocess.run(
                    ["git", "clone", "--depth=1", auth_url, str(tmp_path)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                cloned = (p.returncode == 0)
            except Exception:
                cloned = False

            if not cloned:
                return f"Could not clone '{repo}' to scan for skills. Ensure git is installed or repo is public."

            installed = []
            for root, dirs, files in os.walk(tmp_path):
                for f in files:
                    if f.upper() == "SKILL.MD":
                        src_file = Path(root) / f
                        skill_name = src_file.parent.name
                        if skill_name == tmp_path.name:
                            skill_name = repo.split("/")[-1]
                        dest_file = dev_skills_dir / f"{skill_name}.md"
                        shutil.copy2(src_file, dest_file)
                        installed.append(skill_name)

            if not installed:
                return f"No 'SKILL.md' files found in repository '{repo}'."

            try:
                import skills_engine
                skills_engine.invalidate_cache()
            except Exception:
                pass

            return f"Successfully installed {len(installed)} skill(s) from '{repo}': {', '.join(installed)}"
