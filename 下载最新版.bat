@echo off
chcp 936 >nul
title fconv - 下载最新版
cd /d "%~dp0"

rem ============================================
rem 版本号自动从 pyproject.toml 读取（与 build-portable.bat 同一口径）：
rem 发布新版本时只改 pyproject.toml，本脚本不用再手改。
rem 想临时指定版本：先 set FCONV_VER=1.2.3 再运行本脚本。
rem 注意：下面刻意不用括号块 —— 批处理会在解析整块时就展开 %VER%，
rem       块内的赋值会被提前展开成空值（踩过的坑）。
rem
rem 下载顺序：直连 GitHub 优先（官方源、不经第三方）；
rem          直连不通才依次落到加速镜像兜底。
rem          镜像属第三方代理转发，拿到文件后建议核对 SHA256
rem          （Release 说明末尾给出，命令见文末提示）。
rem ============================================
set "VER="
if defined FCONV_VER set "VER=%FCONV_VER%"
if not defined VER for /f "tokens=2 delims== " %%V in ('findstr /r /c:"^version" "%~dp0pyproject.toml"') do set "VER=%%~V"
set "VER=%VER:"=%"
if "%VER%"=="" goto :no_version

set "FILE=fconv-portable-v%VER%.zip"
set "GHURL=https://github.com/x1303145921/fconv/releases/download/v%VER%/%FILE%"

echo ============================================
echo   fconv 文件格式转换工具 便携版 v%VER% 下载器
echo ============================================
echo 目标文件: %FILE%
echo.

rem 先清掉同名旧包，避免「上一次的包还在 → 误判本次下载成功」
if exist "%FILE%" del /q "%FILE%"

echo [1/3] 正在直连 GitHub 下载（官方源）...
curl.exe -f -L --ssl-no-revoke --connect-timeout 10 --max-time 300 -o "%FILE%" "%GHURL%"
if not exist "%FILE%" (
    echo [2/3] 直连不可用，改用加速镜像1（ghfast.top，第三方代理）...
    curl.exe -f -L --ssl-no-revoke --connect-timeout 10 --max-time 300 -o "%FILE%" "https://ghfast.top/%GHURL%"
)
if not exist "%FILE%" (
    echo [3/3] 镜像1也不可用，改用加速镜像2（gh-proxy.com，第三方代理）...
    curl.exe -f -L --ssl-no-revoke --connect-timeout 10 --max-time 300 -o "%FILE%" "https://gh-proxy.com/%GHURL%"
)
if not exist "%FILE%" (
    echo.
    echo [错误] 下载失败，请检查网络后重试；
    echo        或手动打开 Releases 页面下载：
    echo        https://github.com/x1303145921/fconv/releases/latest
    pause
    exit /b 1
)

for %%F in ("%FILE%") do (
    echo.
    echo 下载完成: %FILE%  （%%~zF 字节）
)
echo.
echo 校验（可选但建议，尤其经镜像下载时）：
echo        certutil -hashfile "%FILE%" SHA256
echo        与 Release 说明末尾给出的 SHA256 比对一致即可。
echo.
echo 下一步：右键压缩包 →「全部解压缩」→ 双击「启动fconv.vbs」即用。
echo        （可选）再双击「安装到桌面.bat」创建桌面/开始菜单快捷方式。
pause
exit /b 0

:no_version
echo.
echo [错误] 无法从 pyproject.toml 读取版本号。
echo        请确认本脚本与 pyproject.toml 在同一目录；或先执行：
echo            set FCONV_VER=1.0.0
echo        再运行本脚本。
pause
exit /b 1
