@echo off
title Nova AI
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

set "PY_CMD="
where python >nul 2>nul
if %errorlevel%==0 set "PY_CMD=python"
if not defined PY_CMD (
  where py >nul 2>nul
  if %errorlevel%==0 set "PY_CMD=py"
)

if not defined PY_CMD (
  echo Python 3.10+ is required. Install it from https://www.python.org/downloads/ ^(tick "Add Python to PATH"^).
  pause
  exit /b 1
)

:: Verify Python version is 3.10+
%PY_CMD% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if %errorlevel% neq 0 (
  echo [ERROR] Nova AI requires Python 3.10 or higher.
  echo Your current Python version is unsupported.
  echo Please install Python 3.10+ from https://www.python.org/downloads/
  pause
  exit /b 1
)

%PY_CMD% server.py
if %errorlevel% neq 0 pause
