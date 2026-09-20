"""
嗅探器边界测试：改名文件、RIFF 三种容器、ZIP 型 Office 文档、编码回退。
"""
from __future__ import annotations

import io

import pytest
from PIL import Image

from fconv.sniffer import FileSniffer

sniffer = FileSniffer()


def test_renamed_jpeg_reported_as_jpg(tmp_path):
    """把 JPEG 改名成 .png —— 魔数优先，必须报 jpg。"""
    fake = tmp_path / "骗人的.png"
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, format="JPEG")
    fake.write_bytes(buf.getvalue())
    assert sniffer.detect(fake) == "jpg"


def test_riff_containers_not_confused(tmp_path):
    """RIFF 家族的 WAV / AVI / WebP 不能互相误判（旧版字典覆盖 bug）。"""
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF" + (36).to_bytes(4, "little") + b"WAVE" + b"fmt " + b"\x00" * 40)
    avi = tmp_path / "b.avi"
    avi.write_bytes(b"RIFF" + (36).to_bytes(4, "little") + b"AVI " + b"LIST" + b"\x00" * 40)
    webp = tmp_path / "c.webp"
    webp.write_bytes(b"RIFF" + (36).to_bytes(4, "little") + b"WEBP" + b"VP8 " + b"\x00" * 40)

    assert sniffer.detect(wav) == "wav"
    assert sniffer.detect(avi) == "avi"
    assert sniffer.detect(webp) == "webp"


def test_mp4_and_mov_brands(tmp_path):
    mp4 = tmp_path / "v.mp4"
    mp4.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32)
    mov = tmp_path / "v.mov"
    mov.write_bytes(b"\x00\x00\x00\x14ftypqt  " + b"\x00" * 32)
    assert sniffer.detect(mp4) == "mp4"
    assert sniffer.detect(mov) == "mov"


def test_ebml_webm_not_reported_as_mkv(tmp_path):
    """EBML 容器：.webm 与 .mkv 文件头完全一样，只能用扩展名区分。

    旧实现只按魔数返回 mkv，导致 .webm 文件被报成 mkv（界面显示错、批量归类也错）。
    """
    ebml = b"\x1a\x45\xdf\xa3" + b"\x00" * 60
    webm = tmp_path / "v.webm"
    webm.write_bytes(ebml)
    mkv = tmp_path / "v.mkv"
    mkv.write_bytes(ebml)
    assert sniffer.detect(webm) == "webm"
    assert sniffer.detect(mkv) == "mkv"


def test_docx_keeps_office_name(tmp_path):
    """docx 本质是 ZIP，但界面应显示 docx 而不是 zip。"""
    docx = tmp_path / "报告.docx"
    docx.write_bytes(b"PK\x03\x04" + b"\x00" * 64)
    assert sniffer.detect(docx) == "docx"


def test_chinese_and_space_path(tmp_path):
    folder = tmp_path / "带 空格的 目录"
    folder.mkdir()
    target = folder / "示例 图片.png"
    Image.new("RGB", (4, 4), "blue").save(target)
    assert sniffer.detect(target) == "png"


def test_gbk_text_fallback(tmp_path):
    """没有魔数、没有已知扩展名时，按 GBK 兜底解码。"""
    weird = tmp_path / "unknown.dat"
    weird.write_bytes("中文内容测试".encode("gbk"))
    assert sniffer.detect(weird) == "txt"


def test_directory_returns_none(tmp_path):
    assert sniffer.detect(tmp_path) is None


def test_get_extension_is_canonical():
    assert sniffer.get_extension("jpg") == "jpg"
    assert sniffer.get_extension("html") == "html"
    assert sniffer.get_extension("yaml") == "yaml"


@pytest.mark.parametrize("bad", [b"", b"\x00" * 8])
def test_degenerate_files(tmp_path, bad):
    path = tmp_path / "x.bin"
    path.write_bytes(bad)
    assert sniffer.detect(path) in (None, "bin")
