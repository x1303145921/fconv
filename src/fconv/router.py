"""
转换路由器 - 数据驱动的格式路由。

新增一种格式只要写一个转换器类（声明 ``source_formats`` / ``target_formats``），
在 ``register`` 时注册即可，不需要改这里的逻辑。
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .core import Converter, ConvertResult, ErrorCode
from .sniffer import FileSniffer, get_sniffer

# 同义格式名归一：jpeg→jpg、htm→html、tiff→tif、yml→yaml、markdown→md
FORMAT_ALIASES: dict[str, str] = {
    "jpeg": "jpg",
    "jpe": "jpg",
    "tiff": "tif",
    "htm": "html",
    "yml": "yaml",
    "markdown": "md",
    "wave": "wav",
}


def normalize_format(fmt: str | None) -> str | None:
    """把用户输入的格式名归一成内部规范名。"""
    if not fmt:
        return None
    key = fmt.strip().lower().lstrip(".")
    return FORMAT_ALIASES.get(key, key)


class ConversionRouter:
    """转换路由器：按「源格式 → 目标格式」挑一个能干的转换器。"""

    def __init__(self, sniffer: FileSniffer | None = None) -> None:
        self._sniffer = sniffer or get_sniffer()
        self._handlers: dict[str, list[Converter]] = {}
        self._register_builtin()

    # ------------------------------------------------------------ 注册
    def _register_builtin(self) -> None:
        from .converters.audio import AudioConverter
        from .converters.image import ImageConverter
        from .converters.pdf import PDFConverter
        from .converters.text import TextConverter
        from .converters.video import VideoConverter

        self.register(
            ImageConverter(),
            VideoConverter(),
            AudioConverter(),
            PDFConverter(),
            TextConverter(),
        )

    def register(self, *converters: Converter) -> None:
        """注册转换器：只按 source_formats 挂入口，避免目标格式被当成入口。"""
        for converter in converters:
            for fmt in converter.source_formats:
                key = normalize_format(fmt)
                if key is None:
                    continue
                bucket = self._handlers.setdefault(key, [])
                if converter not in bucket:
                    bucket.append(converter)

    # ------------------------------------------------------------ 查询
    def detect_format(self, path: str | Path) -> str | None:
        """检测文件真实格式。"""
        return self._sniffer.detect(path)

    def can_convert(self, src_format: str | None, dst_format: str | None) -> bool:
        """是否支持该转换对。"""
        return self._pick(src_format, dst_format) is not None

    def _pick(self, src_format: str | None, dst_format: str | None) -> Converter | None:
        src = normalize_format(src_format)
        dst = normalize_format(dst_format)
        if src is None or dst is None:
            return None
        for converter in self._handlers.get(src, []):
            targets = {normalize_format(t) for t in converter.target_formats}
            if dst in targets:
                return converter
        return None

    def get_supported_formats(self) -> dict[str, list[str]]:
        """源格式 → 可达目标格式列表。"""
        result: dict[str, list[str]] = {}
        for fmt, converters in self._handlers.items():
            targets: set[str] = set()
            for converter in converters:
                targets.update(
                    t for t in (normalize_format(x) for x in converter.target_formats) if t
                )
            result[fmt] = sorted(targets)
        return results_sorted(result)

    def get_format_info(self) -> str:
        """格式支持表的可读文本（CLI ``fconv info`` 用）。"""
        formats = self.get_supported_formats()
        lines = [f"支持的格式转换（共 {sum(len(v) for v in formats.values())} 个格式对）:", ""]
        for src_fmt, targets in sorted(formats.items()):
            lines.append(f"  {src_fmt:>5s} → {', '.join(targets)}")
        return "\n".join(lines)

    def iter_format_pairs(self) -> Iterable[tuple[str, str]]:
        """遍历所有 (源, 目标) 格式对。"""
        for src_fmt, targets in self.get_supported_formats().items():
            for dst_fmt in targets:
                yield src_fmt, dst_fmt

    # ------------------------------------------------------------ 转换
    def convert(
        self,
        src: str | Path,
        dst: str | Path,
        src_format: str | None = None,
        dst_format: str | None = None,
        **options: object,
    ) -> ConvertResult:
        """
        执行一次转换。

        Args:
            src: 源文件路径
            dst: 目标文件路径
            src_format: 源格式（默认自动嗅探）
            dst_format: 目标格式（默认取目标扩展名）
            **options: 传给具体转换器的选项（quality / crf / bitrate ...）

        Returns:
            ConvertResult
        """
        src = Path(src)
        dst = Path(dst)

        if not src.exists():
            return ConvertResult.failure(
                ErrorCode.FILE_NOT_FOUND, f"源文件不存在：{src}", src
            )
        if not src.is_file():
            return ConvertResult.failure(
                ErrorCode.INVALID_INPUT, f"源路径不是文件：{src}", src
            )
        try:
            if src.stat().st_size == 0:
                return ConvertResult.failure(ErrorCode.FILE_EMPTY, "源文件为空", src)
        except OSError as exc:
            return ConvertResult.failure(
                ErrorCode.INVALID_INPUT, f"无法读取源文件：{exc}", src
            )

        src_format = normalize_format(src_format) or self.detect_format(src)
        if not src_format:
            return ConvertResult.failure(
                ErrorCode.INVALID_INPUT, f"无法识别源文件格式：{src.name}", src
            )

        dst_format = normalize_format(dst_format) or normalize_format(dst.suffix)

        converter = self._pick(src_format, dst_format)
        if converter is None:
            return ConvertResult.failure(
                ErrorCode.FORMAT_NOT_SUPPORTED,
                f"不支持从 {src_format} 转换到 {dst_format or '未知格式'}",
                src,
            )

        try:
            result = converter.convert(src, dst, **options)
        except Exception as exc:  # 转换器内部未捕获的异常兜底，绝不让服务崩
            return ConvertResult.failure(
                ErrorCode.CONVERSION_FAILED, f"转换过程中出现异常：{exc}", src
            )

        if result.input_path is None:
            result.input_path = src
        return result


def results_sorted(formats: dict[str, list[str]]) -> dict[str, list[str]]:
    return {k: formats[k] for k in sorted(formats)}


_router: ConversionRouter | None = None


def get_router() -> ConversionRouter:
    """获取全局路由器单例。"""
    global _router
    if _router is None:
        _router = ConversionRouter()
    return _router
