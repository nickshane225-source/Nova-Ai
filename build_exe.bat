@echo off
title Nova AI - Build All Executables
cd /d "%~dp0"
echo ========================================================
echo             Building Nova AI Single-File Installer
echo ========================================================
echo.

where pyinstaller >nul 2>nul
if %errorlevel% neq 0 (
    echo [INFO] PyInstaller not detected. Installing PyInstaller...
    pip install pyinstaller
)

echo [1/2] Building Core Application (NovaAI.exe) without terminal window...
pyinstaller --noconfirm --clean --onefile --windowed --name "NovaAI" ^
  --add-data "web;web" ^
  --add-data "data/characters.json;data" ^
  --hidden-import "nova_browser" ^
  --hidden-import "memory_engine" ^
  --hidden-import "scheduler_engine" ^
  server.py

if %errorlevel% neq 0 (
    echo [ERROR] Failed to build core NovaAI.exe.
    pause
    exit /b 1
)

echo.
echo [2/2] Building Standalone PC Installer (NovaAI-Setup.exe)...
pyinstaller --noconfirm --clean --onefile --windowed --name "NovaAI-Setup" ^
  --add-data "dist/NovaAI.exe;." ^
  --add-data "data/characters.json;." ^
  installer_wizard.py

if %errorlevel% equ 0 (
    echo.
    echo ========================================================
    echo  [SUCCESS] All-In-One Setup EXE Created!
    echo.
    echo  Installer File: dist\NovaAI-Setup.exe
    echo  (You can copy this SINGLE file to any PC to install it!)
    echo ========================================================
    echo.
) else (
    echo [ERROR] Failed to build NovaAI-Setup.exe.
)
pause
