"""
Nova Browser - Dedicated, Session-Persistent Browser Controller for Nova AI.

Pure Python standard library (no external dependencies needed).
Uses Chrome DevTools Protocol (CDP) to communicate with a dedicated Chrome or Edge instance.
Maintains persistent logins (YouTube, WhatsApp Web, Telegram Web) in data/nova_browser_profile.
Tracks all open tabs to prevent duplicate tabs and enable intelligent research.
"""

import base64
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

OS = platform.system()

# Paths
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
else:
    ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
PROFILE_DIR = DATA_DIR / "nova_browser_profile"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACE = ROOT / "workspace"
WORKSPACE.mkdir(parents=True, exist_ok=True)

CDP_HOST = "127.0.0.1"


def _pick_free_local_port() -> int:
    """Chooses a random free TCP port bound strictly to 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


CDP_PORT = _pick_free_local_port()

_browser_process = None
_browser_lock = threading.Lock()

# ----------------------------------------------------------------------------
# Browser Executable Discovery
# ----------------------------------------------------------------------------

def get_profile_dir() -> Path:
    return PROFILE_DIR

def get_browser_executable() -> str:
    """Finds Google Chrome or Microsoft Edge executable on the system."""
    system = platform.system()
    
    if system == "Windows":
        # Check Microsoft Edge first, then Chrome
        candidates = [
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path

        # Try registry lookup or PATH
        for binary in ["msedge.exe", "chrome.exe"]:
            found = shutil.which(binary)
            if found:
                return found

    elif system == "Darwin":
        candidates = [
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path

    else:  # Linux
        for binary in ["google-chrome", "google-chrome-stable", "microsoft-edge", "chromium-browser", "chromium"]:
            found = shutil.which(binary)
            if found:
                return found

    raise FileNotFoundError("Could not find Google Chrome or Microsoft Edge installed on this system.")


# ----------------------------------------------------------------------------
# CDP Health & Launching
# ----------------------------------------------------------------------------

def is_cdp_available(timeout: float = 1.0) -> bool:
    """Checks if the Nova Browser CDP endpoint is responding on localhost."""
    url = f"http://{CDP_HOST}:{CDP_PORT}/json/version"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NovaAI/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


class BrowserLaunchResult(dict):
    """Dictionary result representing browser launch outcome, maintaining backward compatibility with boolean checks."""
    def __bool__(self):
        return bool(self.get("ok", False))


def launch_browser(initial_url: str = "about:blank"):
    """Launches Nova Browser with dedicated profile and remote debugging enabled."""
    global _browser_process
    initial_url = normalize_target_url(initial_url or "about:blank")
    with _browser_lock:
        if is_cdp_available(timeout=1.0):
            return BrowserLaunchResult({"ok": True, "running": True})

        try:
            exe = get_browser_executable()
        except FileNotFoundError as e:
            print(f"[Nova Browser] Warning: Chrome or Edge executable not found: {e}")
            return BrowserLaunchResult({"ok": False, "error": "Chrome or Edge executable not found"})
        profile_path = str(get_profile_dir())

        args = [
            exe,
            f"--remote-debugging-port={CDP_PORT}",
            "--remote-debugging-address=127.0.0.1",
            f"--remote-allow-origins=http://127.0.0.1:{CDP_PORT}",
            f"--user-data-dir={profile_path}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-fre",
            "--disable-search-engine-choice-screen",
            "--disable-features=msFirstRunExperience,msEdgeWelcomePage",
            "--disable-sync",
            "--disable-background-networking",
            "--window-size=1280,850",
            initial_url or "about:blank"
        ]

        try:
            creationflags = 0
            if platform.system() == "Windows":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

            _browser_process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags
            )
        except Exception as e:
            print(f"[Nova Browser] Error launching browser: {e}")
            return BrowserLaunchResult({"ok": False, "error": str(e)})

        # Wait up to 5 seconds for CDP to become active
        for _ in range(25):
            time.sleep(0.2)
            if is_cdp_available(timeout=0.5):
                return BrowserLaunchResult({"ok": True, "running": True})

        return BrowserLaunchResult({"ok": False, "error": "CDP connection timed out"})


# ----------------------------------------------------------------------------
# URL & Tab Utilities
# ----------------------------------------------------------------------------

def extract_domain(url: str) -> str:
    """Extracts base domain (e.g. 'youtube.com') from a URL or keyword."""
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    try:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        if netloc.startswith("web."):
            netloc = netloc[4:]
        return netloc or url.lower()
    except Exception:
        return url.lower()


def find_tab_in_list(tabs: list, target_query_or_url: str) -> dict or None:
    """
    Finds an existing tab matching the query or URL.
    Checks exact URL, domain, or title keywords.
    """
    if not target_query_or_url or not tabs:
        return None

    query_norm = target_query_or_url.strip().lower()
    target_domain = extract_domain(query_norm)

    # 1. Match by domain or partial URL
    for tab in tabs:
        tab_url = tab.get("url", "").lower()
        if not tab_url:
            continue
        tab_domain = extract_domain(tab_url)

        if target_domain and (target_domain in tab_domain or tab_domain in target_domain):
            return tab
        if query_norm in tab_url:
            return tab

    # 2. Match by title
    for tab in tabs:
        tab_title = tab.get("title", "").lower()
        if query_norm in tab_title:
            return tab

    return None


# ----------------------------------------------------------------------------
# CDP REST Commands (Tabs Management)
# ----------------------------------------------------------------------------

def list_tabs() -> list:
    """Returns list of open browser tabs (filtering out internal background targets)."""
    if not is_cdp_available(timeout=0.5):
        if not launch_browser():
            return []

    url = f"http://{CDP_HOST}:{CDP_PORT}/json/list"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NovaAI/1.0"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            # Filter only page targets
            return [t for t in data if t.get("type") == "page"]
    except Exception as e:
        print(f"[Nova Browser] Error fetching tabs: {e}")
        return []


def activate_tab(tab_id: str) -> bool:
    """Brings an existing tab to front and focuses it."""
    url = f"http://{CDP_HOST}:{CDP_PORT}/json/activate/{tab_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NovaAI/1.0"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return resp.status == 200 or resp.read().decode("utf-8").strip() == "Target activated"
    except Exception as e:
        print(f"[Nova Browser] Error activating tab {tab_id}: {e}")
        return False


def open_new_tab(target_url: str) -> dict or None:
    """Opens a new tab with target_url via CDP."""
    target_url = normalize_target_url(target_url)
    if not is_cdp_available(timeout=0.5):
        if not launch_browser(target_url):
            return None
        time.sleep(1.0)
        tabs = list_tabs()
        return tabs[0] if tabs else None

    if not re.match(r"^(https?|file)://", target_url, re.I) and not target_url.startswith("about:"):
        target_url = "https://" + target_url

    encoded_url = urllib.parse.quote(target_url, safe=":/?#[]@!$&'()*+,;=")
    url = f"http://{CDP_HOST}:{CDP_PORT}/json/new?{encoded_url}"
    try:
        req = urllib.request.Request(url, method="PUT", headers={"User-Agent": "NovaAI/1.0"})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        # Some Chrome versions accept GET for /json/new
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "NovaAI/1.0"})
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[Nova Browser] Error opening tab {target_url}: {e}")
            return None


def close_tab(tab_id: str) -> bool:
    """Closes tab with specified ID."""
    url = f"http://{CDP_HOST}:{CDP_PORT}/json/close/{tab_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NovaAI/1.0"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return resp.status == 200 or resp.read().decode("utf-8").strip() == "Target is closing"
    except Exception as e:
        print(f"[Nova Browser] Error closing tab {tab_id}: {e}")
        return False


def is_local_target(target: str) -> bool:
    """Returns True if target is a file: scheme, drive letter, UNC path, leading / ./ ../, traversal .., or an existing path inside the workspace."""
    target = (target or "").strip().strip('"').strip("'")
    if not target or target.lower() in ("blank", "about:blank"):
        return False
    if re.match(r"^(https?|about|chrome|edge):", target, re.I):
        return False
    if target.lower().startswith("file:"):
        return True
    if (
        re.match(r"^[a-zA-Z]:[/\\]", target)
        or target.startswith("\\\\")
        or target.startswith("/")
        or target.startswith("./")
        or target.startswith(".\\")
        or target.startswith("../")
        or target.startswith("..\\")
        or ".." in re.split(r"[/\\]", target)
    ):
        return True
    try:
        clean_rel = target.lstrip("/\\")
        if clean_rel:
            ws_cand = WORKSPACE / clean_rel
            root_cand = ROOT / clean_rel
            if ws_cand.exists() or ws_cand.is_symlink() or root_cand.exists() or root_cand.is_symlink():
                return True
    except Exception:
        pass
    return False


def _resolve_local_target_in_workspace(target: str) -> Path:
    """Resolves a local file target or file:// URI strictly within WORKSPACE and verifies it is not sensitive."""
    raw = (target or "").strip().strip('"').strip("'")
    if raw.startswith("\\\\"):
        raise PermissionError("Access denied: UNC network paths are outside the Nova workspace.")
    if raw.lower().startswith("file:"):
        parsed = urllib.parse.urlparse(raw)
        if parsed.netloc and parsed.netloc.lower() not in ("", "localhost"):
            raise PermissionError("Access denied: remote UNC file:// host is outside the Nova workspace.")
        local_path_str = urllib.request.url2pathname(parsed.path)
        if local_path_str.startswith("\\\\") and not re.match(r"^\\\\\?\\[a-zA-Z]:", local_path_str):
            raise PermissionError("Access denied: UNC network paths are outside the Nova workspace.")
    else:
        local_path_str = raw

    srv = sys.modules.get("server") or sys.modules.get("__main__")
    if srv is None or not hasattr(srv, "resolve_workspace_path"):
        import server as srv

    p = Path(local_path_str)
    if not p.is_absolute():
        ws_candidate = WORKSPACE / local_path_str.lstrip("/\\")
        root_candidate = ROOT / local_path_str.lstrip("/\\")
        # If the relative path does not exist in WORKSPACE, or if it refers to an existing file in ROOT outside WORKSPACE, block it
        if not ws_candidate.exists():
            if root_candidate.exists() or srv.is_sensitive_nova_file(root_candidate):
                raise PermissionError("Access denied: local path outside workspace or sensitive Nova file is blocked.")
            raise PermissionError("Local file does not exist inside the Nova workspace.")

    # Browser local file access is strictly restricted to the workspace (never outside workspace)
    resolved = srv.resolve_workspace_path(local_path_str, cfg={"allow_outside_workspace": False})
    if srv.is_sensitive_nova_file(resolved):
        raise PermissionError("Access denied: access to sensitive Nova configuration or data files is blocked.")
    if not resolved.exists():
        raise PermissionError("Local file does not exist inside the Nova workspace.")
    return resolved


def normalize_target_url(target: str) -> str:
    target = (target or "").strip().strip('"').strip("'")
    if not target or target.lower() in ("blank", "about:blank"):
        return "about:blank"
    # Local file path or file:// URI -> enforce workspace boundary and sensitive file check
    if is_local_target(target):
        resolved = _resolve_local_target_in_workspace(target)
        return resolved.as_uri()
    # Web URL
    if not re.match(r"^(https?|about|chrome|edge):", target, re.I):
        if "." in target and " " not in target and not target.startswith("/"):
            return "https://" + target
        else:
            return f"https://www.google.com/search?q={urllib.parse.quote_plus(target)}"
    return target


def open_or_activate(target_url: str) -> dict:
    """
    Intelligently opens a URL or local file in Nova Browser (Edge)
    or activates the existing tab if already open.
    Prevents duplicate tabs and gives Nova full CDP automation control.
    """
    target_url = normalize_target_url(target_url)

    if not is_cdp_available(timeout=0.5):
        ok = launch_browser(target_url)
        if not ok:
            raise RuntimeError(f"Could not launch Nova Browser for {target_url}")
        tabs = []
        for _ in range(15):
            time.sleep(0.3)
            tabs = list_tabs()
            if tabs:
                break
        if tabs and target_url and target_url not in ["about:blank", "chrome://newtab/", "edge://newtab/"]:
            try:
                execute_cdp_eval(tabs[0], f"window.location.href = {json.dumps(target_url)};")
                activate_tab(tabs[0]["id"])
            except Exception:
                pass
        return {
            "status": "launched",
            "message": f"Launched Nova Browser (Edge) with {target_url}",
            "tab": tabs[0] if tabs else None,
            "already_open": False
        }

    tabs = list_tabs()
    existing_tab = find_tab_in_list(tabs, target_url)

    if existing_tab:
        activate_tab(existing_tab["id"])
        return {
            "status": "activated",
            "message": f"Activated tab '{existing_tab.get('title')}' in Nova Browser",
            "tab": existing_tab,
            "already_open": True
        }
    else:
        # If there is just one blank tab, navigate it
        blank_urls = ["about:blank", "chrome://newtab/", "edge://newtab/"]
        if len(tabs) == 1 and tabs[0].get("url") in blank_urls:
            execute_cdp_eval(tabs[0], f"window.location.href = {json.dumps(target_url)};")
            activate_tab(tabs[0]["id"])
            return {
                "status": "navigated",
                "message": f"Navigated Nova Browser tab to {target_url}",
                "tab": tabs[0],
                "already_open": False
            }

        new_tab = open_new_tab(target_url)
        if new_tab:
            activate_tab(new_tab["id"])
        return {
            "status": "opened",
            "message": f"Opened {target_url} in Nova Browser",
            "tab": new_tab,
            "already_open": False
        }


# ----------------------------------------------------------------------------
# Minimal Pure Python WebSocket Client for CDP Runtime Evaluation
# ----------------------------------------------------------------------------

def _ws_connect_and_eval(ws_url: str, js_code: str, timeout: float = 5.0) -> dict:
    """
    Performs RFC 6455 WebSocket handshake and sends Runtime.evaluate JSON-RPC command
    using pure Python standard library sockets. Supports both Edge and Chrome.
    """
    parsed = urllib.parse.urlparse(ws_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or CDP_PORT
    path = parsed.path

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))

        # Generate Sec-WebSocket-Key
        raw_key = os.urandom(16)
        sec_key = base64.b64encode(raw_key).decode("ascii")

        # Handshake
        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {sec_key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        s.sendall(handshake.encode("utf-8"))

        # Read handshake response
        resp_headers = b""
        while b"\r\n\r\n" not in resp_headers:
            chunk = s.recv(1024)
            if not chunk:
                break
            resp_headers += chunk

        # Support both Edge ("101 WebSocket Protocol Handshake") and Chrome ("101 Switching Protocols")
        if b" 101 " not in resp_headers and b"101 " not in resp_headers:
            return {"error": "WebSocket handshake failed"}

        # Prepare CDP Command: Runtime.evaluate
        msg_id = 1
        cmd = {
            "id": msg_id,
            "method": "Runtime.evaluate",
            "params": {
                "expression": js_code,
                "returnByValue": True,
                "awaitPromise": True
            }
        }
        payload = json.dumps(cmd).encode("utf-8")

        # Construct masked WebSocket frame (client must mask payload)
        mask_key = os.urandom(4)
        masked_payload = bytearray(len(payload))
        for i in range(len(payload)):
            masked_payload[i] = payload[i] ^ mask_key[i % 4]

        # Header: FIN + Text Opcode (0x81)
        length = len(payload)
        if length <= 125:
            frame = bytes([0x81, 0x80 | length]) + mask_key + masked_payload
        elif length <= 65535:
            frame = bytes([0x81, 0x80 | 126]) + struct.pack("!H", length) + mask_key + masked_payload
        else:
            frame = bytes([0x81, 0x80 | 127]) + struct.pack("!Q", length) + mask_key + masked_payload

        s.sendall(frame)

        # Read response frame(s)
        raw_resp = b""
        start_time = time.time()
        while time.time() - start_time < timeout:
            chunk = s.recv(4096)
            if not chunk:
                break
            raw_resp += chunk
            while len(raw_resp) >= 2:
                # Basic frame parsing
                payload_len = raw_resp[1] & 0x7F
                offset = 2
                if payload_len == 126:
                    if len(raw_resp) < 4:
                        break
                    payload_len = struct.unpack("!H", raw_resp[2:4])[0]
                    offset = 4
                elif payload_len == 127:
                    if len(raw_resp) < 10:
                        break
                    payload_len = struct.unpack("!Q", raw_resp[2:10])[0]
                    offset = 10

                if len(raw_resp) >= offset + payload_len:
                    body = raw_resp[offset:offset + payload_len]
                    raw_resp = raw_resp[offset + payload_len:]
                    try:
                        result_json = json.loads(body.decode("utf-8", errors="ignore"))
                        if result_json.get("id") == msg_id:
                            return result_json
                    except Exception:
                        pass
                else:
                    break
        return {"error": "Timeout waiting for CDP response"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        try:
            s.close()
        except Exception:
            pass


def execute_cdp_eval(tab: dict, js_code: str) -> dict:
    """Executes JavaScript inside the given tab via CDP WebSocket."""
    ws_url = tab.get("webSocketDebuggerUrl")
    if not ws_url:
        return {"error": "Tab has no webSocketDebuggerUrl"}
    return _ws_connect_and_eval(ws_url, js_code)


# ----------------------------------------------------------------------------
# High-Level Automation Skills (Research, YouTube, WhatsApp, Telegram)
# ----------------------------------------------------------------------------

def read_page_content(query_or_url: str = None) -> dict:
    """
    Extracts page title, URL, and readable body text from an open tab in Nova Browser.
    If query_or_url is a URL, newspaper site, or file not yet open, opens it first.
    Used for web research and newspaper reading by Nova AI.
    """
    if query_or_url and is_local_target(query_or_url):
        try:
            normalized_local = normalize_target_url(query_or_url)
            open_or_activate(normalized_local)
            time.sleep(1.0)
        except (PermissionError, ValueError) as e:
            return {"error": str(e)}
    elif query_or_url and re.match(r"^https?://", query_or_url, re.I):
        open_or_activate(query_or_url)
        time.sleep(1.0)

    tabs = list_tabs()
    if not tabs:
        return {"error": "Nova Browser is not open or has no tabs."}

    target_tab = None
    if query_or_url:
        target_tab = find_tab_in_list(tabs, query_or_url)

    if not target_tab:
        target_tab = tabs[0]

    js = """
    (() => {
        const title = document.title || "";
        const url = window.location.href;
        let clone = document.body ? document.body.cloneNode(true) : null;
        if (clone) {
            const useless = clone.querySelectorAll('script, style, noscript, iframe, svg');
            useless.forEach(el => el.remove());
            let text = clone.innerText || clone.textContent || "";
            text = text.replace(/\\s+/g, ' ').trim();
            return {
                title: title,
                url: url,
                content: text.slice(0, 4000)
            };
        }
        return {
            title: title,
            url: url,
            content: ""
        };
    })()
    """
    res = execute_cdp_eval(target_tab, js)
    val = res.get("result", {}).get("result", {}).get("value")
    if val:
        return val
    return {
        "title": target_tab.get("title", ""),
        "url": target_tab.get("url", ""),
        "content": "Could not extract full DOM text (page might still be loading)."
    }


def get_first_youtube_video(query: str) -> str:
    """Searches YouTube and returns the first playable video URL."""
    clean = (query or "").strip().lstrip("|").strip()
    if not clean:
        return "https://www.youtube.com"
    if is_local_target(clean):
        _resolve_local_target_in_workspace(clean)
        raise PermissionError("Refused: YouTube action cannot open local files.")
    if clean.startswith("http://") or clean.startswith("https://"):
        return clean
    try:
        search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(clean)}"
        req = urllib.request.Request(search_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            vids = re.findall(r'/watch\?v=([a-zA-Z0-9_-]{11})', html)
            if vids:
                return f"https://www.youtube.com/watch?v={vids[0]}"
    except Exception as e:
        print(f"[Nova Browser] Error fetching top YouTube video: {e}")
    return f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(clean)}"


def youtube_action(action: str, query_or_url: str = "") -> str:
    """
    Controls YouTube inside Nova Browser (Edge) with full CDP automation.
    Plays songs, pauses, searches, or manages tabs in Nova's personal browser.
    """
    try:
        # Clean up pipes and parameters
        action = (action or "play").lower().strip()
        query_or_url = (query_or_url or "").strip().lstrip("|").strip()

        if query_or_url and is_local_target(query_or_url):
            _resolve_local_target_in_workspace(query_or_url)
            return "Refused: YouTube action cannot open local files."

        # If user passed "play" but the query was in action or vice versa
        if action not in ["play", "pause", "resume", "stop", "search", "open"]:
            query_or_url = f"{action} {query_or_url}".strip()
            if is_local_target(query_or_url):
                _resolve_local_target_in_workspace(query_or_url)
                return "Refused: YouTube action cannot open local files."
            action = "play"

        tabs = list_tabs()
        yt_tab = find_tab_in_list(tabs, "youtube.com")

        if action == "play":
            if not query_or_url:
                target_url = "https://www.youtube.com"
                msg_action = "Opened YouTube in Nova Browser"
            else:
                target_url = get_first_youtube_video(query_or_url)
                msg_action = f"Playing '{query_or_url}' on YouTube in Nova Browser"

            if yt_tab:
                execute_cdp_eval(yt_tab, f"window.location.href = {json.dumps(target_url)};")
                activate_tab(yt_tab["id"])
                target_tab_ref = yt_tab
            else:
                open_or_activate(target_url)
                time.sleep(0.8)
                current_tabs = list_tabs()
                target_tab_ref = find_tab_in_list(current_tabs, "youtube.com") or (current_tabs[0] if current_tabs else None)
                if target_tab_ref:
                    activate_tab(target_tab_ref["id"])

            # Ensure video autoplay and un-mute via CDP in Nova Browser
            def _ensure_playback(tab_info):
                if not tab_info:
                    return
                for _ in range(4):
                    time.sleep(1.5)
                    try:
                        execute_cdp_eval(tab_info, "const v = document.querySelector('video'); if (v) { v.muted = false; v.play(); }")
                    except Exception:
                        pass

            if target_tab_ref:
                threading.Thread(target=_ensure_playback, args=(target_tab_ref,), daemon=True).start()

            return f"{msg_action}: {target_url}"

        if action == "open":
            if yt_tab:
                activate_tab(yt_tab["id"])
                return "Switched to YouTube tab in Nova Browser."
            open_or_activate("https://www.youtube.com")
            return "Opened YouTube in Nova Browser."

        if action == "search":
            target = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query_or_url)}" if query_or_url else "https://www.youtube.com"
            if yt_tab:
                execute_cdp_eval(yt_tab, f"window.location.href = {json.dumps(target)};")
                activate_tab(yt_tab["id"])
                return f"Searched YouTube for '{query_or_url}' in Nova Browser."
            open_or_activate(target)
            return f"Searched YouTube for '{query_or_url}' in Nova Browser."

        if not yt_tab:
            open_or_activate("https://www.youtube.com")
            return "Opened YouTube in Nova Browser."

        activate_tab(yt_tab["id"])
        if action in ["pause", "stop"]:
            execute_cdp_eval(yt_tab, "const v = document.querySelector('video'); if (v) v.pause();")
            return "Paused YouTube video in Nova Browser."
        elif action in ["resume", "play"]:
            execute_cdp_eval(yt_tab, "const v = document.querySelector('video'); if (v) { v.muted = false; v.play(); }")
            return "Resumed YouTube video in Nova Browser."

        return f"Active YouTube tab in Nova Browser: {yt_tab.get('title')} ({yt_tab.get('url')})"

    except (PermissionError, ValueError) as e:
        return f"Refused: {e}"
    except Exception as e:
        # Fallback to default system browser so it NEVER fails!
        try:
            target = get_first_youtube_video(query_or_url) if (action != "search" and query_or_url) else (
                f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query_or_url)}" if query_or_url else "https://www.youtube.com"
            )
            webbrowser.open(target)
            return f"Opened and playing YouTube in default browser: {target}"
        except Exception as e2:
            return f"Error controlling YouTube: {e} / {e2}"


def whatsapp_action(action: str, contact: str = "", message: str = "") -> str:
    """
    Controls WhatsApp Web in Nova Browser.
    Preserves user login in data/nova_browser_profile.
    """
    whatsapp_url = "https://web.whatsapp.com"
    status = open_or_activate(whatsapp_url)
    tabs = list_tabs()
    wa_tab = find_tab_in_list(tabs, "whatsapp.com")

    if not wa_tab:
        return "Could not connect to WhatsApp Web tab in Nova Browser."

    if not contact and not message:
        return (
            "Opened WhatsApp Web in Nova Browser. If this is your first time, scan the QR code to log in. "
            "Your session is permanently saved in Nova Browser's private profile."
        )

    # If contact and message provided, use WhatsApp direct click-to-chat API url
    if contact and message:
        clean_contact = re.sub(r"[^\d+]", "", contact)
        if clean_contact:
            send_url = f"https://web.whatsapp.com/send?phone={clean_contact}&text={urllib.parse.quote(message)}"
            execute_cdp_eval(wa_tab, f"window.location.href = {json.dumps(send_url)};")
            activate_tab(wa_tab["id"])
            return f"Navigated WhatsApp Web to chat with {clean_contact}. Message drafted in Nova Browser."
        else:
            return (
                f"Activated WhatsApp Web for contact '{contact}'. Please provide full phone number with country code "
                f"to direct-link, or use the open chat."
            )

    return f"WhatsApp Web is active in Nova Browser: {wa_tab.get('title')}"


def telegram_action(action: str, chat: str = "", message: str = "") -> str:
    """
    Controls Telegram Web in Nova Browser.
    Preserves user login in data/nova_browser_profile.
    """
    tg_url = "https://web.telegram.org/a/"
    status = open_or_activate(tg_url)
    tabs = list_tabs()
    tg_tab = find_tab_in_list(tabs, "telegram.org")

    if not tg_tab:
        return "Could not connect to Telegram Web tab in Nova Browser."

    if not chat and not message:
        return (
            "Opened Telegram Web in Nova Browser. If this is your first time, log in once. "
            "Your login is permanently remembered in Nova Browser's private profile."
        )

    if chat:
        clean_chat = chat.lstrip("@").strip()
        nav_url = f"https://web.telegram.org/a/#{clean_chat}"
        execute_cdp_eval(tg_tab, f"window.location.href = {json.dumps(nav_url)};")
        activate_tab(tg_tab["id"])
        return f"Opened Telegram chat with @{clean_chat} in Nova Browser."

    return f"Telegram Web is active in Nova Browser: {tg_tab.get('title')}"


# ----------------------------------------------------------------------------
# Interactive DOM Automation (Click, Type, Scroll, Visual Capture)
# ----------------------------------------------------------------------------

def build_scroll_js(direction_or_pixels: str) -> str:
    s = (direction_or_pixels or "").strip().lower()
    if s == "top":
        return "window.scrollTo(0, 0);"
    elif s == "bottom":
        return "window.scrollTo(0, document.body.scrollHeight);"
    elif s == "up":
        return "window.scrollBy(0, -600);"
    elif s.isdigit():
        return f"window.scrollBy(0, {s});"
    elif s.startswith("-") and s[1:].isdigit():
        return f"window.scrollBy(0, {s});"
    else:  # default down
        return "window.scrollBy(0, 600);"


def build_click_js(selector_or_text: str) -> str:
    escaped = json.dumps(selector_or_text.strip())
    return f"""
    (() => {{
        const target = {escaped};
        // 1. Try CSS selector
        try {{
            const el = document.querySelector(target);
            if (el) {{
                el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                el.click();
                return 'Clicked element matching selector: ' + target;
            }}
        }} catch (e) {{}}

        // 2. Try text search across clickable elements (button, a, input[type=submit])
        const candidates = Array.from(document.querySelectorAll('button, a, [role="button"], input[type="submit"], input[type="button"]'));
        for (const el of candidates) {{
            const txt = (el.innerText || el.value || el.getAttribute('aria-label') || '').toLowerCase();
            if (txt.includes(target.toLowerCase())) {{
                el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                el.click();
                return 'Clicked ' + el.tagName.toLowerCase() + ' containing text: ' + target;
            }}
        }}
        return 'Could not find element matching: ' + target;
    }})()
    """


def build_type_js(selector: str, text: str) -> str:
    escaped_sel = json.dumps(selector.strip())
    escaped_val = json.dumps(text)
    return f"""
    (() => {{
        const sel = {escaped_sel};
        const val = {escaped_val};
        let el = null;
        try {{
            el = document.querySelector(sel);
        }} catch (e) {{}}

        if (!el) {{
            // Fallback: first visible input/textarea
            el = document.querySelector('input[type="text"], input[type="search"], textarea, input:not([type="hidden"])');
        }}

        if (!el) return 'No input field found.';

        el.focus();
        el.value = val;
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
        return 'Typed text into ' + el.tagName.toLowerCase();
    }})()
    """


def click_element(selector_or_text: str) -> str:
    tabs = list_tabs()
    if not tabs:
        return "Nova Browser has no open tabs."
    tab = tabs[0]
    js = build_click_js(selector_or_text)
    res = execute_cdp_eval(tab, js)
    val = res.get("result", {}).get("result", {}).get("value")
    return val or "Click action executed."


def type_in_element(selector: str, text: str) -> str:
    tabs = list_tabs()
    if not tabs:
        return "Nova Browser has no open tabs."
    tab = tabs[0]
    js = build_type_js(selector, text)
    res = execute_cdp_eval(tab, js)
    val = res.get("result", {}).get("result", {}).get("value")
    return val or "Type action executed."


def scroll_page(direction_or_pixels: str) -> str:
    tabs = list_tabs()
    if not tabs:
        return "Nova Browser has no open tabs."
    tab = tabs[0]
    js = build_scroll_js(direction_or_pixels)
    execute_cdp_eval(tab, js)
    return f"Scrolled page: {direction_or_pixels}"

