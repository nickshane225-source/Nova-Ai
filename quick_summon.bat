@echo off
:: Nova AI Quick Summon Launcher
:: Only focus an existing Nova window; if port 8765 is listening but no window found,
:: show a message "Nova is running - use the open tab or restart Nova"; if the port is not listening, start run.bat.
powershell -NoProfile -Command "$w = (Get-Process | Where-Object { $_.MainWindowTitle -match 'Nova AI' -or $_.MainWindowTitle -match '127.0.0.1:8765' -or ($env:NOVA_TEST_WINDOW_PID -and $_.Id -eq [int]$env:NOVA_TEST_WINDOW_PID) } | Select-Object -First 1); if ($w) { [void](New-Object -ComObject WScript.Shell).AppActivate($w.Id); exit 0 }; $listening = [bool](Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue); if ($listening) { Write-Host 'Nova is running - use the open tab or restart Nova'; exit 1 } else { exit 2 }"
set PS_CODE=%errorlevel%
if %PS_CODE% equ 2 (
    if not defined NOVA_TEST_NO_START start "" "%~dp0run.bat"
)
exit /b %PS_CODE%
