@echo off
setlocal EnableDelayedExpansion
chcp 936 >nul
title fconv 文件格式转换工具（调试窗口）
cd /d "%~dp0"

set "PY_BIN=python"
if exist "%~dp0python\python.exe" set "PY_BIN=%~dp0python\python.exe"

"%PY_BIN%" --version >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10 及以上版本。
    echo        下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

"%PY_BIN%" -c "import flask, PIL, pypdf" >nul 2>nul
if errorlevel 1 (
    echo [提示] 检测到缺少运行依赖，正在自动安装（需要联网）...
    "%PY_BIN%" -m pip install -r "%~dp0requirements.txt"
)

netstat -ano | findstr ":8765.*LISTENING" >nul 2>nul
if not errorlevel 1 (
    curl -s --noproxy "*" -m 3 http://127.0.0.1:8765/api/health >nul 2>nul
    if not errorlevel 1 goto open_browser
    echo [提示] 端口被占用但服务无响应，正在清理...
    for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8765.*LISTENING"') do taskkill /F /PID %%p >nul 2>nul
    ping -n 2 127.0.0.1 >nul
)

start "fconv 服务"  cmd /c ""%PY_BIN%" "%~dp0src\web\server.py""

set /a count=0
:wait
ping -n 2 127.0.0.1 >nul
curl -s --noproxy "*" -m 3 http://127.0.0.1:8765/api/health >nul 2>nul
if errorlevel 1 (
    set /a count+=1
    if !count! gtr 30 (
        echo [错误] 服务启动超时，请检查上方窗口的报错信息。
        pause
        exit /b 1
    )
    goto wait
)

:open_browser
powershell -NoProfile -Command "Start-Process 'http://127.0.0.1:8765'"
echo 
echo [就绪] fconv 已启动: http://127.0.0.1:8765
echo 服务运行在另一个窗口中，关闭那个窗口即停止服务。
pause
