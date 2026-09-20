"""
视频转换器 - 基于 FFmpeg。

支持：MP4 / MKV / AVI / MOV / WMV / FLV / WEBM 互转，以及导出 GIF 动图。
特点：GIF 走「调色板两遍法」保证画质，生成的临时调色板文件用完即删。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..core import Converter, ConvertResult, ErrorCode, Timer
from ..ffmpeg import FFmpegError, ffmpeg_hint, find_ffmpeg, run_ffmpeg

logger = logging.getLogger(__name__)

TARGET_FORMATS = ["mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "gif"]

# GIF 输出参数：10fps、宽 480，够小够清楚
GIF_FILTER = "fps=10,scale=480:-1:flags=lanczos"

# 每种容器配自己的编码器——把 H.264 塞进 WebM 是非法组合，
# 早期版本对所有容器都用 libx264+aac，导致所有 →webm 的转换都产出空文件。
_H264 = ["-c:v", "libx264", "-crf", "{crf}", "-preset", "medium", "-pix_fmt", "yuv420p"]
_AAC = ["-c:a", "aac", "-b:a", "128k"]

VIDEO_PROFILES: dict[str, dict[str, list[str]]] = {
    "mp4": {"video": _H264, "audio": _AAC},
    "mov": {"video": _H264, "audio": _AAC},
    "mkv": {"video": _H264, "audio": _AAC},
    "flv": {
        "video": ["-c:v", "libx264", "-crf", "{crf}", "-preset", "veryfast", "-pix_fmt", "yuv420p"],
        "audio": _AAC,
    },
    "avi": {
        "video": ["-c:v", "mpeg4", "-qscale:v", "4"],
        "audio": ["-c:a", "libmp3lame", "-b:a", "192k"],
    },
    "wmv": {
        "video": ["-c:v", "wmv2", "-qscale:v", "4"],
        "audio": ["-c:a", "wmav2", "-b:a", "128k"],
    },
    "webm": {
        "video": ["-c:v", "libvpx-vp9", "-crf", "34", "-b:v", "0", "-row-mt", "1"],
        "audio": ["-c:a", "libopus", "-b:a", "96k"],
    },
}

# 如果本机 FFmpeg 没编 VP9，用 VP8 兼底
WEBM_FALLBACK: dict[str, list[str]] = {
    "video": ["-c:v", "libvpx", "-crf", "12", "-b:v", "1M"],
    "audio": ["-c:a", "libvorbis", "-b:a", "128k"],
}


class VideoConverter(Converter):
    """视频格式转换器。"""

    source_formats = ["mp4", "mkv", "avi", "mov", "wmv", "flv", "webm"]
    target_formats = TARGET_FORMATS

    def convert(
        self,
        src: Path,
        dst: Path,
        fps: int | None = None,
        resolution: tuple[int, int] | None = None,
        crf: int = 23,
        **options: Any,
    ) -> ConvertResult:
        """
        Args:
            fps: 目标帧率，None 保持原样
            resolution: 目标分辨率 (宽, 高)，None 保持原样
            crf: x264 质量（1-51，越小越清晰），默认 23
        """
        src, dst = Path(src), Path(dst)
        ext = dst.suffix.lower().lstrip(".")
        if ext not in TARGET_FORMATS:
            return ConvertResult.failure(
                ErrorCode.FORMAT_NOT_SUPPORTED,
                f"不支持的视频输出格式：{ext or '（无扩展名）'}",
                src,
            )

        ffmpeg = find_ffmpeg()
        if ffmpeg is None:
            return ConvertResult.failure(ErrorCode.DEPENDENCY_MISSING, ffmpeg_hint(), src)

        crf = max(1, min(51, int(crf)))
        dst.parent.mkdir(parents=True, exist_ok=True)

        try:
            with Timer() as timer:
                if ext == "gif":
                    self._convert_to_gif(ffmpeg, src, dst)
                else:
                    self._convert_video(ffmpeg, src, dst, ext, fps, resolution, crf)
        except TimeoutError as exc:
            return ConvertResult.failure(ErrorCode.CONVERSION_FAILED, str(exc), src)
        except FFmpegError as exc:
            logger.error("视频转换失败 %s：%s", src.name, exc)
            return ConvertResult.failure(
                ErrorCode.CONVERSION_FAILED, f"视频转换失败：{exc}", src
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("视频转换异常：%s", src)
            return ConvertResult.failure(
                ErrorCode.CONVERSION_FAILED, f"转换失败：{exc}", src
            )

        logger.info("视频转换成功：%s → %s", src.name, dst.name)
        return ConvertResult.success(dst, duration=timer.elapsed)

    # ------------------------------------------------------------ 内部实现
    @staticmethod
    def _convert_video(
        ffmpeg: str,
        src: Path,
        dst: Path,
        ext: str,
        fps: int | None,
        resolution: tuple[int, int] | None,
        crf: int,
    ) -> None:
        profile = VIDEO_PROFILES.get(ext)
        if profile is None:
            raise FFmpegError(-1, f"没有为 {ext} 配置编码器")

        def build(chosen: dict[str, list[str]]) -> list[str]:
            command = [ffmpeg, "-i", str(src), *chosen["video"]]
            if fps:
                command += ["-r", str(int(fps))]
            if resolution:
                width, height = resolution
                command += ["-vf", f"scale={int(width)}:{int(height)}"]
            command += [*chosen["audio"], "-movflags", "+faststart", "-y", str(dst)]
            return [part.format(crf=crf) for part in command]

        try:
            run_ffmpeg(build(profile), timeout=3600)
        except FFmpegError:
            if ext != "webm":
                raise
            # VP9 不可用（旧版 FFmpeg）时降级到 VP8
            logger.warning("VP9 编码不可用，改用 VP8 重试：%s", src.name)
            run_ffmpeg(build(WEBM_FALLBACK), timeout=3600)

    @staticmethod
    def _convert_to_gif(ffmpeg: str, src: Path, dst: Path) -> None:
        """两遍法：先生成最优调色板，再套用调色板生成 GIF。"""
        palette = dst.with_name(dst.stem + "_palette.png")
        try:
            run_ffmpeg(
                [ffmpeg, "-i", str(src), "-vf", f"{GIF_FILTER},palettegen", "-y", str(palette)],
                timeout=1800,
            )
            run_ffmpeg(
                [
                    ffmpeg, "-i", str(src), "-i", str(palette),
                    "-lavfi", f"{GIF_FILTER} [x]; [x][1:v] paletteuse",
                    "-loop", "0", "-y", str(dst),
                ],
                timeout=1800,
            )
        finally:
            palette.unlink(missing_ok=True)  # 临时文件不留在用户目录里
