"""
批量转换、历史记录、路由与错误码测试。
"""
from __future__ import annotations

import json

import pytest
from PIL import Image

from fconv.batch import BatchConverter
from fconv.core import ErrorCode, get_error_message
from fconv.history import HistoryStore
from fconv.router import ConversionRouter, get_router, normalize_format


# ------------------------------------------------------------------ 路由
def test_normalize_alias():
    assert normalize_format("JPEG") == "jpg"
    assert normalize_format(".htm") == "html"
    assert normalize_format("yml") == "yaml"
    assert normalize_format(None) is None


def test_router_reports_unsupported_pair(tmp_path):
    src = tmp_path / "a.png"
    Image.new("RGB", (4, 4)).save(src)
    result = get_router().convert(src, tmp_path / "a.mp4")
    assert not result.ok
    assert result.error_code is ErrorCode.FORMAT_NOT_SUPPORTED


def test_router_never_raises_on_broken_input(tmp_path):
    """转换器内部炸了也要变成 ConvertResult，而不是抛异常。"""
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not an image at all")
    result = get_router().convert(broken, tmp_path / "out.jpg")
    assert not result.ok
    assert result.error_code is not None


def test_router_file_empty(tmp_path):
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    result = get_router().convert(empty, tmp_path / "out.jpg")
    assert result.error_code is ErrorCode.FILE_EMPTY


def test_error_message_lookup():
    assert "格式" in get_error_message(ErrorCode.FORMAT_NOT_SUPPORTED)
    assert get_error_message(None)  # 不炸


# ------------------------------------------------------------------ 批量
def _make_pngs(tmp_path, count=5):
    paths = []
    for i in range(count):
        p = tmp_path / f"pic_{i}.png"
        Image.new("RGB", (12, 12), (i * 20, 60, 200)).save(p)
        paths.append(p)
    return paths


def test_batch_keeps_input_order(tmp_path):
    files = _make_pngs(tmp_path, 6)
    results = BatchConverter(max_workers=4).convert(files, "jpg")
    assert [r.input_path.name for r in results] == [f.name for f in files]
    assert all(r.ok for r in results)


def test_batch_output_dir(tmp_path):
    files = _make_pngs(tmp_path, 3)
    out_dir = tmp_path / "出 目录"    # 中文 + 空格路径
    results = BatchConverter(max_workers=2).convert(files, "webp", output_dir=out_dir)
    assert all(r.ok for r in results)
    for item in results:
        assert item.output_path is not None
        assert item.output_path.parent == out_dir


def test_batch_mixed_inputs(tmp_path):
    files = _make_pngs(tmp_path, 2)
    broken = tmp_path / "坏文件.png"
    broken.write_bytes(b"broken !!")
    empty = tmp_path / "空文件.png"
    empty.write_bytes(b"")

    results = BatchConverter(max_workers=3).convert([*files, broken, empty], "jpg")
    status = {r.input_path.name: r for r in results}
    assert status["pic_0.png"].ok
    assert not status["坏文件.png"].ok
    assert status["坏文件.png"].error_code is not None
    assert not status["空文件.png"].ok
    assert status["空文件.png"].error_message == "文件为空"


def test_batch_and_pack_zip(tmp_path):
    files = _make_pngs(tmp_path, 4)
    results, zip_path = BatchConverter().convert_and_pack(files, "jpg")
    assert zip_path is not None and zip_path.exists()

    import zipfile

    with zipfile.ZipFile(zip_path) as archive:
        assert len(archive.namelist()) == 4


def test_batch_empty_input(tmp_path):
    assert BatchConverter().convert([], "jpg") == []


# ------------------------------------------------------------------ 历史
def test_history_store_roundtrip(tmp_path):
    store = HistoryStore(path=tmp_path / "history.jsonl")
    store.add({"source_name": "a.png", "status": "completed", "duration_ms": 12.5})
    store.add({"source_name": "b.png", "status": "failed", "error": "坏了"})

    items = store.list(limit=10)
    assert len(items) == 2
    assert items[0]["source_name"] == "b.png"      # 新 → 旧
    assert items[0]["timestamp"]                   # 自动补时间戳

    stats = store.stats()
    assert stats["total"] == 2
    assert stats["completed"] == 1
    assert stats["failed"] == 1
    assert stats["success_rate"] == 50.0

    assert len(store.list(status="failed")) == 1


def test_history_survives_broken_line(tmp_path):
    path = tmp_path / "history.jsonl"
    path.write_text(
        json.dumps({"source_name": "ok", "status": "completed"}) + "\n这不是 JSON\n",
        encoding="utf-8",
    )
    store = HistoryStore(path=path)
    assert len(store.list()) == 1


def test_history_trim(tmp_path):
    store = HistoryStore(path=tmp_path / "history.jsonl", keep=5)
    for i in range(12):
        store.add({"source_name": f"{i}.png", "status": "completed"})
    assert len(store.list(limit=100)) == 5
