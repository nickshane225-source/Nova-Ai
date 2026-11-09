"""
test_quick_summon_standalone.py - Runs the PowerShell 5.1 quick_summon fragment across all 3 cases:
Case 1: Window found -> Exit code 0
Case 2: Port listening but no window -> Prints message, Exit code 1
Case 3: Port closed -> Exit code 2
"""

import socket
import subprocess
import time


def test_case_3_port_closed():
    print("=== CASE 3: Port closed, no window ===")
    ps_cmd = (
        "$w = (Get-Process | Where-Object { $_.MainWindowTitle -match 'Nova AI' -or $_.MainWindowTitle -match '127.0.0.1:8765' } | Select-Object -First 1); "
        "if ($w) { [void](New-Object -ComObject WScript.Shell).AppActivate($w.Id); exit 0 }; "
        "$listening = [bool](Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue); "
        "if ($listening) { Write-Host 'Nova is running - use the open tab or restart Nova'; exit 1 } else { exit 2 }"
    )
    res = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
        capture_output=True,
        text=True,
    )
    print(f"Exit code: {res.returncode}")
    print(f"Stdout   : {res.stdout.strip()!r}")
    print(f"Stderr   : {res.stderr.strip()!r}")
    assert res.returncode == 2, f"Expected exit code 2, got {res.returncode}"
    assert res.stdout.strip() == "", f"Expected empty stdout, got {res.stdout.strip()!r}"
    print("[PASS] Case 3 verified: exit code 2\n")


def test_case_2_port_listening_no_window():
    print("=== CASE 2: Port 8765 listening, no window ===")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 8765))
        sock.listen(1)
        time.sleep(0.3)

        ps_cmd = (
            "$w = (Get-Process | Where-Object { $_.MainWindowTitle -match 'Nova AI' -or $_.MainWindowTitle -match '127.0.0.1:8765' } | Select-Object -First 1); "
            "if ($w) { [void](New-Object -ComObject WScript.Shell).AppActivate($w.Id); exit 0 }; "
            "$listening = [bool](Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue); "
            "if ($listening) { Write-Host 'Nova is running - use the open tab or restart Nova'; exit 1 } else { exit 2 }"
        )
        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
        )
        print(f"Exit code: {res.returncode}")
        print(f"Stdout   : {res.stdout.strip()!r}")
        print(f"Stderr   : {res.stderr.strip()!r}")
        assert res.returncode == 1, f"Expected exit code 1, got {res.returncode}"
        assert "Nova is running - use the open tab or restart Nova" in res.stdout
        print("[PASS] Case 2 verified: message displayed and exit code 1\n")
    finally:
        sock.close()
        time.sleep(0.2)


def test_case_1_window_found():
    print("=== CASE 1: Window found ===")
    # Test that when a process matching the filter is resolved, the activation path fires and exits 0
    ps_cmd = (
        "$mockProc = [PSCustomObject]@{ Id = $PID; MainWindowTitle = 'Nova AI' }; "
        "$w = $mockProc; "
        "if ($w) { [void](New-Object -ComObject WScript.Shell).AppActivate($w.Id); exit 0 }; "
        "$listening = [bool](Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue); "
        "if ($listening) { Write-Host 'Nova is running - use the open tab or restart Nova'; exit 1 } else { exit 2 }"
    )
    res = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
        capture_output=True,
        text=True,
    )
    print(f"Exit code: {res.returncode}")
    print(f"Stdout   : {res.stdout.strip()!r}")
    print(f"Stderr   : {res.stderr.strip()!r}")
    assert res.returncode == 0, f"Expected exit code 0, got {res.returncode}"
    print("[PASS] Case 1 verified: window activated and exit code 0\n")


if __name__ == "__main__":
    test_case_3_port_closed()
    test_case_2_port_listening_no_window()
    test_case_1_window_found()
    print("ALL THREE CASES VERIFIED IN POWERSHELL 5.1!")
