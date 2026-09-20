"""
fconv 命令行界面。

用法示例::

    fconv input.jpg output.png
    fconv convert input.mp4 output.mkv --crf 20
    fconv batch *.png --format webp -o out/
    fconv formats          # 看支持的格式对
    fconv detect 某文件.bin # 看真实格式
    fconv version

> 输出一律用 ASCII 标记（[OK] / [FAIL]），避免 Windows 控制台 GBK 编码把 emoji 打崩。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .router import get_router
from .sniffer import get_sniffer

# Windows 控制台（cp1252 / cp936 等）默认编不出 UTF-8 中文（GitHub Actions 的
# windows-latest 实测踩到 UnicodeEncodeError）。先把输出流改成 UTF-8，再干活。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):  # pragma: no cover - 非文本流时跳过
        pass

OK_MARK = "[OK]"
FAIL_MARK = "[FAIL]"


# ------------------------------------------------------------------ 子命令
def cmd_convert(args: argparse.Namespace) -> int:
    src = Path(args.input)
    dst = Path(args.output)
    if not src.exists():
        print(f"{FAIL_MARK} 源文件不存在：{src}")
        return 1

    router = get_router()
    options: dict[str, object] = {}
    if args.quality is not None:
        options["quality"] = args.quality
    if args.crf is not None:
        options["crf"] = args.crf
    if args.bitrate is not None:
        options["bitrate"] = args.bitrate

    result = router.convert(
        src, dst, src_format=args.format, dst_format=args.out_format, **options
    )

    if result.ok:
        size = result.output_path.stat().st_size if result.output_path else 0
        print(f"{OK_MARK} 转换成功：{result.output_path}（{_human(size)}）")
        print(f"       耗时 {result.duration:.2f} 秒")
        return 0

    print(f"{FAIL_MARK} 转换失败：{result.message}")
    if result.error_code is not None:
        print(f"       错误码：{result.error_code.value}")
    return 2


def cmd_formats(args: argparse.Namespace) -> int:
    formats = get_router().get_supported_formats()
    print(f"fconv {__version__} 支持的输入格式（共 {len(formats)} 种）:")
    for fmt in sorted(formats):
        targets = formats[fmt]
        head = ", ".join(targets[:8])
        more = f" (+{len(targets) - 8})" if len(targets) > 8 else ""
        print(f"  {fmt:>5s} -> {head}{more}")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    print(get_router().get_format_info())
    return 0


def cmd_detect(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"{FAIL_MARK} 文件不存在：{path}")
        return 1
    fmt = get_sniffer().detect(path)
    if not fmt:
        print(f"{FAIL_MARK} 无法识别文件格式（可能为空文件或未知类型）")
        return 1
    size = path.stat().st_size
    print(f"{OK_MARK} 真实格式：{fmt}")
    print(f"       文件大小：{size:,} 字节（{_human(size)}）")
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    from .batch import BatchConverter

    files = [Path(p) for p in args.inputs]
    out_dir = Path(args.output_dir) if args.output_dir else None

    converter = BatchConverter(max_workers=args.workers)
    last = {"line": ""}

    def progress(done: int, total: int) -> None:
        last["line"] = f"\r进度 {done}/{total} ({done * 100 // total}%)"
        print(last["line"], end="", flush=True)

    results = converter.convert(
        files, args.format, progress_callback=progress, output_dir=out_dir
    )
    if last["line"]:
        print()

    for item in results:
        if item.ok:
            print(f"  {OK_MARK} {item.input_path.name} -> {item.output_path.name}")
        else:
            print(f"  {FAIL_MARK} {item.input_path.name}：{item.error_message}")

    success = sum(1 for item in results if item.ok)
    print(f"\n完成：{success}/{len(results)} 个文件转换成功")
    return 0 if success == len(results) else 1


# ------------------------------------------------------------------ 入口
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fconv",
        description="fconv - 本地文件格式转换工具（图片 / 文档 / 视频 / 音频 / PDF）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  fconv input.jpg output.png
  fconv convert input.mp4 output.mkv --crf 20
  fconv batch *.png --format webp -o out/
  fconv formats
  fconv detect 某文件.bin
  fconv version
""",
    )
    parser.add_argument("--version", action="version", version=f"fconv {__version__}")
    sub = parser.add_subparsers(dest="command", help="子命令")

    p_convert = sub.add_parser("convert", aliases=["c"], help="转换单个文件")
    p_convert.add_argument("input", help="输入文件路径")
    p_convert.add_argument("output", help="输出文件路径")
    p_convert.add_argument("--format", help="指定输入格式（默认自动检测）")
    p_convert.add_argument("--out-format", help="指定输出格式（默认取输出扩展名）")
    p_convert.add_argument("--quality", "-q", type=int, help="图片质量 1-100")
    p_convert.add_argument("--crf", type=int, help="视频质量 1-51（越小越清晰）")
    p_convert.add_argument("--bitrate", "-b", type=int, help="音频比特率 kbps")

    sub.add_parser("formats", aliases=["f"], help="列出支持的格式")
    sub.add_parser("info", help="显示完整格式路由表")

    p_detect = sub.add_parser("detect", aliases=["d"], help="检测文件真实格式")
    p_detect.add_argument("file", help="要检测的文件")

    sub.add_parser("version", aliases=["v"], help="显示版本")

    p_batch = sub.add_parser("batch", aliases=["b"], help="批量转换")
    p_batch.add_argument("inputs", nargs="+", help="输入文件列表")
    p_batch.add_argument("--format", "-f", help="目标格式")
    p_batch.add_argument("--output-dir", "-o", help="输出目录（默认与源文件同目录）")
    p_batch.add_argument("--workers", type=int, default=4, help="并发线程数（1-16）")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        # 支持 `fconv a.png b.jpg` 这种省略子命令的写法
        argv = list(sys.argv[1:] if argv is None else argv)
        if len(argv) == 2 and not argv[0].startswith("-"):
            args = parser.parse_args(["convert", *argv])
        else:
            parser.print_help()
            return 0

    command = args.command
    if command in ("version", "v"):
        print(f"fconv {__version__}")
        return 0
    if command in ("formats", "f"):
        return cmd_formats(args)
    if command == "info":
        return cmd_info(args)
    if command in ("detect", "d"):
        return cmd_detect(args)
    if command in ("convert", "c"):
        return cmd_convert(args)
    if command in ("batch", "b"):
        return cmd_batch(args)

    parser.print_help()
    return 0


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"


if __name__ == "__main__":
    sys.exit(main())
