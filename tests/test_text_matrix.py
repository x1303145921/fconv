"""
文本转换矩阵测试：TXT / MD / HTML / JSON / CSV / XML / YAML 共 49 个方向。

目标：**每个方向都产出与目标扩展名匹配的可用内容**，不再出现「原样拷贝但扩展名不对」。
"""
from __future__ import annotations

import json

import pytest

from fconv.converters.text import TextConverter

FORMATS = ["txt", "md", "html", "json", "csv", "xml", "yaml"]

SAMPLES = {
    "txt": "标题\n\n第一段内容\n第二行",
    "md": "# 标题\n\n正文一段\n\n- 条目一\n- 条目二",
    "html": "<html><body><h1>标题</h1><p>正文内容</p></body></html>",
    "json": json.dumps(
        [{"name": "Alice", "age": 25}, {"name": "Bob", "age": 30}], ensure_ascii=False
    ),
    "csv": "name,age\r\nAlice,25\r\nBob,30\r\n",
    "xml": '<?xml version="1.0"?><root><item><name>Alice</name></item></root>',
    "yaml": "name: Alice\nage: 25\n",
}


@pytest.mark.parametrize("src_ext", FORMATS)
@pytest.mark.parametrize("dst_ext", FORMATS)
def test_text_matrix(tmp_path, src_ext, dst_ext):
    """每个方向都要成功，并且产物能被目标格式解析。"""
    src = tmp_path / f"in.{src_ext}"
    dst = tmp_path / f"out.{dst_ext}"
    src.write_text(SAMPLES[src_ext], encoding="utf-8")

    result = TextConverter().convert(src, dst)
    assert result.ok, f"{src_ext}->{dst_ext} 失败：{result.message}"
    assert dst.exists()

    text = dst.read_text(encoding="utf-8")
    assert text.strip(), f"{src_ext}->{dst_ext} 产物为空"

    # 结构化格式做一次真解析
    if dst_ext == "json":
        json.loads(text)
    elif dst_ext == "csv":
        import csv
        import io

        rows = list(csv.reader(io.StringIO(text)))
        assert rows, "CSV 至少要有表头"
    elif dst_ext == "xml":
        import xml.etree.ElementTree as ET

        ET.fromstring(text)
    elif dst_ext == "yaml":
        yaml = pytest.importorskip("yaml")
        yaml.safe_load(text)
    elif dst_ext == "html":
        assert "<html" in text.lower()


def test_text_to_csv_is_real_csv(tmp_path):
    """旧版把 txt 直接拷贝成 .csv；现在必须是真正的 CSV。"""
    src = tmp_path / "in.txt"
    src.write_text("第一行\n第二行", encoding="utf-8")
    dst = tmp_path / "out.csv"
    assert TextConverter().convert(src, dst).ok

    content = dst.read_text(encoding="utf-8")
    assert content != src.read_text(encoding="utf-8"), "不应该原样拷贝"
    lines = [line for line in content.splitlines() if line.strip()]
    assert lines[0] == "value", "单列 CSV 应有表头"
    assert "第一行" in content


def test_json_to_csv_roundtrip(tmp_path):
    """JSON → CSV → JSON 数据不丢。"""
    data = [{"name": "Alice", "age": 25}, {"name": "Bob", "age": 30}]
    src = tmp_path / "data.json"
    src.write_text(json.dumps(data), encoding="utf-8")

    mid = tmp_path / "data.csv"
    assert TextConverter().convert(src, mid).ok
    back = tmp_path / "back.json"
    assert TextConverter().convert(mid, back).ok

    restored = json.loads(back.read_text(encoding="utf-8"))
    assert restored[0]["name"] == "Alice"
    assert len(restored) == 2


def test_html_strip_removes_script(tmp_path):
    src = tmp_path / "page.html"
    src.write_text(
        "<html><head><style>p{color:red}</style><script>alert(1)</script></head>"
        "<body><h1>标题</h1><p>正文</p></body></html>",
        encoding="utf-8",
    )
    dst = tmp_path / "page.txt"
    assert TextConverter().convert(src, dst).ok
    text = dst.read_text(encoding="utf-8")
    assert "alert" not in text
    assert "color:red" not in text
    assert "标题" in text


def test_bad_json_reports_line(tmp_path):
    src = tmp_path / "broken.json"
    src.write_text('{"a": 1,,}', encoding="utf-8")
    dst = tmp_path / "out.csv"
    result = TextConverter().convert(src, dst)
    assert not result.ok
    assert result.error_code is not None
    assert "JSON" in result.message


def test_unsupported_target(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("hello", encoding="utf-8")
    dst = tmp_path / "a.docx"
    result = TextConverter().convert(src, dst)
    assert not result.ok
    assert result.error_code is not None
