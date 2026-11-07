@echo off
:: Nova AI Quick Summon Launcher
:: Brings existing Nova AI window to the front or launches it if not open
powershell -NoProfile -Command "$w = (Get-Process | Where-Object { $_.MainWindowTitle -match 'Nova AI' -or $_.MainWindowTitle -match '127.0.0.1:8765' } | Select-Object -First 1); if ($w) { $sig = '[DllImport(\"user32.dll\")] public static extern bool SetForegroundWindow(IntPtr hWnd); [DllImport(\"user32.dll\")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);'; $type = Add-Type -MemberDefinition $sig -Name Win32Utils -Namespace Win32 -PassThru; $type::ShowWindow($w.MainWindowHandle, 9); $type::SetForegroundWindow($w.MainWindowHandle) } else { Start-Process 'http://127.0.0.1:8765' }"
