"""
文件嗅探器 - 通过魔数（Magic Number）与扩展名双重判断真实文件类型。

设计要点
--------
1. **魔数优先**：读文件头判断真实格式，改名文件（`.png` 里其实是 JPEG）也能认出来。
2. **容器歧义消解**：`RIFF` 家族（WAV / AVI / WebP）靠偏移 8 处的 FourCC 区分，
   旧实现用字典存 `RIFF` 键，后写的会覆盖先写的，导致 WebP/AVI 被误判成 WAV。
3. **扩展名兜底**：纯文本类格式（txt / md / json / csv / xml / yaml）没有固定魔数，
   此时回退到扩展名 + 内容启发式。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------- 魔数表
# 顺序即优先级；容器类（RIFF / ISO-BMFF）在 _match_magic 里单独处理。
MAGIC_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"BM", "bmp"),
    (b"II\x2a\x00", "tif"),
    (b"MM\x00\x2a", "tif"),
    (b"%PDF", "pdf"),
    (b"\x1a\x45\xdf\xa3", "mkv"),          # EBML：MKV / WebM 共用
    (b"ID3", "mp3"),
    (b"\xff\xfb", "mp3"),
    (b"\xff\xf3", "mp3"),
    (b"\xff\xf2", "mp3"),
    (b"OggS", "ogg"),
    (b"fLaC", "flac"),
    (b"PK\x03\x04", "zip"),                 # DOCX / XLSX / ODT 等容器
)

# RIFF 容器：偏移 8 处的 FourCC → 格式
RIFF_FOURCC: dict[bytes, str] = {
    b"WAVE": "wav",
    b"AVI ": "avi",
    b"WEBP": "webp",
}

# ISO-BMFF（ftyp）容器：偏移 8 处的 brand → 格式
FTYP_BRANDS: dict[bytes, str] = {
    b"isom": "mp4",
    b"iso2": "mp4",
    b"mp41": "mp4",
    b"mp42": "mp4",
    b"M4V ": "mp4",
    b"M4A ": "m4a",
    b"qt  ": "mov",
    b"avc1": "mp4",
    b"webm": "webm",
}

# ---------------------------------------------------------------- 扩展名表
EXTENSION_MAP: dict[str, str] = {
    # 图片
    "png": "png", "jpg": "jpg", "jpeg": "jpg", "gif": "gif",
    "bmp": "bmp", "tif": "tif", "tiff": "tif", "webp": "webp",
    "svg": "svg", "ico": "ico",
    # 视频
    "mp4": "mp4", "mkv": "mkv", "avi": "avi", "mov": "mov",
    "wmv": "wmv", "flv": "flv", "webm": "webm",
    # 音频
    "mp3": "mp3", "wav": "wav", "ogg": "ogg", "flac": "flac",
    "aac": "aac", "m4a": "m4a", "wma": "wma",
    # 文档
    "pdf": "pdf", "docx": "docx", "doc": "doc",
    "odt": "odt", "rtf": "rtf",
    "txt": "txt", "md": "md", "markdown": "md",
    "html": "html", "htm": "html",
    # 数据
    "json": "json", "csv": "csv", "xml": "xml", "yaml": "yaml", "yml": "yaml",
}

# 规范扩展名（反查时优先使用）
CANONICAL_EXTENSION: dict[str, str] = {
    "jpg": "jpg", "tif": "tif", "html": "html", "yaml": "yaml", "md": "md",
}

TEXT_FORMATS = frozenset({"txt", "md", "json", "csv", "xml", "yaml", "svg", "htm", "html"})


class FileSniffer:
    """文件嗅探器：魔数优先、扩展名兜底。"""

    def __init__(self) -> None:
        # 格式 → 规范扩展名（多扩展名时取 CANONICAL_EXTENSION 指定的那个）
        self._format_ext: dict[str, str] = {}
        for ext, fmt in EXTENSION_MAP.items():
            if fmt in CANONICAL_EXTENSION:
                self._format_ext[fmt] = CANONICAL_EXTENSION[fmt]
            else:
                self._format_ext.setdefault(fmt, ext)

    # ------------------------------------------------------------ 公共 API
    def detect(self, path: str | Path) -> Optional[str]:
        """检测文件真实格式，无法识别返回 None。"""
        path = Path(path)
        try:
            if not path.exists() or not path.is_file():
                return None
            if path.stat().st_size == 0:
                return None
        except OSError:
            return None

        header = self._read_header(path, 64)

        ext_fmt = EXTENSION_MAP.get(path.suffix.lower().lstrip("."))

        # 1) 魔数优先（改名文件也能识别）
        by_magic = self._match_magic(header)
        if by_magic is not None:
            # ZIP 容器里的 Office 文档：按扩展名报更准确的名字
            if by_magic == "zip" and ext_fmt in {"docx", "odt", "xlsx", "pptx"}:
                return ext_fmt
            return by_magic

        # 2) 纯文本/标记类：扩展名 + 内容启发
        if ext_fmt in TEXT_FORMATS:
            return ext_fmt

        # 3) 扩展名兜底（无魔数的老格式）
        if ext_fmt is not None:
            return ext_fmt

        return self._sniff_text(path)

    def get_extension(self, format_name: str) -> str:
        """格式名 → 规范扩展名。"""
        return self._format_ext.get(format_name, format_name)

    # ------------------------------------------------------------ 内部实现
    @staticmethod
    def _read_header(path: Path, size: int) -> bytes:
        try:
            with open(path, "rb") as fh:
                return fh.read(size)
        except OSError:
            return b""

    @staticmethod
    def _match_magic(header: bytes) -> Optional[str]:
        if len(header) < 12:
            return None

        # RIFF 容器
        if header[:4] == b"RIFF":
            return RIFF_FOURCC.get(header[8:12])
        # ISO-BMFF（MP4 / MOV / M4A）
        if header[4:8] == b"ftyp":
            brand = header[8:12]
            if brand in FTYP_BRANDS:
                return FTYP_BRANDS[brand]
            return "mp4"  # 未知 brand，按 MP4 家族处理

        for magic, fmt in MAGIC_SIGNATURES:
            if header.startswith(magic):
                return fmt
        return None

    @staticmethod
    def _sniff_text(path: Path) -> Optional[str]:
        """无魔数、无扩展名时的内容探测。"""
        try:
            raw = path.read_bytes()[:65536]
        except OSError:
            return None
        if b"\x00" in raw[:4096]:
            return None  # 含 NUL，判定为二进制
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = raw.decode("gbk")
            except UnicodeDecodeError:
                return None

        stripped = text.lstrip()
        if stripped.startswith("<?xml"):
            return "xml"
        if stripped.startswith("{") or stripped.startswith("["):
            return "json"
        if stripped.startswith("<!DOCTYPE") or stripped.startswith("<html"):
            return "html"
        if text:
            return "txt"
        return None


# ------------------------------------------------------------------ 单例
_sniffer: Optional[FileSniffer] = None


def get_sniffer() -> FileSniffer:
    """获取全局嗅探器单例。"""
    global _sniffer
    if _sniffer is None:
        _sniffer = FileSniffer()
    return _sniffer
