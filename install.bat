@echo off
setlocal enabledelayedexpansion
title Nova AI - PC Installer
cd /d "%~dp0"

echo ========================================================
echo             Nova AI - Direct PC Installer
echo ========================================================
echo.

set "DIST_EXE=%~dp0dist\NovaAI.exe"

if not exist "%DIST_EXE%" (
    echo [INFO] dist\NovaAI.exe not found. Building it first...
    call "%~dp0build_exe.bat"
    if not exist "%DIST_EXE%" (
        echo [ERROR] Could not build NovaAI.exe. Installation aborted.
        pause
        exit /b 1
    )
)

set "INSTALL_DIR=%LOCALAPPDATA%\Programs\NovaAI"
echo [1/4] Installing Nova AI to "%INSTALL_DIR%"...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

copy /y "%DIST_EXE%" "%INSTALL_DIR%\NovaAI.exe" >nul

echo [2/4] Setting up data folders...
if not exist "%INSTALL_DIR%\data" mkdir "%INSTALL_DIR%\data"
if not exist "%INSTALL_DIR%\workspace" mkdir "%INSTALL_DIR%\workspace"

if exist "%~dp0data\characters.json" (
    if not exist "%INSTALL_DIR%\data\characters.json" (
        copy "%~dp0data\characters.json" "%INSTALL_DIR%\data\characters.json" >nul
    )
)

echo [3/4] Creating Desktop and Start Menu shortcuts...
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; " ^
  "$desktop = [Environment]::GetFolderPath('Desktop'); " ^
  "$sc1 = $ws.CreateShortcut(\"$desktop\Nova AI.lnk\"); " ^
  "$sc1.TargetPath = '%INSTALL_DIR%\NovaAI.exe'; " ^
  "$sc1.WorkingDirectory = '%INSTALL_DIR%'; " ^
  "$sc1.Description = 'Nova AI Desktop Assistant'; " ^
  "$sc1.Save(); " ^
  "$startMenu = [Environment]::GetFolderPath('Programs'); " ^
  "$sc2 = $ws.CreateShortcut(\"$startMenu\Nova AI.lnk\"); " ^
  "$sc2.TargetPath = '%INSTALL_DIR%\NovaAI.exe'; " ^
  "$sc2.WorkingDirectory = '%INSTALL_DIR%'; " ^
  "$sc2.Description = 'Nova AI Desktop Assistant'; " ^
  "$sc2.Save()"

echo [4/4] Creating uninstaller...
(
echo @echo off
echo title Nova AI - Uninstaller
echo echo Uninstalling Nova AI...
echo taskkill /f /im NovaAI.exe 2^>nul
echo del "%USERPROFILE%\Desktop\Nova AI.lnk" 2^>nul
echo del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Nova AI.lnk" 2^>nul
echo rd /s /q "%INSTALL_DIR%" 2^>nul
echo echo Nova AI has been uninstalled.
echo pause
) > "%INSTALL_DIR%\uninstall.bat"

echo.
echo ========================================================
echo  [SUCCESS] Nova AI successfully installed on your PC!
echo.
echo  - Shortcuts created on Desktop and Start Menu
echo  - Installed path: %INSTALL_DIR%\NovaAI.exe
echo  - To uninstall: run %INSTALL_DIR%\uninstall.bat
echo ========================================================
echo.
set /p RUN_NOW="Do you want to launch Nova AI now? (Y/N): "
if /i "%RUN_NOW%"=="Y" (
    start "" "%INSTALL_DIR%\NovaAI.exe"
)
pause
