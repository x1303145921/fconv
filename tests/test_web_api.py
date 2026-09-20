"""
Web API 测试：用 Flask 测试客户端跑，不需要真的起服务、不占端口。

覆盖：健康检查 / 格式表 / 单文件转换全链路 / 批量 / 历史 /
      路径穿越净化 / 损坏文件 / 空请求 / 413 / 404 JSON 化。
"""
from __future__ import annotations

import io
import json
import time

import pytest
from PIL import Image

from fconv import __version__


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """把上传目录指到临时目录，避免污染仓库。"""
    from web import server

    monkeypatch.setattr(server, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(server, "history", server.get_history_store().__class__(path=tmp_path / "history.jsonl"))
    server.app.config.update(TESTING=True)
    return server.app.test_client()


def _png_bytes(color=(200, 40, 40)):
    buf = io.BytesIO()
    Image.new("RGB", (24, 18), color).save(buf, format="PNG")
    return buf.getvalue()


def _wait_task(client, task_id, timeout=15.0):
    deadline = time.time() + timeout
    payload = {}
    while time.time() < deadline:
        payload = client.get(f"/api/tasks/{task_id}").get_json()
        if payload.get("status") in ("completed", "failed"):
            return payload
        time.sleep(0.05)
    return payload


def test_health_reports_version(client):
    data = client.get("/api/health").get_json()
    assert data["ok"] is True
    assert data["version"] == __version__


def test_index_and_assets(client):
    assert client.get("/").status_code == 200
    assert client.get("/assets/icon.svg").status_code == 200
    assert client.get("/favicon.ico").status_code == 200


def test_formats_endpoint(client):
    formats = client.get("/api/formats").get_json()
    assert "png" in formats
    assert "jpg" in formats["png"]


def test_single_convert_flow(client):
    resp = client.post(
        "/api/convert",
        data={"file": (io.BytesIO(_png_bytes()), "演示 图片.png"), "format": "jpg"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    task_id = resp.get_json()["task_id"]

    task = _wait_task(client, task_id)
    assert task["status"] == "completed", task
    assert task["result"]["output"]["size"] > 0

    download = client.get(f"/api/download/{task_id}")
    assert download.status_code == 200
    assert download.data[:2] == b"\xff\xd8"          # JPEG 魔数
    assert "attachment" in download.headers["Content-Disposition"]


def test_convert_writes_history(client):
    resp = client.post(
        "/api/convert",
        data={"file": (io.BytesIO(_png_bytes()), "h.png"), "format": "webp"},
        content_type="multipart/form-data",
    )
    task_id = resp.get_json()["task_id"]
    _wait_task(client, task_id)

    history = client.get("/api/history?limit=5").get_json()
    assert history["items"], "历史记录应有内容"
    first = history["items"][0]
    assert first["source_name"] == "h.png"
    assert first["target_format"] == "webp"
    assert first["status"] == "completed"
    assert first["timestamp"]
    assert history["summary"]["total"] >= 1


def test_broken_file_fails_gracefully(client):
    resp = client.post(
        "/api/convert",
        data={"file": (io.BytesIO(b"definitely not an image"), "broken.jpg"), "format": "png"},
        content_type="multipart/form-data",
    )
    task_id = resp.get_json()["task_id"]
    task = _wait_task(client, task_id)
    assert task["status"] == "failed"
    assert task["error"]


def test_path_traversal_is_sanitized(client):
    from web.server import sanitize_filename

    assert sanitize_filename("../../windows/win.ini") == "win.ini"
    assert sanitize_filename("..\\..\\evil.exe") == "evil.exe"
    assert sanitize_filename("正常 文件.png") == "正常 文件.png"
    assert sanitize_filename("") == "file"
    assert sanitize_filename(":::") == "file"

    resp = client.post(
        "/api/convert",
        data={"file": (io.BytesIO(_png_bytes()), "../../escape.png"), "format": "jpg"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert resp.get_json()["file"] == "escape.png"


def test_empty_request_rejected(client):
    assert client.post("/api/convert", data={}, content_type="multipart/form-data").status_code == 400
    assert client.post("/api/batch-convert", data={}, content_type="multipart/form-data").status_code == 400


def test_batch_convert_and_download(client):
    data = {
        "files": [(io.BytesIO(_png_bytes((i * 30, 60, 200))), f"b{i}.png") for i in range(3)],
        "format": "jpg",
    }
    resp = client.post("/api/batch-convert", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["summary"] == {"total": 3, "success": 3, "failed": 0}
    assert payload["download"]["filename"].startswith("batch_")

    zip_resp = client.get("/api/download-batch/" + payload["download"]["filename"])
    assert zip_resp.status_code == 200
    assert zip_resp.data[:2] == b"PK"

    # 非法文件名
    assert client.get("/api/download-batch/乱来.zip").status_code == 400


def test_batch_partial_failure_returns_207(client):
    data = {
        "files": [
            (io.BytesIO(_png_bytes()), "good.png"),
            (io.BytesIO(b"junk"), "bad.png"),
        ],
        "format": "jpg",
    }
    resp = client.post("/api/batch-convert", data=data, content_type="multipart/form-data")
    assert resp.status_code == 207
    payload = resp.get_json()
    assert payload["summary"]["success"] == 1
    assert payload["summary"]["failed"] == 1
    by_name = {r["file"]: r for r in payload["results"]}
    assert by_name["bad.png"]["error"]


def test_unknown_api_returns_json_404(client):
    resp = client.get("/api/does-not-exist")
    assert resp.status_code == 404
    assert resp.is_json
    assert resp.get_json()["ok"] is False


def test_stats_endpoint(client):
    data = client.get("/api/stats").get_json()
    assert data["version"] == __version__
    assert data["total_format_pairs"] > 0
    assert "history" in data


def test_benchmark_endpoint(client):
    data = client.post("/api/benchmark").get_json()
    assert data["summary"]["failed"] == 0
    assert data["summary"]["total"] >= 5


def test_missing_task_returns_json_404(client):
    resp = client.get("/api/tasks/deadbeef")
    assert resp.status_code == 404
    assert resp.is_json
    assert "不存在" in resp.get_json()["error"]
