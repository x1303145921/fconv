"""
fconv 启动器生成器（.bat 部分）

生成与「音频提取器 / 随机密码生成器」同款的批处理入口。
VBS 启动器不在这里生成 —— 见 scripts/_vbs_tpl.txt + scripts/build_vbs.py
（VBS 内含 COM 对象名，单独放在模板里便于受控生成）。

用法： python scripts/make_launchers.py
      python scripts/fix_encoding.py      # 统一转 GBK + CRLF
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = "8765"

HEAD = r"""@echo off
setlocal EnableDelayedExpansion
chcp 936 >nul
title @TITLE@
cd /d "%~dp0"

set "PY_BIN=python"
if exist "%~dp0python\python.exe" set "PY_BIN=%~dp0python\python.exe"

"%PY_BIN%" --version >nul 2>nul
if errorlevel 1 (
    echo @ERR_NO_PYTHON@
    pause
    exit /b 1
)

"%PY_BIN%" -c "import flask, PIL, pypdf" >nul 2>nul
if errorlevel 1 (
    echo @ERR_NO_DEPS@
    "%PY_BIN%" -m pip install -r "%~dp0requirements.txt"
)

netstat -ano | findstr ":@PORT@.*LISTENING" >nul 2>nul
if not errorlevel 1 (
    curl -s --noproxy "*" -m 3 http://127.0.0.1:@PORT@/api/health >nul 2>nul
    if not errorlevel 1 goto open_browser
    echo @ERR_PORT_BUSY@
    for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":@PORT@.*LISTENING"') do taskkill /F /PID %%p >nul 2>nul
    ping -n 2 127.0.0.1 >nul
)

start "fconv 服务" @WINMODE@ cmd /c ""%PY_BIN%" "%~dp0src\web\server.py""

set /a count=0
:wait
ping -n 2 127.0.0.1 >nul
curl -s --noproxy "*" -m 3 http://127.0.0.1:@PORT@/api/health >nul 2>nul
if errorlevel 1 (
    set /a count+=1
    if !count! gtr 30 (
        echo @ERR_TIMEOUT@
        pause
        exit /b 1
    )
    goto wait
)

:open_browser
powershell -NoProfile -Command "Start-Process 'http://127.0.0.1:@PORT@'"
echo @OK_MSG@
@TAIL@
"""

TAIL_CONSOLE = "echo 服务运行在另一个窗口中，关闭那个窗口即停止服务。\npause"
TAIL_MIN = "echo 服务在后台最小化运行；要停止请双击「停止fconv.bat」。"
TAIL_EN = "echo Run the stop script to stop the service."

STOP = r"""@echo off
setlocal EnableDelayedExpansion
chcp 936 >nul
title 停止 fconv 服务
cd /d "%~dp0"

set "FOUND=0"
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":@PORT@.*LISTENING"') do (
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
"""

INSTALL = r"""@echo off
setlocal EnableDelayedExpansion
chcp 936 >nul
title 安装到桌面 - fconv
cd /d "%~dp0"

if not exist "src\web\server.py" goto :missing
if not exist "启动fconv.vbs" goto :missing
if not exist "assets\icon.ico" goto :missing

set "PWD_DIR=%~dp0"
set "PWD_DIR=%PWD_DIR:~0,-1%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $name='fconv 文件格式转换.lnk'; $target=(Join-Path $env:PWD_DIR '启动fconv.vbs'); $icon=(Join-Path $env:PWD_DIR 'assets\icon.ico')+',0'; $sh=New-Object -ComObject WScript.Shell; foreach($d in @([Environment]::GetFolderPath('Desktop'), (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'))){ if(-not (Test-Path $d)){ continue }; $lnk=Join-Path $d $name; if(Test-Path $lnk){ Remove-Item $lnk -Force }; $s=$sh.CreateShortcut($lnk); $s.TargetPath=$target; $s.WorkingDirectory=$env:PWD_DIR; $s.IconLocation=$icon; $s.Description='fconv 文件格式转换工具 - 双击使用'; $s.Save(); Write-Output ('  [ok] ' + $lnk) }"
if errorlevel 1 goto :fail
set "PWD_DIR="

echo.
echo  安装完成：桌面与开始菜单都已生成「fconv 文件格式转换」快捷方式，双击即可使用。
echo  提示：快捷方式失效时删除重建即可，不影响程序本体；卸载时删掉这两个快捷方式即可。
pause
exit /b 0

:missing
echo  缺少必要文件，请确认本脚本位于解压目录（与 src 文件夹同级）。
pause
exit /b 1

:fail
echo  创建快捷方式失败，可尝试：右键「启动fconv.vbs」→ 发送到 → 桌面快捷方式。
pause
exit /b 1
"""

# 下载器：版本号自动从 pyproject.toml 读，发布新版本时不用再手改本文件。
DOWNLOAD = r"""@echo off
chcp 936 >nul
title fconv - 下载最新版
cd /d "%~dp0"

rem ============================================
rem 版本号自动从 pyproject.toml 读取（与 build-portable.bat 同一口径）：
rem 发布新版本时只改 pyproject.toml，本脚本不用再手改。
rem 想临时指定版本：先 set FCONV_VER=1.2.3 再运行本脚本。
rem 注意：下面刻意不用括号块 —— 批处理会在解析整块时就展开 %VER%，
rem       块内的赋值会被提前展开成空值（踩过的坑）。
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

echo [1/3] 正在从镜像1（ghfast.top）下载...
curl.exe -f -L --ssl-no-revoke --connect-timeout 10 --max-time 300 -o "%FILE%" "https://ghfast.top/%GHURL%"
if not exist "%FILE%" (
    echo [2/3] 镜像1不可用，改用镜像2（gh-proxy.com）...
    curl.exe -f -L --ssl-no-revoke --connect-timeout 10 --max-time 300 -o "%FILE%" "https://gh-proxy.com/%GHURL%"
)
if not exist "%FILE%" (
    echo [3/3] 镜像2也不可用，尝试直连 GitHub（网络好或开加速器时可用）...
    curl.exe -f -L --ssl-no-revoke --connect-timeout 10 --max-time 300 -o "%FILE%" "%GHURL%"
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
"""

VARIANTS = {
    "启动fconv.bat": dict(
        TITLE="fconv 文件格式转换工具（调试窗口）",
        WINMODE="",
        ERR_NO_PYTHON="[错误] 未检测到 Python，请先安装 Python 3.10 及以上版本。\n    echo        下载地址: https://www.python.org/downloads/",
        ERR_NO_DEPS="[提示] 检测到缺少运行依赖，正在自动安装（需要联网）...",
        ERR_PORT_BUSY="[提示] 端口被占用但服务无响应，正在清理...",
        ERR_TIMEOUT="[错误] 服务启动超时，请检查上方窗口的报错信息。",
        OK_MSG="\necho [就绪] fconv 已启动: http://127.0.0.1:%s" % PORT,
        TAIL=TAIL_CONSOLE,
    ),
    "启动fconv-最小化.bat": dict(
        TITLE="fconv 文件格式转换工具",
        WINMODE="/min",
        ERR_NO_PYTHON="[错误] 未检测到 Python，请先安装 Python 3.10 及以上版本。\n    echo        下载地址: https://www.python.org/downloads/",
        ERR_NO_DEPS="[提示] 检测到缺少运行依赖，正在自动安装（需要联网）...",
        ERR_PORT_BUSY="[提示] 端口被占用但服务无响应，正在清理...",
        ERR_TIMEOUT="[错误] 服务启动超时。请双击「启动fconv.bat」查看详细报错。",
        OK_MSG="[就绪] fconv 已启动: http://127.0.0.1:%s" % PORT,
        TAIL=TAIL_MIN,
    ),
    "start.bat": dict(
        TITLE="fconv - File Format Converter",
        WINMODE="/min",
        ERR_NO_PYTHON="[ERROR] Python not found. Please install Python 3.10 or newer.",
        ERR_NO_DEPS="[INFO] Installing missing dependencies...",
        ERR_PORT_BUSY="[INFO] Port busy, clearing stale process...",
        ERR_TIMEOUT="[ERROR] Server startup timed out.",
        OK_MSG="[OK] fconv is running at http://127.0.0.1:%s" % PORT,
        TAIL=TAIL_EN,
    ),
}


def build(name: str, cfg: dict) -> str:
    text = HEAD
    for key, val in cfg.items():
        if key == "TAIL":
            continue
        text = text.replace("@" + key + "@", val)
    text = text.replace("@TAIL@", cfg["TAIL"])
    text = text.replace("@PORT@", PORT)
    return text.replace("\n", "\r\n")


def main() -> int:
    print("生成 fconv 批处理入口（GBK · CRLF）")
    for name, cfg in VARIANTS.items():
        (ROOT / name).write_bytes(build(name, cfg).encode("gbk"))
        print(f"  [ok] {name}")

    (ROOT / "停止fconv.bat").write_bytes(
        STOP.replace("@PORT@", PORT).replace("\n", "\r\n").encode("gbk")
    )
    print("  [ok] 停止fconv.bat")

    (ROOT / "安装到桌面.bat").write_bytes(
        INSTALL.replace("\n", "\r\n").encode("gbk")
    )
    print("  [ok] 安装到桌面.bat")

    (ROOT / "下载最新版.bat").write_bytes(
        DOWNLOAD.replace("\n", "\r\n").encode("gbk")
    )
    print("  [ok] 下载最新版.bat（版本号运行时从 pyproject.toml 读取）")

    print("完成。VBS 请另跑 scripts/build_vbs.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
