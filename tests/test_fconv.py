"""
fconv 测试套件
"""
from __future__ import annotations
import pytest
from pathlib import Path
import tempfile
import os
import json
import time


# 测试 fixtures 目录
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestFileSniffer:
    """文件嗅探器测试"""

    def test_detect_png(self, tmp_path: Path):
        from fconv.sniffer import FileSniffer
        sniffer = FileSniffer()
        
        # 创建一个简单的 PNG 文件（最小有效 PNG）
        png_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG 签名
            0x00, 0x00, 0x00, 0x0D,  # IHDR 长度
            0x49, 0x48, 0x44, 0x52,  # IHDR
            0x00, 0x00, 0x00, 0x01,  # 宽度 1
            0x00, 0x00, 0x00, 0x01,  # 高度 1
            0x08, 0x02, 0x00, 0x00, 0x00,  # 8位RGB
            0x90, 0x77, 0x53, 0xDE,  # CRC
            0x00, 0x00, 0x00, 0x0C,  # IDAT 长度
            0x49, 0x44, 0x41, 0x54,  # IDAT
            0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00, 0x00, 0x00, 0x02, 0x00, 0x01,
            0xE2, 0x21, 0xBC, 0x33,  # CRC
            0x00, 0x00, 0x00, 0x00,  # IEND 长度
            0x49, 0x45, 0x4E, 0x44,  # IEND
            0xAE, 0x42, 0x60, 0x82,  # CRC
        ])
        
        test_file = tmp_path / "test.png"
        test_file.write_bytes(png_data)
        
        assert sniffer.detect(test_file) == "png"

    def test_detect_jpg(self, tmp_path: Path):
        from fconv.sniffer import FileSniffer
        sniffer = FileSniffer()
        
        # 创建一个简单的 JPEG 文件（最小有效 JPEG）
        jpg_data = bytes([
            0xFF, 0xD8, 0xFF, 0xE0,  # SOI + APP0
            0x00, 0x10,  # length
            0x4A, 0x46, 0x49, 0x46, 0x00,  # JFIF
            0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00,
            0xFF, 0xDB, 0x00, 0x43,  # SOS
            0x00,
        ] + [0x00] * 100)  # 填充数据
        
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(jpg_data)
        
        assert sniffer.detect(test_file) == "jpg"

    def test_detect_by_extension(self, tmp_path: Path):
        from fconv.sniffer import FileSniffer
        sniffer = FileSniffer()
        
        # 测试扩展名检测
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Hello world")
        assert sniffer.detect(txt_file) == "txt"
        
        json_file = tmp_path / "test.json"
        json_file.write_text('{"a": 1}')
        assert sniffer.detect(json_file) == "json"

    def test_detect_nonexistent(self, tmp_path: Path):
        from fconv.sniffer import FileSniffer
        sniffer = FileSniffer()
        
        assert sniffer.detect(tmp_path / "nonexistent.txt") is None

    def test_detect_empty_file(self, tmp_path: Path):
        from fconv.sniffer import FileSniffer
        sniffer = FileSniffer()
        
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")
        assert sniffer.detect(empty_file) is None


class TestImageConverter:
    """图片转换器测试"""

    def test_png_to_jpg(self, tmp_path: Path):
        from fconv.converters.image import ImageConverter
        from PIL import Image
        
        converter = ImageConverter()
        
        # 创建测试图片
        src = tmp_path / "test.png"
        img = Image.new('RGB', (100, 100), color='red')
        img.save(src)
        
        dst = tmp_path / "test.jpg"
        result = converter.convert(src, dst)
        
        assert result.ok
        assert dst.exists()
        assert dst.suffix == '.jpg'

    def test_jpg_to_png(self, tmp_path: Path):
        from fconv.converters.image import ImageConverter
        from PIL import Image
        
        converter = ImageConverter()
        
        src = tmp_path / "test.jpg"
        img = Image.new('RGB', (100, 100), color='blue')
        img.save(src, format='JPEG')
        
        dst = tmp_path / "test.png"
        result = converter.convert(src, dst)
        
        assert result.ok
        assert dst.exists()

    def test_webp_to_png(self, tmp_path: Path):
        from fconv.converters.image import ImageConverter
        from PIL import Image
        
        converter = ImageConverter()
        
        src = tmp_path / "test.webp"
        img = Image.new('RGBA', (50, 50), color=(255, 0, 0, 128))
        img.save(src, format='WEBP')
        
        dst = tmp_path / "test_out.png"
        result = converter.convert(src, dst)
        
        assert result.ok
        assert dst.exists()

    def test_invalid_file(self, tmp_path: Path):
        from fconv.converters.image import ImageConverter
        
        converter = ImageConverter()
        
        src = tmp_path / "not_an_image.txt"
        src.write_text("This is not an image")
        
        dst = tmp_path / "out.png"
        result = converter.convert(src, dst)
        
        assert not result.ok
        assert result.error_code is not None

    def test_gif_conversion(self, tmp_path: Path):
        from fconv.converters.image import ImageConverter
        from PIL import Image
        
        converter = ImageConverter()
        
        src = tmp_path / "test.gif"
        img = Image.new('P', (50, 50), color=1)
        img.save(src, format='GIF')
        
        dst = tmp_path / "test_out.png"
        result = converter.convert(src, dst)
        
        assert result.ok
        assert dst.exists()


class TestTextConverter:
    """文本文档转换器测试"""

    def test_txt_to_html(self, tmp_path: Path):
        from fconv.converters.text import TextConverter
        
        converter = TextConverter()
        
        src = tmp_path / "test.txt"
        src.write_text("# Hello\n\nWorld\n\n- Item 1\n- Item 2")
        
        dst = tmp_path / "test.html"
        result = converter.convert(src, dst)
        
        assert result.ok
        assert dst.exists()
        content = dst.read_text()
        assert "<h1>Hello</h1>" in content
        assert "<p>World</p>" in content

    def test_json_to_csv(self, tmp_path: Path):
        from fconv.converters.text import TextConverter
        
        converter = TextConverter()
        
        data = [{"name": "Alice", "age": 25}, {"name": "Bob", "age": 30}]
        src = tmp_path / "data.json"
        src.write_text(json.dumps(data, indent=2))
        
        dst = tmp_path / "data.csv"
        result = converter.convert(src, dst)
        
        assert result.ok
        assert dst.exists()
        content = dst.read_text()
        assert "name,age" in content
        assert "Alice,25" in content

    def test_csv_to_json(self, tmp_path: Path):
        from fconv.converters.text import TextConverter
        
        converter = TextConverter()
        
        src = tmp_path / "data.csv"
        src.write_text("name,age\nAlice,25\nBob,30\n")
        
        dst = tmp_path / "data.json"
        result = converter.convert(src, dst)
        
        assert result.ok
        assert dst.exists()
        data = json.loads(dst.read_text())
        assert len(data) == 2
        assert data[0]["name"] == "Alice"

    def test_md_to_html(self, tmp_path: Path):
        from fconv.converters.text import TextConverter
        
        converter = TextConverter()
        
        src = tmp_path / "doc.md"
        src.write_text("# Title\n\nParagraph\n\n## Subtitle\n\nMore text")
        
        dst = tmp_path / "doc.html"
        result = converter.convert(src, dst)
        
        assert result.ok
        content = dst.read_text()
        assert "<h1>Title</h1>" in content
        assert "<h2>Subtitle</h2>" in content


class TestRouter:
    """路由表测试"""

    def test_can_convert(self):
        from fconv.router import ConversionRouter
        
        router = ConversionRouter()
        
        # 图片互转
        assert router.can_convert("png", "jpg")
        assert router.can_convert("jpg", "png")
        
        # 文本互转
        assert router.can_convert("json", "csv")
        assert router.can_convert("csv", "json")
        
        # 不支持的转换
        assert not router.can_convert("mp4", "txt")

    def test_get_supported_formats(self):
        from fconv.router import ConversionRouter
        
        router = ConversionRouter()
        formats = router.get_supported_formats()
        
        assert "png" in formats
        assert "jpg" in formats["png"]
        assert "mp4" in formats
        assert "txt" in formats.get("pdf", [])

    def test_convert_png_to_jpg(self, tmp_path: Path):
        from fconv.router import get_router
        from PIL import Image
        
        router = get_router()
        
        src = tmp_path / "test.png"
        img = Image.new('RGB', (100, 100), color='green')
        img.save(src)
        
        dst = tmp_path / "test.jpg"
        result = router.convert(src, dst)
        
        assert result.ok
        assert dst.exists()

    def test_convert_with_auto_detect(self, tmp_path: Path):
        from fconv.router import get_router
        from PIL import Image
        
        router = get_router()
        
        src = tmp_path / "test.jpg"
        img = Image.new('RGB', (50, 50), color='blue')
        img.save(src, format='JPEG')
        
        dst = tmp_path / "test_out.png"
        result = router.convert(src, dst)  # 不指定格式，自动检测
        
        assert result.ok
        assert dst.exists()


class TestCLI:
    """命令行接口测试"""

    def test_version(self, capsys):
        from fconv.cli import main
        import sys
        
        # 保存原始 argv
        orig_argv = sys.argv
        sys.argv = ["fconv", "version"]
        
        try:
            ret = main()
            assert ret == 0
            captured = capsys.readouterr()
            assert "fconv" in captured.out
        finally:
            sys.argv = orig_argv

    def test_formats(self, capsys):
        from fconv.cli import main
        import sys
        
        orig_argv = sys.argv
        sys.argv = ["fconv", "formats"]
        
        try:
            ret = main()
            assert ret == 0
            captured = capsys.readouterr()
            assert "png" in captured.out
        finally:
            sys.argv = orig_argv

    def test_detect_valid_file(self, tmp_path, capsys):
        from fconv.cli import main
        import sys
        
        # 创建测试文件
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello")
        
        orig_argv = sys.argv
        sys.argv = ["fconv", "detect", str(test_file)]
        
        try:
            ret = main()
            assert ret == 0
            captured = capsys.readouterr()
            assert "txt" in captured.out
        finally:
            sys.argv = orig_argv

    def test_detect_nonexistent(self, tmp_path, capsys):
        from fconv.cli import main
        import sys
        
        orig_argv = sys.argv
        sys.argv = ["fconv", "detect", str(tmp_path / "missing.txt")]
        
        try:
            ret = main()
            assert ret == 1
        finally:
            sys.argv = orig_argv


class TestPerformance:
    """性能基准测试"""

    def test_image_conversion_speed(self, tmp_path: Path):
        """测试图片转换速度"""
        from fconv.converters.image import ImageConverter
        
        converter = ImageConverter()
        
        # 创建不同大小的测试图片
        sizes = [(100, 100), (500, 500), (1000, 1000)]
        
        results = {}
        for w, h in sizes:
            src = tmp_path / f"test_{w}x{h}.png"
            from PIL import Image
            img = Image.new('RGB', (w, h), color='red')
            img.save(src)
            
            dst = tmp_path / f"test_{w}x{h}.jpg"
            
            start = time.time()
            result = converter.convert(src, dst)
            elapsed = time.time() - start
            
            assert result.ok
            results[(w, h)] = elapsed
        
        # 记录性能数据
        for (w, h), elapsed in results.items():
            print(f"\n{w}x{h} 图片转换耗时: {elapsed:.4f}秒")
            assert elapsed < 1.0, f"转换耗时过长: {elapsed}"

    def test_batch_conversion(self, tmp_path: Path):
        """测试批量转换性能"""
        from fconv.converters.image import ImageConverter
        
        converter = ImageConverter()
        
        # 创建多个测试图片
        files = []
        for i in range(5):
            src = tmp_path / f"batch_{i}.png"
            from PIL import Image
            img = Image.new('RGB', (100, 100), color=i % 256)
            img.save(src)
            files.append(src)
        
        start = time.time()
        results = []
        for src in files:
            dst = tmp_path / f"{src.stem}.jpg"
            results.append(converter.convert(src, dst))
        elapsed = time.time() - start
        
        # 所有转换成功
        assert all(r.ok for r in results)
        
        avg_time = elapsed / len(results)
        print(f"\n批量转换 {len(files)} 个文件总耗时: {elapsed:.4f}秒，平均: {avg_time:.4f}秒/文件")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
