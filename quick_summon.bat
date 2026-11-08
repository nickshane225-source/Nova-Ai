@echo off
:: Nova AI Quick Summon Launcher
:: Only focus an existing Nova window; if port 8765 is listening but no window found,
:: show a message "Nova is running - use the open tab or restart Nova"; if the port is not listening, start run.bat.
powershell -NoProfile -Command "$w = (Get-Process | Where-Object { $_.MainWindowTitle -match 'Nova AI' -or $_.MainWindowTitle -match '127.0.0.1:8765' } | Select-Object -First 1); if ($w) { $sig = '[DllImport(\"user32.dll\")] public static extern bool SetForegroundWindow(IntPtr hWnd); [DllImport(\"user32.dll\")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);'; $type = Add-Type -MemberDefinition $sig -Name Win32Utils -Namespace Win32 -PassThru; $type::ShowWindow($w.MainWindowHandle, 9); $type::SetForegroundWindow($w.MainWindowHandle); exit 0 }; $listening = [bool](Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue); if ($listening) { Write-Host 'Nova is running - use the open tab or restart Nova'; exit 1 } else { exit 2 }"
if %errorlevel% equ 2 (
    start "" "%~dp0run.bat"
)
