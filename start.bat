@echo off
setlocal EnableDelayedExpansion
chcp 936 >nul
title fconv - File Format Converter
cd /d "%~dp0"

set "PY_BIN=python"
if exist "%~dp0python\python.exe" set "PY_BIN=%~dp0python\python.exe"

"%PY_BIN%" --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10 or newer.
    pause
    exit /b 1
)

"%PY_BIN%" -c "import flask, PIL, pypdf" >nul 2>nul
if errorlevel 1 (
    echo [INFO] Installing missing dependencies...
    "%PY_BIN%" -m pip install -r "%~dp0requirements.txt"
)

netstat -ano | findstr ":8765.*LISTENING" >nul 2>nul
if not errorlevel 1 (
    curl -s --noproxy "*" -m 3 http://127.0.0.1:8765/api/health >nul 2>nul
    if not errorlevel 1 goto open_browser
    echo [INFO] Port busy, clearing stale process...
    for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8765.*LISTENING"') do taskkill /F /PID %%p >nul 2>nul
    ping -n 2 127.0.0.1 >nul
)

start "fconv ·þÎñ" /min cmd /c ""%PY_BIN%" "%~dp0src\web\server.py""

set /a count=0
:wait
ping -n 2 127.0.0.1 >nul
curl -s --noproxy "*" -m 3 http://127.0.0.1:8765/api/health >nul 2>nul
if errorlevel 1 (
    set /a count+=1
    if !count! gtr 30 (
        echo [ERROR] Server startup timed out.
        pause
        exit /b 1
    )
    goto wait
)

:open_browser
powershell -NoProfile -Command "Start-Process 'http://127.0.0.1:8765'"
echo [OK] fconv is running at http://127.0.0.1:8765
echo Run the stop script to stop the service.
