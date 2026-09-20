"""
把启动器文本文件统一转成 GBK（代码页 936）+ CRLF。

Windows 批处理里的中文在 cmd.exe 下按 OEM 代码页解析，
脚本写成 UTF-8 会显示成乱码，因此统一 GBK。
VBScript 中文同样必须 GBK，否则报「无效字符」。

用法： python scripts/fix_encoding.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TARGETS = [
    "启动fconv.bat",
    "启动fconv-最小化.bat",
    "启动fconv.vbs",
    "停止fconv.bat",
    "安装到桌面.bat",
    "下载最新版.bat",
    "build-portable.bat",
    "start.bat",
    "README.txt",
]


def main() -> int:
    bad = 0
    for name in TARGETS:
        p = ROOT / name
        if not p.exists():
            print(f"  [skip] {name}（不存在）")
            continue
        raw = p.read_bytes()
        # 已是 GBK 就不再动
        try:
            text = raw.decode("gbk")
            already = True
        except UnicodeDecodeError:
            text = raw.decode("utf-8-sig")
            already = False

        norm = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
        out = norm.encode("gbk")
        if already and out == raw:
            print(f"  [ok ] {name}（已是 GBK）")
            continue
        p.write_bytes(out)
        print(f"  [fix] {name}  -> GBK/CRLF  {len(out)} B")
        bad += 0
    print("完成。")
    return bad


if __name__ == "__main__":
    sys.exit(main())
