#!/usr/bin/env python3
"""fconv 命令行入口（源码目录直接运行用）。

用法:
    python run.py formats
    python run.py detect 示例.png
    python run.py 输入.png 输出.jpg
    python run.py batch 图片1.png 图片2.png --format webp -o 输出目录
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fconv.cli import main

if __name__ == "__main__":
    sys.exit(main())
