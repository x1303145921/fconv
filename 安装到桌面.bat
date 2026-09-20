@echo off
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
