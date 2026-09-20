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
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $lnk=Join-Path $d 'fconv 文件格式转换.lnk'; if(Test-Path $lnk){Remove-Item $lnk -Force}; $s=(New-Object -ComObject WScript.Shell).CreateShortcut($lnk); $s.TargetPath=(Join-Path $env:PWD_DIR '启动fconv.vbs'); $s.WorkingDirectory=$env:PWD_DIR; $s.IconLocation=(Join-Path $env:PWD_DIR 'assets\icon.ico')+',0'; $s.Description='fconv 文件格式转换工具 - 双击使用'; $s.Save()"
if errorlevel 1 goto :fail
set "PWD_DIR="

echo.
echo  安装完成，桌面已出现「fconv 文件格式转换」图标，双击即可使用。
echo  提示：图标失效时删除重建即可，不影响本体。
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

    print("完成。VBS 请另跑 scripts/build_vbs.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
