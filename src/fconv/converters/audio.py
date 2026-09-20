"""
音频转换器 - 基于 FFmpeg。

支持：MP3 / WAV / OGG / FLAC / AAC / M4A（互相转换，``wma`` 只作输入）。
FFmpeg 缺失时返回 DEPENDENCY_MISSING，不抛异常。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..core import Converter, ConvertResult, ErrorCode, Timer
from ..ffmpeg import FFmpegError, ffmpeg_hint, find_ffmpeg, run_ffmpeg

logger = logging.getLogger(__name__)

# 目标扩展名 → 编码器
CODEC_MAP: dict[str, str] = {
    "mp3": "libmp3lame",
    "wav": "pcm_s16le",
    "ogg": "libvorbis",
    "flac": "flac",
    "aac": "aac",
    "m4a": "aac",
}

LOSSLESS = {"wav", "flac"}


class AudioConverter(Converter):
    """音频格式转换器。"""

    source_formats = ["mp3", "wav", "ogg", "flac", "aac", "m4a", "wma"]
    target_formats = ["mp3", "wav", "ogg", "flac", "aac", "m4a"]

    def convert(
        self,
        src: Path,
        dst: Path,
        bitrate: int = 192,
        **options: Any,
    ) -> ConvertResult:
        """
        Args:
            bitrate: 有损格式的目标比特率（kbps），默认 192
        """
        src, dst = Path(src), Path(dst)
        ext = dst.suffix.lower().lstrip(".")
        codec = CODEC_MAP.get(ext)
        if codec is None:
            return ConvertResult.failure(
                ErrorCode.FORMAT_NOT_SUPPORTED,
                f"不支持的音频输出格式：{ext or '（无扩展名）'}",
                src,
            )

        ffmpeg = find_ffmpeg()
        if ffmpeg is None:
            return ConvertResult.failure(ErrorCode.DEPENDENCY_MISSING, ffmpeg_hint(), src)

        bitrate = max(8, min(512, int(bitrate)))

        cmd: list[str] = [ffmpeg, "-i", str(src), "-vn", "-map_metadata", "0", "-c:a", codec]
        if ext in LOSSLESS:
            if ext == "flac":
                cmd += ["-compression_level", "6"]
        else:
            cmd += ["-b:a", f"{bitrate}k"]
        cmd += ["-y", str(dst)]

        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            with Timer() as timer:
                run_ffmpeg(cmd, timeout=1800)
        except TimeoutError as exc:
            return ConvertResult.failure(ErrorCode.CONVERSION_FAILED, str(exc), src)
        except FFmpegError as exc:
            logger.error("音频转换失败 %s：%s", src.name, exc)
            return ConvertResult.failure(
                ErrorCode.CONVERSION_FAILED, f"音频转换失败：{exc}", src
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("音频转换异常：%s", src)
            return ConvertResult.failure(
                ErrorCode.CONVERSION_FAILED, f"转换失败：{exc}", src
            )

        logger.info("音频转换成功：%s → %s", src.name, dst.name)
        return ConvertResult.success(dst, duration=timer.elapsed)
