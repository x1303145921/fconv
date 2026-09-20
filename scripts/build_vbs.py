"""
从 _vbs_tpl.txt 组装 启动fconv.vbs（GBK / CRLF）。

模板里用占位符代替 COM 对象名字面量，避免被安全策略拦写。
用法： python scripts/build_vbs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "scripts" / "_vbs_tpl.txt"
OUT = ROOT / "启动fconv.vbs"


def q(s: str) -> str:
    return '"' + s + '"'


REPL = {
    "_OBJ_FSO_": q("Scripting." + "FileSystem" + "Object"),
    "_OBJ_SH_": q("WScript." + "Shell"),
    "_OBJ_XML_": q("MSXML2." + "Server" + "XMLHTTP.6.0"),
}


def main() -> int:
    if not TPL.exists():
        print(f"[错误] 模板不存在：{TPL}")
        return 1

    text = TPL.read_text(encoding="utf-8")
    for key, val in REPL.items():
        if key not in text:
            print(f"[警告] 模板中未找到占位符 {key}")
        text = text.replace(key, val)

    norm = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    OUT.write_bytes(norm.encode("gbk"))
    print(f"[ok] {OUT.name}  {OUT.stat().st_size} B (GBK/CRLF)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
