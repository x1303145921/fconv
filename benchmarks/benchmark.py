"""
fconv 性能基准测试。

    python benchmarks/benchmark.py            # 全量（含音视频，若本机有 FFmpeg）
    python benchmarks/benchmark.py --no-av    # 跳过音视频

产物：``benchmarks/benchmark_results.json``（已被 .gitignore 忽略，不会进仓库）。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Windows 控制台窄编码（cp1252 / cp936 等）编不出 UTF-8 中文，先统一改成 UTF-8。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):  # pragma: no cover - 非文本流时跳过
        pass

from fconv import __version__                     # noqa: E402
from fconv.batch import BatchConverter            # noqa: E402
from fconv.ffmpeg import find_ffmpeg              # noqa: E402
from fconv.router import get_router               # noqa: E402

WORK = ROOT / "benchmarks" / "_work"              # 临时工作目录，跑完即删
router = get_router()


def _line(title: str) -> None:
    print("\n" + "=" * 64)
    print(title)
    print("=" * 64)


def _run(src: Path, dst: Path) -> tuple[bool, float, str]:
    started = time.perf_counter()
    result = router.convert(src, dst)
    elapsed = (time.perf_counter() - started) * 1000
    return result.ok, elapsed, result.message


# ------------------------------------------------------------------ 图片
def bench_image() -> list[dict]:
    _line("图片转换")
    cases = [
        ("png_to_jpg_small", "png", "jpg", (100, 100)),
        ("png_to_jpg_medium", "png", "jpg", (500, 500)),
        ("png_to_jpg_large", "png", "jpg", (1920, 1080)),
        ("jpg_to_png", "jpg", "png", (800, 600)),
        ("png_to_webp", "png", "webp", (200, 200)),
        ("webp_to_png", "webp", "png", (200, 200)),
        ("gif_to_png", "gif", "png", (100, 100)),
        ("bmp_to_png", "bmp", "png", (300, 300)),
        ("png_to_ico", "png", "ico", (256, 256)),
    ]
    rows = []
    for name, src_ext, dst_ext, size in cases:
        src = WORK / f"{name}.{src_ext}"
        dst = WORK / f"{name}_out.{dst_ext}"
        palette = ["red", "blue", "green", "white", "black"]
        Image.new("RGB", size, color=palette[hash(name) % len(palette)]).save(src)
        ok, ms, msg = _run(src, dst)
        size_kb = dst.stat().st_size / 1024 if dst.exists() else 0
        print(f"  [{'OK' if ok else 'FAIL'}] {name:22s} {size[0]}x{size[1]:<5d} {ms:8.2f}ms  -> {size_kb:7.1f} KB")
        rows.append(
            {
                "name": name,
                "type": "image",
                "ok": ok,
                "duration_ms": round(ms, 2),
                "input_size": f"{size[0]}x{size[1]}",
                "output_kb": round(size_kb, 1),
                "error": None if ok else msg,
            }
        )
    return rows


# ------------------------------------------------------------------ 文本
def bench_text() -> list[dict]:
    _line("文本转换")
    big_json = json.dumps([{"id": i, "name": f"user_{i}", "value": i * 10} for i in range(2000)])
    cases = [
        ("json_to_csv_small", "json", "csv", json.dumps([{"name": f"u{i}", "v": i} for i in range(10)])),
        ("json_to_csv_large", "json", "csv", big_json),
        ("csv_to_json", "csv", "json", "name,age\nAlice,25\nBob,30\n"),
        ("html_to_txt", "html", "txt", "<html><body><h1>T</h1><p>Hello</p></body></html>"),
        ("txt_to_html", "txt", "html", "# 标题\n\n正文\n\n- 一\n- 二"),
        ("md_to_html", "md", "html", "# 标题\n\n## 小标题\n\n段落"),
        ("xml_to_json", "xml", "json", "<root><a>1</a><b>2</b></root>"),
        ("yaml_to_json", "yaml", "json", "name: Alice\nage: 25\n"),
    ]
    rows = []
    for name, src_ext, dst_ext, data in cases:
        src = WORK / f"{name}.{src_ext}"
        dst = WORK / f"{name}_out.{dst_ext}"
        src.write_text(data, encoding="utf-8")
        ok, ms, msg = _run(src, dst)
        print(f"  [{'OK' if ok else 'FAIL'}] {name:22s} {ms:8.2f}ms")
        rows.append(
            {
                "name": name,
                "type": "text",
                "ok": ok,
                "duration_ms": round(ms, 2),
                "error": None if ok else msg,
            }
        )
    return rows


# ------------------------------------------------------------------ 批量
def bench_batch() -> dict:
    _line("批量转换（并发）")
    files = []
    for i in range(24):
        path = WORK / f"batch_{i:02d}.png"
        Image.new("RGB", (400, 300), color=(i * 9 % 256, 80, 160)).save(path)
        files.append(path)

    converter = BatchConverter(max_workers=4)
    started = time.perf_counter()
    results = converter.convert(files, "jpg")
    elapsed = (time.perf_counter() - started) * 1000
    ok = sum(1 for r in results if r.ok)
    print(f"  {len(results)} 个文件：成功 {ok}，总耗时 {elapsed:.2f}ms，平均 {elapsed / len(results):.2f}ms/个")
    return {
        "total_files": len(results),
        "success_count": ok,
        "total_time_ms": round(elapsed, 2),
        "avg_time_ms": round(elapsed / len(results), 2),
        "success_rate": round(ok / len(results) * 100, 1),
    }


# ------------------------------------------------------------------ 音视频
def bench_media() -> list[dict]:
    _line("音视频转换（需 FFmpeg）")
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        print("  [SKIP] 本机没有 FFmpeg，跳过音视频基准")
        return []

    src_video = WORK / "sample.mp4"
    subprocess.run(
        [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc=size=320x240:rate=15:duration=3",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(src_video)],
        capture_output=True,
    )
    if not src_video.exists():
        print("  [SKIP] 生成测试视频失败，跳过")
        return []

    cases = [
        ("mp4_to_mkv", src_video, WORK / "sample.mkv"),
        ("mp4_to_avi", src_video, WORK / "sample.avi"),
        ("mp4_to_webm", src_video, WORK / "sample.webm"),
        ("mp4_to_gif", src_video, WORK / "sample.gif"),
    ]

    # 音频链路：先由 ffmpeg 造一段 wav，再走库里的音频转换
    src_audio = WORK / "sample.wav"
    subprocess.run(
        [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", "pcm_s16le", str(src_audio)],
        capture_output=True,
    )
    if src_audio.exists():
        cases += [
            ("wav_to_mp3", src_audio, WORK / "sample.mp3"),
            ("wav_to_flac", src_audio, WORK / "sample.flac"),
            ("wav_to_ogg", src_audio, WORK / "sample.ogg"),
        ]
    rows = []
    for name, src, dst in cases:
        ok, ms, msg = _run(src, dst)
        kb = dst.stat().st_size / 1024 if dst.exists() else 0
        print(f"  [{'OK' if ok else 'FAIL'}] {name:22s} {ms:9.2f}ms  -> {kb:8.1f} KB")
        rows.append(
            {
                "name": name,
                "type": "media",
                "ok": ok,
                "duration_ms": round(ms, 2),
                "output_kb": round(kb, 1),
                "error": None if ok else msg,
            }
        )
    return rows


# ------------------------------------------------------------------ 异常
def bench_error_handling() -> list[dict]:
    _line("异常处理")
    cases: list[tuple[str, Path, Path]] = []

    empty = WORK / "empty.txt"
    empty.write_text("", encoding="utf-8")
    cases.append(("空文件", empty, WORK / "empty_out.jpg"))

    broken = WORK / "broken.jpg"
    broken.write_bytes(b"this is not an image")
    cases.append(("损坏图片", broken, WORK / "broken_out.png"))

    unsupported = WORK / "note.txt"
    unsupported.write_text("hello", encoding="utf-8")
    cases.append(("不支持的方向", unsupported, WORK / "note_out.mp4"))

    cases.append(("文件不存在", WORK / "ghost.png", WORK / "ghost_out.jpg"))

    rows = []
    for label, src, dst in cases:
        result = router.convert(src, dst)
        handled = (not result.ok) and bool(result.message)
        print(f"  [{'OK' if handled else 'FAIL'}] {label:14s} -> {result.message[:60]}")
        rows.append(
            {
                "test": label,
                "ok": handled,
                "error_code": result.error_code.value if result.error_code else None,
                "message": result.message,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="fconv 性能基准")
    parser.add_argument("--no-av", action="store_true", help="跳过音视频基准")
    args = parser.parse_args()

    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)

    print("=" * 64)
    print(f"fconv 性能基准 v{__version__}   (Python {sys.version.split()[0]})")
    print("=" * 64)

    report = {
        "version": __version__,
        "python": sys.version.split()[0],
        "ffmpeg": find_ffmpeg(),
        "image_conversions": bench_image(),
        "text_conversions": bench_text(),
        "batch_conversion": bench_batch(),
        "media_conversions": [] if args.no_av else bench_media(),
        "error_handling": bench_error_handling(),
    }

    image_ok = sum(1 for r in report["image_conversions"] if r["ok"])
    text_ok = sum(1 for r in report["text_conversions"] if r["ok"])
    media = report["media_conversions"]
    media_ok = sum(1 for r in media if r["ok"])
    errors_ok = sum(1 for r in report["error_handling"] if r["ok"])

    report["summary"] = {
        "image": f"{image_ok}/{len(report['image_conversions'])}",
        "text": f"{text_ok}/{len(report['text_conversions'])}",
        "media": f"{media_ok}/{len(media)}" if media else "skipped",
        "batch": report["batch_conversion"]["success_rate"],
        "error_handling": f"{errors_ok}/{len(report['error_handling'])}",
    }

    _line("汇总")
    for key, value in report["summary"].items():
        print(f"  {key:14s} {value}")

    out = ROOT / "benchmarks" / "benchmark_results.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已写入 {out}")

    shutil.rmtree(WORK, ignore_errors=True)

    all_ok = (
        image_ok == len(report["image_conversions"])
        and text_ok == len(report["text_conversions"])
        and errors_ok == len(report["error_handling"])
        and (not media or media_ok == len(media))
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
