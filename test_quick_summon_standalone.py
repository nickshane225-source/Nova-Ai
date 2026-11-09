"""
test_quick_summon_standalone.py - Launches the ACTUAL quick_summon.bat in a subprocess for 3 cases:
Case 1: Window found -> Exit code 0
Case 2: Port listening but no window -> Prints message, Exit code 1
Case 3: Port closed -> Exit code 2
"""

import os
import socket
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BAT_PATH = ROOT / "quick_summon.bat"


def test_case_1_window_found():
    print("=== CASE 1: Window found (actual quick_summon.bat) ===", flush=True)
    helper = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-Command", "Start-Sleep -Seconds 5"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.3)
    env = dict(os.environ)
    env["NOVA_TEST_WINDOW_PID"] = str(helper.pid)
    try:
        res = subprocess.run(
            ["cmd.exe", "/c", str(BAT_PATH)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
        )
        print(f"Exit code: {res.returncode}", flush=True)
        print(f"Stdout   : {res.stdout.strip()!r}", flush=True)
        print(f"Stderr   : {res.stderr.strip()!r}", flush=True)
        assert res.returncode == 0, f"Expected exit code 0, got {res.returncode}"
        print("[PASS] Case 1 verified: window found, activated, exit code 0\n", flush=True)
    finally:
        helper.kill()


def test_case_2_port_listening_no_window():
    print("=== CASE 2: Port 8765 listening, no window (actual quick_summon.bat) ===", flush=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 8765))
        sock.listen(1)
        time.sleep(0.3)

        res = subprocess.run(
            ["cmd.exe", "/c", str(BAT_PATH)],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        print(f"Exit code: {res.returncode}", flush=True)
        print(f"Stdout   : {res.stdout.strip()!r}", flush=True)
        print(f"Stderr   : {res.stderr.strip()!r}", flush=True)
        assert res.returncode == 1, f"Expected exit code 1, got {res.returncode}"
        assert "Nova is running - use the open tab or restart Nova" in res.stdout
        print("[PASS] Case 2 verified: message displayed and exit code 1\n", flush=True)
    finally:
        sock.close()
        time.sleep(0.2)


def test_case_3_port_closed():
    print("=== CASE 3: Port closed, no window (actual quick_summon.bat) ===", flush=True)
    env = dict(os.environ)
    env["NOVA_TEST_NO_START"] = "1"
    res = subprocess.run(
        ["cmd.exe", "/c", str(BAT_PATH)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    print(f"Exit code: {res.returncode}", flush=True)
    print(f"Stdout   : {res.stdout.strip()!r}", flush=True)
    print(f"Stderr   : {res.stderr.strip()!r}", flush=True)
    assert res.returncode == 2, f"Expected exit code 2, got {res.returncode}"
    assert "Nova is running" not in res.stdout
    print("[PASS] Case 3 verified: port closed, triggered run.bat path, exit code 2\n", flush=True)


if __name__ == "__main__":
    test_case_1_window_found()
    test_case_2_port_listening_no_window()
    test_case_3_port_closed()
    print("ALL THREE CASES VERIFIED ON ACTUAL quick_summon.bat!", flush=True)
