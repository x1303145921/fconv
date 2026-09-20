"""
批量转换 - 多文件并发处理，可选打包成 ZIP。
"""
from __future__ import annotations

import concurrent.futures
import logging
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from .core import ConvertResult
from .router import get_router

logger = logging.getLogger(__name__)

DEFAULT_WORKERS = 4
MAX_WORKERS = 16


@dataclass
class BatchItemResult:
    """批量里单个文件的结果。"""

    input_path: Path
    output_path: Path | None
    ok: bool
    error_message: str = ""
    error_code: str | None = None
    duration: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "input": str(self.input_path),
            "input_name": self.input_path.name,
            "output": str(self.output_path) if self.output_path else None,
            "output_name": self.output_path.name if self.output_path else None,
            "ok": self.ok,
            "error_code": self.error_code,
            "error": self.error_message,
            "duration_ms": round(self.duration * 1000, 2),
        }


# 向后兼容的别名（旧代码 / 文档里叫 BatchResult）
BatchResult = BatchItemResult


class BatchConverter:
    """并发批量转换器。"""

    def __init__(self, max_workers: int = DEFAULT_WORKERS) -> None:
        self.max_workers = max(1, min(MAX_WORKERS, int(max_workers)))
        self.router = get_router()

    # ------------------------------------------------------------ 主流程
    def convert(
        self,
        files: Sequence[Path],
        target_format: str | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
        output_dir: Path | None = None,
        **options: Any,
    ) -> list[BatchItemResult]:
        """
        Args:
            files: 源文件列表
            target_format: 目标格式；None 时在每个文件旁生成 ``*_converted.<原扩展名>``
            progress_callback: ``(已完成数, 总数)``
            output_dir: 产物目录；None 时与源文件同目录
            **options: 透传给具体转换器
        """
        file_list = [Path(f) for f in files]
        total = len(file_list)
        if total == 0:
            return []

        destination = Path(output_dir) if output_dir else None
        if destination is not None:
            destination.mkdir(parents=True, exist_ok=True)

        results: list[BatchItemResult] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(self._convert_one, path, target_format, options, destination): path
                for path in file_list
            }
            for done, future in enumerate(concurrent.futures.as_completed(futures), start=1):
                source = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:  # noqa: BLE001 - 线程内异常不能漏
                    logger.exception("批量转换异常：%s", source)
                    results.append(
                        BatchItemResult(source, None, False, f"内部错误：{exc}")
                    )
                if progress_callback:
                    progress_callback(done, total)

        # 保持输入顺序，方便对照
        order = {str(path): index for index, path in enumerate(file_list)}
        results.sort(key=lambda item: order.get(str(item.input_path), 0))
        return results

    def _convert_one(
        self,
        src: Path,
        target_format: str | None,
        options: dict[str, Any],
        output_dir: Path | None = None,
    ) -> BatchItemResult:
        if not src.exists():
            return BatchItemResult(src, None, False, "文件不存在", "file_not_found")
        if src.is_dir():
            return BatchItemResult(src, None, False, "是目录，不是文件", "invalid_input")
        if src.stat().st_size == 0:
            return BatchItemResult(src, None, False, "文件为空", "file_empty")

        target_dir = output_dir or src.parent
        clean_format = (target_format or "").lstrip(".").lower()
        if clean_format:
            dst = target_dir / f"{src.stem}.{clean_format}"
            if dst == src:
                dst = target_dir / f"{src.stem}_converted{src.suffix}"
        else:
            dst = target_dir / f"{src.stem}_converted{src.suffix}"

        start = time.perf_counter()
        result: ConvertResult = self.router.convert(src, dst, **options)
        duration = time.perf_counter() - start

        if result.ok and result.output_path is not None:
            return BatchItemResult(src, result.output_path, True, duration=duration)
        return BatchItemResult(
            src,
            None,
            False,
            result.message,
            result.error_code.value if result.error_code else None,
            duration,
        )

    # ------------------------------------------------------------ 转换并打包
    def convert_and_pack(
        self,
        files: Sequence[Path],
        target_format: str | None = None,
        output_zip: Path | None = None,
        output_dir: Path | None = None,
        **options: Any,
    ) -> tuple[list[BatchItemResult], Path | None]:
        """批量转换并把成功的产物打成一个 ZIP；全部失败时返回 (结果, None)。"""
        results = self.convert(files, target_format, output_dir=output_dir, **options)

        successes = [
            item for item in results if item.ok and item.output_path and item.output_path.exists()
        ]
        if not successes:
            return results, None

        if output_zip is None:
            first = Path(files[0])
            label = (target_format or "converted").lstrip(".")
            output_zip = first.parent / f"converted_{label}.zip"

        output_zip.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            used: set[str] = set()
            for item in successes:
                assert item.output_path is not None
                name = item.output_path.name
                if name in used:  # 同名文件加序号，避免 ZIP 内覆盖
                    name = f"{item.output_path.stem}_{len(used)}{item.output_path.suffix}"
                used.add(name)
                archive.write(item.output_path, name)

        return results, output_zip

    # 兼容旧名字
    convert_batch_and_pack = convert_and_pack
