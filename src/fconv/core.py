"""
fconv 核心数据结构：转换器协议、转换结果、错误码。

约定
----
* 转换器**不抛异常**给上层，一律返回 :class:`ConvertResult`；
* 错误一律带 :class:`ErrorCode`，界面按错误码给用户看的提示；
* 结果里同时保留 `input_path` / `output_path`，方便写日志与历史记录。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class ErrorCode(str, Enum):
    """转换错误码（同时也是给前端/日志用的稳定标识）。"""

    SUCCESS = "success"
    FORMAT_NOT_SUPPORTED = "format_not_supported"
    DEPENDENCY_MISSING = "dependency_missing"
    CONVERSION_FAILED = "conversion_failed"
    FILE_NOT_FOUND = "file_not_found"
    FILE_EMPTY = "file_empty"
    OUTPUT_IN_USE = "output_in_use"
    DISK_FULL = "disk_full"
    INVALID_INPUT = "invalid_input"
    FILE_TOO_LARGE = "file_too_large"
    UNKNOWN_ERROR = "unknown_error"


# 内置错误消息映射（面向用户的中文提示）
ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.SUCCESS: "转换成功",
    ErrorCode.FORMAT_NOT_SUPPORTED: "不支持此格式转换",
    ErrorCode.DEPENDENCY_MISSING: "缺少必要的转换组件",
    ErrorCode.CONVERSION_FAILED: "转换失败，请检查文件是否损坏",
    ErrorCode.FILE_NOT_FOUND: "源文件不存在",
    ErrorCode.FILE_EMPTY: "源文件为空",
    ErrorCode.OUTPUT_IN_USE: "目标文件正在被其他程序占用",
    ErrorCode.DISK_FULL: "磁盘空间不足",
    ErrorCode.INVALID_INPUT: "输入文件格式无效",
    ErrorCode.FILE_TOO_LARGE: "文件超过大小上限",
    ErrorCode.UNKNOWN_ERROR: "发生未知错误",
}


def get_error_message(error_code: ErrorCode | str | None) -> str:
    """获取错误码对应的用户友好消息。"""
    if error_code is None:
        return ERROR_MESSAGES[ErrorCode.UNKNOWN_ERROR]
    if isinstance(error_code, str):
        try:
            error_code = ErrorCode(error_code)
        except ValueError:
            return error_code
    return ERROR_MESSAGES.get(error_code, str(error_code))


@dataclass
class ConvertResult:
    """一次转换的结果。"""

    ok: bool
    error_code: ErrorCode | None = None
    message: str = ""
    duration: float = 0.0
    output_path: Path | None = None
    input_path: Path | None = None
    progress: float = 0.0  # 0-100，异步场景预留
    extra: dict[str, Any] = field(default_factory=dict)

    # ---------------------------------------------------------- 构造快捷方法
    @classmethod
    def success(
        cls,
        output_path: Path,
        duration: float = 0.0,
        **extra: Any,
    ) -> "ConvertResult":
        return cls(
            ok=True,
            error_code=ErrorCode.SUCCESS,
            message="转换成功",
            output_path=Path(output_path),
            duration=duration,
            progress=100.0,
            extra=dict(extra),
        )

    @classmethod
    def failure(
        cls,
        error_code: ErrorCode | str,
        message: str = "",
        input_path: Path | None = None,
    ) -> "ConvertResult":
        code = error_code if isinstance(error_code, ErrorCode) else ErrorCode(str(error_code))
        return cls(
            ok=False,
            error_code=code,
            message=message or get_error_message(code),
            input_path=Path(input_path) if input_path is not None else None,
        )

    @classmethod
    def in_progress(cls, progress: float) -> "ConvertResult":
        return cls(ok=False, progress=progress)

    # ---------------------------------------------------------- 辅助方法
    @property
    def error_message(self) -> str:
        """失败原因（成功时为空串）。"""
        return "" if self.ok else self.message

    def to_dict(self) -> dict[str, Any]:
        """序列化（写历史记录 / API 返回用）。"""
        return {
            "ok": self.ok,
            "error_code": self.error_code.value if self.error_code else None,
            "message": self.message,
            "duration_ms": round(self.duration * 1000, 2),
            "input": str(self.input_path) if self.input_path else None,
            "output": str(self.output_path) if self.output_path else None,
        }


@runtime_checkable
class Converter(Protocol):
    """转换器协议。"""

    source_formats: list[str]
    target_formats: list[str]

    def convert(self, src: Path, dst: Path, **options: Any) -> ConvertResult:
        """把 ``src`` 转成 ``dst``；失败返回 ConvertResult.failure(...)"""
        ...


class Timer:
    """给转换器记耗时的轻量上下文管理器。"""

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        self.elapsed = 0.0
        return self

    def __exit__(self, *exc: object) -> bool:
        self.elapsed = time.perf_counter() - self._start
        return False
