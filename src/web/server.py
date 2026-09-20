"""
fconv Web 服务 - Flask 后端。

接口一览
--------
| 方法 | 路径 | 说明 |
|---|---|---|
| GET  | `/` | 单页界面 |
| GET  | `/assets/<file>` `/favicon.ico` | 图标等静态资源 |
| GET  | `/api/health` | 健康检查（含版本号） |
| GET  | `/api/formats` | 支持的格式与可达目标 |
| POST | `/api/convert` | 单文件转换（异步，返回 task_id） |
| GET  | `/api/tasks/<id>` | 查询任务状态 |
| GET  | `/api/download/<id>` | 下载转换结果 |
| POST | `/api/batch-convert` | 批量转换（并发 + ZIP 打包） |
| GET  | `/api/download-batch/<zip>` | 下载批量打包结果 |
| GET  | `/api/history` | 转换历史（持久化，可翻页/过滤） |
| GET  | `/api/stats` | 统计信息 |
| POST | `/api/benchmark` | 内置性能自测 |

设计约束
--------
* 所有错误都以 JSON 返回，前端永远拿得到可读的中文提示；
* 上传文件名做净化，杜绝 ``../`` 之类的路径穿越；
* 每次转换落一条历史记录（``logs/history.jsonl``），运行日志写 ``logs/fconv.log``。
"""
from __future__ import annotations

import concurrent.futures
import logging
import os
import re
import shutil
import sys
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any

# 允许直接 `python src/web/server.py` 启动（便携版启动脚本就是这么跑的）
_SRC_DIR = Path(__file__).resolve().parents[1]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from flask import Flask, jsonify, request, send_file, send_from_directory  # noqa: E402

from fconv import __version__
from fconv.core import ErrorCode, get_error_message
from fconv.history import get_history_store, setup_logging
from fconv.router import get_router
from fconv.sniffer import get_sniffer

# ------------------------------------------------------------------ 基础配置
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "assets"
UPLOAD_DIR = PROJECT_ROOT / "src" / "uploads"

DEFAULT_PORT = int(os.environ.get("FCONV_PORT", "8765"))
MAX_CONTENT_LENGTH = 200 * 1024 * 1024          # 单请求上限 200MB
UPLOAD_TTL_HOURS = 24                           # 上传/产物保留时长
MAX_TASK_RECORDS = 500                          # 内存里保留的任务条数

app = Flask(__name__, static_folder=".", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.config["JSON_AS_ASCII"] = False

log_file = setup_logging()
logger = logging.getLogger("fconv.web")

history = get_history_store()

# 内存任务表：task_id -> 任务信息（历史另有持久化副本）
_tasks: dict[str, dict[str, Any]] = {}
_tasks_lock = threading.Lock()

_SAFE_NAME_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff\u3040-\u30ff._\- ()\[\]（）]+")


# ------------------------------------------------------------------ 工具函数
def sanitize_filename(name: str, fallback: str = "file") -> str:
    """
    净化上传文件名：去掉路径部分与危险字符，保留中文。

    ``../../etc/passwd`` → ``passwd``；``a<b>:c?.png`` → ``abc.png``
    """
    base = Path(name or "").name.replace("\\", "/").split("/")[-1]
    base = _SAFE_NAME_RE.sub("", base).strip(" .")
    if not base or base in {".", ".."}:
        base = fallback
    if len(base) > 120:  # 保留扩展名，截断主干
        stem, dot, suffix = base.rpartition(".")
        base = (stem[:110] + dot + suffix[:9]) if dot else base[:120]
    return base


def json_error(message: str, status: int = 400, code: str | None = None):
    payload: dict[str, Any] = {"ok": False, "error": message}
    if code:
        payload["error_code"] = code
    return jsonify(payload), status


def record_history(**fields: Any) -> None:
    try:
        history.add(fields)
    except Exception:  # 历史写失败不能影响主流程
        logger.exception("写转换历史失败")


def cleanup_uploads(max_age_hours: int = UPLOAD_TTL_HOURS) -> int:
    """清掉过期的上传件与产物（含每个任务的子目录），返回删除的条目数。"""
    if not UPLOAD_DIR.exists():
        return 0
    deadline = time.time() - max_age_hours * 3600
    removed = 0
    for item in UPLOAD_DIR.iterdir():
        try:
            if item.stat().st_mtime >= deadline:
                continue
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink()
            removed += 1
        except OSError:
            continue
    if removed:
        logger.info("清理过期上传文件 %d 项", removed)
    return removed


def _remember_task(task_id: str, payload: dict[str, Any]) -> None:
    with _tasks_lock:
        _tasks[task_id] = payload
        if len(_tasks) > MAX_TASK_RECORDS:  # 简单淘汰最旧的
            for key in list(_tasks)[: len(_tasks) - MAX_TASK_RECORDS]:
                _tasks.pop(key, None)


def _describe(path: Path, fmt: str | None = None) -> str | None:
    return fmt or get_sniffer().detect(path)


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


# ------------------------------------------------------------------ 路由
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/assets/<path:filename>")
def assets(filename: str):
    return send_from_directory(ASSETS_DIR, filename)


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(ASSETS_DIR, "favicon.ico")


@app.route("/api/health")
def api_health():
    return jsonify(
        {
            "ok": True,
            "service": "fconv",
            "version": __version__,
            "ffmpeg": _ffmpeg_status(),
        }
    )


def _ffmpeg_status() -> bool:
    try:
        from fconv.ffmpeg import ffmpeg_available

        return ffmpeg_available()
    except Exception:  # noqa: BLE001
        return False


@app.route("/api/formats")
def api_formats():
    return jsonify(get_router().get_supported_formats())


@app.route("/api/convert", methods=["POST"])
def api_convert():
    """单文件转换：立刻返回 task_id，后台线程干活。"""
    file = request.files.get("file")
    if file is None or not file.filename:
        return json_error("未收到文件，请重新选择", 400, "invalid_input")

    target_format = request.form.get("format", "").strip().lower().lstrip(".")
    try:
        quality = int(request.form.get("quality", 92))
    except (TypeError, ValueError):
        quality = 92

    task_id = uuid.uuid4().hex[:8]
    safe_name = sanitize_filename(file.filename)
    # 每个任务一个子目录：磁盘路径带任务号，但出错提示里仍是用户原本的文件名
    task_dir = UPLOAD_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    src_path = task_dir / safe_name
    try:
        file.save(src_path)
    except OSError as exc:
        logger.error("保存上传文件失败：%s", exc)
        return json_error(f"保存上传文件失败：{exc}", 500, "conversion_failed")

    dst_ext = target_format or Path(safe_name).suffix.lstrip(".").lower()
    dst_path = task_dir / f"output.{dst_ext}" if dst_ext else task_dir / "output"

    source_format = _describe(src_path)
    _remember_task(
        task_id,
        {
            "status": "processing",
            "file": safe_name,
            "source_format": source_format,
            "target_format": dst_ext,
            "progress": 0,
            "result": None,
            "error": None,
        },
    )

    def worker() -> None:
        started = time.perf_counter()
        result = get_router().convert(src_path, dst_path, quality=quality)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

        output_info = None
        if result.ok and result.output_path and result.output_path.exists():
            output_path = result.output_path
            download_name = output_path.name
            if output_path.suffix != ".zip":
                download_name = f"{Path(safe_name).stem}{output_path.suffix}"
            output_info = {
                "path": str(output_path),
                "filename": download_name,
                "size": output_path.stat().st_size,
            }

        _remember_task(
            task_id,
            {
                "status": "completed" if result.ok else "failed",
                "file": safe_name,
                "source_format": source_format,
                "target_format": dst_ext,
                "progress": 100 if result.ok else 0,
                "result": {
                    "ok": result.ok,
                    "duration_ms": elapsed_ms,
                    "output": output_info,
                },
                "error": None if result.ok else result.message,
            },
        )
        record_history(
            task_id=task_id,
            kind="single",
            source_name=safe_name,
            source_format=source_format,
            target_format=dst_ext,
            status="completed" if result.ok else "failed",
            error=None if result.ok else result.message,
            error_code=result.error_code.value if result.error_code else None,
            duration_ms=elapsed_ms,
            bytes_in=_safe_size(src_path),
            bytes_out=output_info["size"] if output_info else 0,
        )

    threading.Thread(target=worker, name=f"fconv-{task_id}", daemon=True).start()
    return jsonify({"task_id": task_id, "status": "processing", "file": safe_name})


@app.route("/api/tasks/<task_id>")
def api_task_status(task_id: str):
    with _tasks_lock:
        task = _tasks.get(task_id)
        task = dict(task) if task else None
    if task is None:
        return json_error("任务不存在（可能已过期，历史记录里仍可查）", 404, "not_found")
    return jsonify(task)


@app.route("/api/download/<task_id>")
def api_download(task_id: str):
    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        return json_error("任务不存在", 404, "not_found")
    output = (task.get("result") or {}).get("output")
    if not output:
        return json_error("任务尚未产出文件", 404, "not_found")
    path = Path(output["path"])
    if not path.exists():
        return json_error("输出文件已被清理，请重新转换", 404, "not_found")
    return send_file(path, as_attachment=True, download_name=output["filename"])


@app.route("/api/batch-convert", methods=["POST"])
def api_batch_convert():
    files = [f for f in request.files.getlist("files") if f and f.filename]
    if not files:
        return json_error("未收到文件，请重新选择", 400, "invalid_input")

    target_format = request.form.get("format", "").strip().lower().lstrip(".")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    jobs: list[tuple[Path, str, str, str]] = []  # (src, 原始名, 安全名, task_id)
    for file in files:
        task_id = uuid.uuid4().hex[:8]
        safe_name = sanitize_filename(file.filename)
        task_dir = UPLOAD_DIR / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        src_path = task_dir / safe_name
        try:
            file.save(src_path)
        except OSError as exc:
            logger.error("保存上传文件失败：%s", exc)
            continue
        jobs.append((src_path, file.filename, safe_name, task_id))

    if not jobs:
        return json_error("文件保存失败，请重试", 500, "conversion_failed")

    workers = max(1, min(8, len(jobs)))

    def convert_one(job: tuple[Path, str, str, str]) -> dict[str, Any]:
        src_path, _original, safe_name, task_id = job
        dst_ext = target_format or Path(safe_name).suffix.lstrip(".").lower()
        dst_path = src_path.parent / (f"output.{dst_ext}" if dst_ext else "output")
        started = time.perf_counter()
        result = get_router().convert(src_path, dst_path)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "task_id": task_id,
            "file": safe_name,
            "source_format": _describe(src_path),
            "target_format": dst_ext,
            "ok": result.ok,
            "status": "completed" if result.ok else "failed",
            "error": None if result.ok else result.message,
            "error_code": result.error_code.value if result.error_code else None,
            "duration_ms": elapsed_ms,
            "output_path": str(result.output_path) if result.output_path else None,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(convert_one, jobs))

    for item in results:
        record_history(
            task_id=item["task_id"],
            kind="batch",
            source_name=item["file"],
            source_format=item["source_format"],
            target_format=item["target_format"],
            status=item["status"],
            error=item["error"],
            error_code=item["error_code"],
            duration_ms=item["duration_ms"],
        )

    success_count = sum(1 for item in results if item["ok"])
    summary = {
        "total": len(results),
        "success": success_count,
        "failed": len(results) - success_count,
    }

    download = None
    if success_count:
        zip_path = UPLOAD_DIR / f"batch_{uuid.uuid4().hex[:8]}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            used: set[str] = set()
            for item in results:
                if not item["ok"] or not item["output_path"]:
                    continue
                output_path = Path(item["output_path"])
                if not output_path.exists():
                    continue
                name = output_path.name
                if name in used:
                    name = f"{output_path.stem}_{len(used)}{output_path.suffix}"
                used.add(name)
                archive.write(output_path, name)
        download = {
            "path": str(zip_path),
            "filename": zip_path.name,
            "size": zip_path.stat().st_size,
        }

    status_code = 200 if success_count == len(results) else 207  # 207 Multi-Status：部分失败
    return jsonify({"results": results, "download": download, "summary": summary}), status_code


@app.route("/api/download-batch/<path:filename>")
def api_download_batch(filename: str):
    safe = Path(filename).name
    if not safe.startswith("batch_") or not safe.endswith(".zip"):
        return json_error("非法文件名", 400, "invalid_input")
    target = UPLOAD_DIR / safe
    if not target.exists():
        return json_error("打包文件不存在或已过期", 404, "not_found")
    return send_file(target, as_attachment=True, download_name=safe)


@app.route("/api/history")
def api_history():
    """转换历史（持久化），支持 limit / status 过滤。"""
    try:
        limit = max(1, min(200, int(request.args.get("limit", 20))))
    except (TypeError, ValueError):
        limit = 20
    status = request.args.get("status")
    if status not in (None, "", "completed", "failed"):
        status = None
    return jsonify(
        {
            "items": history.list(limit=limit, status=status or None),
            "summary": history.stats(),
            "log_file": str(log_file),
        }
    )


@app.route("/api/stats")
def api_stats():
    router = get_router()
    formats = router.get_supported_formats()
    return jsonify(
        {
            "version": __version__,
            "supported_formats": sorted(formats.keys()),
            "total_format_pairs": sum(len(targets) for targets in formats.values()),
            "active_tasks": sum(1 for t in _tasks.values() if t["status"] == "processing"),
            "completed_tasks": sum(1 for t in _tasks.values() if t["status"] == "completed"),
            "failed_tasks": sum(1 for t in _tasks.values() if t["status"] == "failed"),
            "history": history.stats(),
            "ffmpeg_available": _ffmpeg_status(),
        }
    )


@app.route("/api/benchmark", methods=["POST"])
def api_benchmark():
    """内置小基准：跑一遍图片/文本转换，返回每条耗时。"""
    from PIL import Image as PILImage
    import json as json_module

    router = get_router()
    temp_dir = PROJECT_ROOT / "benchmarks"
    temp_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    image_cases = [
        ("png_to_jpg", "png", "jpg", (200, 150)),
        ("png_to_webp", "png", "webp", (200, 150)),
        ("jpg_to_png", "jpg", "png", (800, 600)),
        ("large_jpg_to_png", "jpg", "png", (1920, 1080)),
    ]
    for name, src_ext, dst_ext, size in image_cases:
        src = temp_dir / f"api_bench_{name}.{src_ext}"
        dst = temp_dir / f"api_bench_{name}_out.{dst_ext}"
        PILImage.new("RGB", size, color=(200, 60, 60)).save(src)
        started = time.perf_counter()
        result = router.convert(src, dst)
        results.append(
            {
                "name": name,
                "type": "image",
                "ok": result.ok,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "input_size": f"{size[0]}x{size[1]}",
                "error": result.message if not result.ok else None,
            }
        )
        src.unlink(missing_ok=True)
        dst.unlink(missing_ok=True)

    text_cases = [
        ("json_to_csv_small", "json", "csv", [{"name": f"user_{i}", "value": i} for i in range(10)]),
        ("json_to_csv_large", "json", "csv", [{"id": i, "name": f"user_{i}"} for i in range(1000)]),
        ("html_to_txt", "html", "txt", "<html><body><h1>Test</h1><p>Hello World</p></body></html>"),
    ]
    for name, src_ext, dst_ext, data in text_cases:
        src = temp_dir / f"api_bench_{name}.{src_ext}"
        dst = temp_dir / f"api_bench_{name}_out.{dst_ext}"
        src.write_text(
            json_module.dumps(data, indent=2) if isinstance(data, list) else data, encoding="utf-8"
        )
        started = time.perf_counter()
        result = router.convert(src, dst)
        results.append(
            {
                "name": name,
                "type": "text",
                "ok": result.ok,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "error": result.message if not result.ok else None,
            }
        )
        src.unlink(missing_ok=True)
        dst.unlink(missing_ok=True)

    passed = sum(1 for item in results if item["ok"])
    return jsonify(
        {
            "results": results,
            "summary": {
                "total": len(results),
                "passed": passed,
                "failed": len(results) - passed,
                "avg_duration_ms": round(
                    sum(item["duration_ms"] for item in results) / len(results), 2
                )
                if results
                else 0,
            },
        }
    )


# ------------------------------------------------------------------ 错误处理
@app.errorhandler(404)
def handle_404(error):
    if request.path.startswith("/api/"):
        return json_error("接口不存在", 404, "not_found")
    return error


@app.errorhandler(413)
def handle_413(error):
    limit_mb = MAX_CONTENT_LENGTH // (1024 * 1024)
    return json_error(
        f"文件超过 {limit_mb}MB 上限，请先拆分或压缩后再试", 413, ErrorCode.FILE_TOO_LARGE.value
    )


@app.errorhandler(500)
def handle_500(error):
    logger.exception("服务器内部错误：%s", error)
    return json_error("服务器内部错误，请查看 logs/fconv.log", 500, "unknown_error")


@app.errorhandler(Exception)
def handle_uncaught(error):
    from werkzeug.exceptions import HTTPException

    if isinstance(error, HTTPException):
        if request.path.startswith("/api/"):
            return json_error(error.description or error.name, error.code or 500, "unknown_error")
        return error
    logger.exception("未捕获异常：%s", error)
    return json_error(f"处理失败：{error}", 500, ErrorCode.CONVERSION_FAILED.value)


# ------------------------------------------------------------------ 启动
def create_app() -> Flask:
    """给 WSGI 部署用的工厂函数（在 src 目录下：``gunicorn web.server:create_app``）。"""
    return app


def run_server(host: str = "127.0.0.1", port: int | None = None, debug: bool = False) -> None:
    port = port or DEFAULT_PORT
    # 启动横幅带中文：Windows 控制台若是 cp1252 等窄编码会直接抛 UnicodeEncodeError，
    # 先把标准输出改成 UTF-8。
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):  # pragma: no cover - 非文本流时跳过
            pass
    cleanup_uploads()
    logger.info("启动 fconv %s：http://%s:%s（日志：%s）", __version__, host, port, log_file)
    print(f"[fconv] v{__version__} 已启动: http://{host}:{port}")
    print(f"[fconv] 日志: {log_file}")
    print("[fconv] 关闭此窗口即停止服务。")
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    run_server(port=DEFAULT_PORT)
