"""
转换历史与运行日志。

* **历史记录**：``logs/history.jsonl``，一行一条 JSON，追加写入；
  记录每个任务的源文件、目标格式、结果状态、失败原因、耗时——可追溯、可导出。
* **运行日志**：``logs/fconv.log``，带轮转（默认单文件 2MB × 3 份），
  出错时先看这里。

两个文件都在 ``.gitignore`` 里，不会进仓库。
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"

MAX_HISTORY_LINES = 2000  # 超过就滚动裁剪，防文件无限膨胀


class HistoryStore:
    """JSONL 追加式转换历史。线程安全。"""

    def __init__(self, path: Path | None = None, keep: int = MAX_HISTORY_LINES) -> None:
        self.path = Path(path) if path else DEFAULT_LOG_DIR / "history.jsonl"
        self.keep = keep
        self._lock = threading.Lock()

    # ------------------------------------------------------------ 写入
    def add(self, record: dict[str, Any]) -> dict[str, Any]:
        record = {**record, "timestamp": record.get("timestamp") or _now_iso()}
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(line + "\n")
            self._trim_if_needed()
        return record

    def _trim_if_needed(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError:
            return
        if len(lines) <= self.keep:
            return
        with open(self.path, "w", encoding="utf-8", newline="\n") as fh:
            fh.writelines(lines[-self.keep :])

    # ------------------------------------------------------------ 读取
    def list(self, limit: int = 50, status: str | None = None) -> list[dict[str, Any]]:
        """最近 ``limit`` 条（新 → 旧）。"""
        records = self._read_all()
        if status:
            records = [r for r in records if r.get("status") == status]
        records.reverse()
        return records[: max(1, int(limit))]

    def stats(self) -> dict[str, Any]:
        records = self._read_all()
        ok = sum(1 for r in records if r.get("status") == "completed")
        failed = sum(1 for r in records if r.get("status") == "failed")
        durations = [r.get("duration_ms", 0) for r in records if r.get("status") == "completed"]
        return {
            "total": len(records),
            "completed": ok,
            "failed": failed,
            "success_rate": round(ok / len(records) * 100, 1) if records else 0.0,
            "avg_duration_ms": round(sum(durations) / len(durations), 2) if durations else 0.0,
        }

    def _read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        try:
            with open(self.path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue  # 坏行跳过，不影响其他记录
        except OSError:
            return []
        return records


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ------------------------------------------------------------------ 日志
_configured = False


def setup_logging(log_dir: Path | None = None, level: int = logging.INFO) -> Path:
    """
    配置根日志：控制台 + 轮转文件。重复调用只生效一次。

    Returns:
        日志文件路径
    """
    global _configured
    directory = Path(log_dir) if log_dir else Path(os.environ.get("FCONV_LOG_DIR", DEFAULT_LOG_DIR))
    log_file = directory / "fconv.log"

    root = logging.getLogger()
    if _configured:
        return log_file

    directory.mkdir(parents=True, exist_ok=True)
    root.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root.addHandler(stream)

    _configured = True
    return log_file


def get_history_store() -> HistoryStore:
    """全局历史记录单例。"""
    global _history
    if _history is None:
        _history = HistoryStore()
    return _history


_history: HistoryStore | None = None
