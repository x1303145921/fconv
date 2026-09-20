@echo off
setlocal EnableDelayedExpansion
chcp 936 >nul
title 停止 fconv 服务
cd /d "%~dp0"

set "FOUND=0"
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8765.*LISTENING"') do (
    taskkill /F /PID %%p >nul 2>nul
    if not errorlevel 1 set "FOUND=1"
)

echo.
if "!FOUND!"=="1" (
    echo   fconv 服务已停止。
) else (
    echo   未发现正在运行的 fconv 服务。
)
echo.
pause
