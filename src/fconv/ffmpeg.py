"""
FFmpeg 定位与调用封装（音视频转换共用）。

查找顺序
--------
1. 环境变量 ``FCONV_FFMPEG`` 指定的可执行文件
2. 项目内 ``tools/ffmpeg/bin/ffmpeg(.exe)``（便携版可自带）
3. 环境变量 ``PATH`` 里的 ``ffmpeg``

> 不再硬编码任何开发者本机路径——开源版本必须能在别人机器上跑。
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

# 项目根（src/fconv/ffmpeg.py → 项目根）
PROJECT_ROOT = Path(__file__).resolve().parents[2]

BUNDLED_CANDIDATES = (
    PROJECT_ROOT / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe",
    PROJECT_ROOT / "tools" / "ffmpeg" / "bin" / "ffmpeg",
    PROJECT_ROOT / "ffmpeg" / "bin" / "ffmpeg.exe",
    PROJECT_ROOT / "ffmpeg-bin" / "ffmpeg.exe",
)

ENV_VAR = "FCONV_FFMPEG"


def find_ffmpeg() -> str | None:
    """返回可用的 ffmpeg 路径，找不到返回 None。"""
    env_path = os.environ.get(ENV_VAR)
    if env_path:
        candidate = Path(env_path)
        if candidate.is_file():
            return str(candidate)
        found = shutil.which(env_path)
        if found:
            return found

    for candidate in BUNDLED_CANDIDATES:
        if candidate.is_file():
            return str(candidate)

    return shutil.which("ffmpeg")


def ffmpeg_available() -> bool:
    return find_ffmpeg() is not None


def ffmpeg_hint() -> str:
    """给用户的安装提示（写清楚两条路，省得来回问）。"""
    return (
        "未找到 FFmpeg。请任选其一："
        "① 安装 FFmpeg 并加入 PATH；"
        f"② 设置环境变量 {ENV_VAR} 指向 ffmpeg 可执行文件；"
        "③ 把 ffmpeg 放到项目 tools/ffmpeg/bin/ 目录下。"
    )


class FFmpegError(RuntimeError):
    """FFmpeg 非零退出的封装，message 已裁剪到可读长度。"""

    def __init__(self, returncode: int, stderr: str) -> None:
        self.returncode = returncode
        self.stderr = (stderr or "").strip()
        super().__init__(self._summary())

    def _summary(self) -> str:
        # FFmpeg 的报错重点通常在最后几行
        lines = [ln.strip() for ln in self.stderr.splitlines() if ln.strip()]
        tail = " / ".join(lines[-3:]) if lines else "无错误输出"
        return tail[:400]


def run_ffmpeg(cmd: Sequence[str], timeout: int = 1800) -> None:
    """
    执行 ffmpeg 命令；成功返回 None，失败抛 :class:`FFmpegError`。

    ``-nostdin`` 防止 ffmpeg 抢标准输入导致后台运行时卡死。
    """
    full_cmd = [cmd[0], "-nostdin", "-hide_banner", *cmd[1:]]
    try:
        proc = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"转换超时（超过 {timeout // 60} 分钟）") from exc
    except FileNotFoundError as exc:
        raise FFmpegError(-1, f"无法启动 FFmpeg：{exc}") from exc

    if proc.returncode != 0:
        raise FFmpegError(proc.returncode, proc.stderr)
