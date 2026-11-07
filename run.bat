@echo off
title Nova AI
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
  python server.py
  if %errorlevel% neq 0 pause
) else (
  where py >nul 2>nul
  if %errorlevel%==0 (
    py server.py
    if %errorlevel% neq 0 pause
  ) else (
    echo Python 3.8+ is required. Install it from https://www.python.org/downloads/ ^(tick "Add Python to PATH"^).
    pause
  )
)
