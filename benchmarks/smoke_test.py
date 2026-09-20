"""
全格式矩阵冒烟测试：把「声明支持的每个格式对」真的跑一遍。

    python benchmarks/smoke_test.py                 # 只跑不需要 FFmpeg 的部分
    python benchmarks/smoke_test.py --with-ffmpeg   # 音视频也跑（需本机 FFmpeg）

输出：逐条 PASS/FAIL，最后汇总；退出码 0 表示全过。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from fconv import __version__                  # noqa: E402
from fconv.ffmpeg import find_ffmpeg           # noqa: E402
from fconv.router import get_router            # noqa: E402
from fconv.sniffer import get_sniffer          # noqa: E402

WORK = ROOT / "benchmarks" / "_smoke"
router = get_router()
sniffer = get_sniffer()


def make_fixture(fmt: str, path: Path) -> bool:
    """按格式造一个最小可用的样本文件。"""
    if fmt in ("png", "jpg", "gif", "bmp", "tif", "webp", "ico"):
        Image.new("RGB", (64, 48), (30, 120, 200)).save(path)
        return True
    if fmt == "txt":
        path.write_text("示例文本\n第二行", encoding="utf-8")
        return True
    if fmt == "md":
        path.write_text("# 标题\n\n- 一\n- 二", encoding="utf-8")
        return True
    if fmt == "html":
        path.write_text("<html><body><h1>标题</h1><p>正文</p></body></html>", encoding="utf-8")
        return True
    if fmt == "json":
        path.write_text(json.dumps([{"name": "Alice", "age": 25}]), encoding="utf-8")
        return True
    if fmt == "csv":
        path.write_text("name,age\r\nAlice,25\r\n", encoding="utf-8")
        return True
    if fmt == "xml":
        path.write_text("<root><a>1</a><b>2</b></root>", encoding="utf-8")
        return True
    if fmt == "yaml":
        path.write_text("name: Alice\nage: 25\n", encoding="utf-8")
        return True
    if fmt == "pdf":
        try:
            from pypdf import PdfWriter
        except ImportError:
            return False
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        with open(path, "wb") as fh:
            writer.write(fh)
        return True
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return False
    if fmt in ("mp4", "mkv", "avi", "mov", "webm", "flv", "wmv"):
        cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
               "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=1",
               "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path)]
        if fmt == "flv":
            cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                   "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=1",
                   "-c:v", "flv", "-f", "flv", str(path)]
        if fmt in ("webm", "mkv"):
            cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                   "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=1",
                   "-c:v", "libvpx-vp9", "-b:v", "200k", str(path)]
        return subprocess.run(cmd, capture_output=True).returncode == 0
    if fmt in ("mp3", "wav", "ogg", "flac", "aac", "m4a", "wma"):
        codec = {"mp3": "libmp3lame", "wav": "pcm_s16le", "ogg": "libvorbis",
                 "flac": "flac", "aac": "aac", "m4a": "aac", "wma": "wmav2"}[fmt]
        cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
               "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", codec, str(path)]
        return subprocess.run(cmd, capture_output=True).returncode == 0
    return False


def verify_output(dst: Path) -> tuple[bool, str]:
    """产物必须真实存在且不是坏文件。"""
    if dst.suffix == ".zip" or dst.suffix == "":
        if not dst.exists() or dst.stat().st_size == 0:
            return False, "空产物"
        if dst.suffix == ".zip":
            try:
                with zipfile.ZipFile(dst) as archive:
                    if not archive.namelist():
                        return False, "ZIP 为空"
            except Exception as exc:  # noqa: BLE001
                return False, f"ZIP 坏了：{exc}"
        return True, f"{dst.stat().st_size}B"
    if not dst.exists() or dst.stat().st_size == 0:
        return False, "空产物"

    fmt = dst.suffix.lstrip(".").lower()
    if fmt in ("png", "jpg", "gif", "bmp", "tif", "webp", "ico"):
        try:
            with Image.open(dst) as img:
                img.load()
                return True, f"{img.size[0]}x{img.size[1]}"
        except Exception as exc:  # noqa: BLE001
            return False, f"打不开：{exc}"
    if fmt == "json":
        try:
            json.loads(dst.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return False, f"JSON 坏了：{exc}"
    if fmt == "xml":
        import xml.etree.ElementTree as ET

        try:
            ET.fromstring(dst.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return False, f"XML 坏了：{exc}"
    if fmt == "yaml":
        try:
            import yaml

            yaml.safe_load(dst.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return False, f"YAML 坏了：{exc}"
    return True, f"{dst.stat().st_size}B"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-ffmpeg", action="store_true", help="音视频也一起跑")
    args = parser.parse_args()

    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)

    if not args.with_ffmpeg:
        media = {"mp4", "mkv", "avi", "mov", "wmv", "flv", "webm",
                 "mp3", "wav", "ogg", "flac", "aac", "m4a", "wma"}
        print(f"[提示] 跳过音视频格式（{len(media)} 种），加 --with-ffmpeg 可全跑\n")

    print("=" * 72)
    print(f"fconv 格式矩阵冒烟测试 v{__version__}")
    print("=" * 72)

    pairs = list(router.iter_format_pairs())
    passed, failed, skipped = 0, 0, 0
    rows = []

    for src_fmt, dst_fmt in pairs:
        if not args.with_ffmpeg and (src_fmt in media or dst_fmt in media):
            skipped += 1
            continue

        src = WORK / f"in_{src_fmt}.{src_fmt}"
        if not src.exists() and not make_fixture(src_fmt, src):
            skipped += 1
            rows.append({"pair": f"{src_fmt}->{dst_fmt}", "status": "skip", "detail": "无法造样本"})
            continue

        dst = WORK / f"out_{src_fmt}_to_{dst_fmt}.{dst_fmt}"
        started = time.perf_counter()
        result = router.convert(src, dst)
        ms = (time.perf_counter() - started) * 1000

        if not result.ok:
            failed += 1
            rows.append({"pair": f"{src_fmt}->{dst_fmt}", "status": "fail", "detail": result.message})
            print(f"  [FAIL] {src_fmt:>5s} -> {dst_fmt:<5s} {result.message[:60]}")
            continue

        ok, detail = verify_output(result.output_path or dst)
        if ok:
            passed += 1
            rows.append({"pair": f"{src_fmt}->{dst_fmt}", "status": "pass", "detail": detail, "ms": round(ms, 2)})
            print(f"  [PASS] {src_fmt:>5s} -> {dst_fmt:<5s} {ms:7.1f}ms  {detail}")
        else:
            failed += 1
            rows.append({"pair": f"{src_fmt}->{dst_fmt}", "status": "fail", "detail": detail})
            print(f"  [FAIL] {src_fmt:>5s} -> {dst_fmt:<5s} {detail}")

    print("-" * 72)
    print(f"通过 {passed} / 失败 {failed} / 跳过 {skipped}（共 {len(pairs)} 个格式对）")

    out = ROOT / "benchmarks" / "smoke_results.json"
    out.write_text(
        json.dumps(
            {
                "version": __version__,
                "with_ffmpeg": args.with_ffmpeg,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"明细写入 {out}")

    shutil.rmtree(WORK, ignore_errors=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
