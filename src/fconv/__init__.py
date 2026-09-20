"""
fconv - 本地文件格式转换工具库。

一个入口搞定 图片 / 文档 / 视频 / 音频 / PDF 互转；文件不上传，隐私安全。

版本号唯一来源：``fconv.__version__``（CLI、Web 服务、打包脚本都从这里读）。
"""
from __future__ import annotations

__version__ = "1.0.0"
__author__ = "fconv contributors"
__license__ = "MIT"
__url__ = "https://github.com/x1303145921/fconv"

from .core import Converter, ConvertResult, ErrorCode, get_error_message
from .router import ConversionRouter, get_router
from .sniffer import FileSniffer, get_sniffer

__all__ = [
    "__version__",
    "__author__",
    "__license__",
    "Converter",
    "ConvertResult",
    "ErrorCode",
    "get_error_message",
    "ConversionRouter",
    "get_router",
    "FileSniffer",
    "get_sniffer",
]
