@echo off
setlocal EnableDelayedExpansion
chcp 936 >nul
title fconv - 打包便携版
cd /d "%~dp0"

set "PROJECT=%~dp0"
set "OUTDIR=%PROJECT%dist-portable"
set "DIST=%OUTDIR%\pkg\fconv"

for /f "tokens=2 delims== " %%V in ('findstr /r /c:"^version" "%PROJECT%pyproject.toml"') do set "VERSION=%%~V"
set "VERSION=%VERSION:"=%"
if "%VERSION%"=="" ( echo [错误] 无法从 pyproject.toml 读取版本号 & pause & exit /b 1 )

set "ZIPNAME=fconv-portable-v%VERSION%.zip"
set "ZIPFULL=%OUTDIR%\%ZIPNAME%"

echo [打包] 版本: %VERSION%
echo [打包] 解压后目录结构: fconv\  (根目录直接是启动入口与 src/)
echo [打包] 输出: %ZIPFULL%

if exist "%DIST%" rd /s /q "%DIST%"
if not exist "%OUTDIR%" mkdir "%OUTDIR%"
mkdir "%DIST%"

copy "%PROJECT%pyproject.toml" "%DIST%\" >nul
copy "%PROJECT%requirements.txt" "%DIST%\" >nul
copy "%PROJECT%LICENSE" "%DIST%\" >nul
xcopy "%PROJECT%src" "%DIST%\src\" /E /I /Y /Q >nul
xcopy "%PROJECT%assets" "%DIST%\assets\" /E /I /Y /Q >nul
xcopy "%PROJECT%scripts" "%DIST%\scripts\" /E /I /Y /Q >nul
rem docs\ 里是 README 引用的截图与发布说明：一起打进去，
rem 这样解压后直接读 README.md 也不会出现红叉图。
xcopy "%PROJECT%docs" "%DIST%\docs\" /E /I /Y /Q >nul

if exist "%DIST%\src\uploads" rd /s /q "%DIST%\src\uploads"
for /d /r "%DIST%" %%D in (__pycache__) do @if exist "%%D" rd /s /q "%%D"

for %%F in ("%PROJECT%*.bat") do (
    if /I not "%%~nxF"=="build-portable.bat" copy "%%F" "%DIST%\" >nul
)
for %%F in ("%PROJECT%*.vbs") do copy "%%F" "%DIST%\" >nul
for %%F in ("%PROJECT%*.md") do copy "%%F" "%DIST%\" >nul
for %%F in ("%PROJECT%*.txt") do copy "%%F" "%DIST%\" >nul

if exist "%PROJECT%python\python.exe" (
    xcopy "%PROJECT%python" "%DIST%\python\" /E /I /Y /Q >nul
    echo [打包] 已内置 python\ 便携运行时
)

if exist "%ZIPFULL%" del /q "%ZIPFULL%"
echo [打包] 正在压缩...

set "SZ="
where 7z.exe >nul 2>nul && set "SZ=7z.exe"
if not defined SZ if exist "%ProgramFiles%\7-Zip\7z.exe" set "SZ=%ProgramFiles%\7-Zip\7z.exe"
if not defined SZ if exist "%ProgramFiles(x86)%\7-Zip\7z.exe" set "SZ=%ProgramFiles(x86)%\7-Zip\7z.exe"
if defined SZ (
    "%SZ%" a -tzip -mx9 "%ZIPFULL%" "%DIST%" >nul
) else (
    powershell -NoProfile -Command "Compress-Archive -Path '%DIST%' -DestinationPath '%ZIPFULL%' -CompressionLevel Optimal -Force"
)

if exist "%ZIPFULL%" (
    for %%F in ("%ZIPFULL%") do set "ZSIZE=%%~zF"
    echo.
    echo =======================================
    echo   完成: %ZIPFULL%
    echo   大小: !ZSIZE! 字节
    echo =======================================
) else (
    echo [错误] 打包失败
)

if /I not "%~1"=="-y" pause
