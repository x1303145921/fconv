"""
PDF 转换器。

* PDF → TXT / MD：用 pypdf 抽文字（纯 Python，必装依赖）
* PDF → HTML：抽文字后套一层可读的 HTML 模板
* PDF → PNG / JPG：按页渲染成图片，需要可选的 PyMuPDF（AGPL，未随包分发）；
  多页 PDF 会打包成 ZIP。缺少依赖时**明确报缺组件**，不会产出坏文件。
"""
from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from typing import Any

from ..core import Converter, ConvertResult, ErrorCode, Timer

logger = logging.getLogger(__name__)

IMAGE_SUFFIXES = {"png", "jpg", "jpeg"}
TEXT_SUFFIXES = {"txt", "md"}

HTML_CSS = (
    "body{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;"
    "max-width:820px;margin:40px auto;padding:0 20px;line-height:1.7;color:#111}"
    ".page{margin:0 0 36px;padding-bottom:24px;border-bottom:1px solid #e5e5e5}"
    ".page h2{font-size:15px;font-weight:600;color:#666;margin:0 0 12px}"
    "pre{white-space:pre-wrap;word-break:break-word;font-size:14px;color:#222;margin:0}"
)


class PDFConverter(Converter):
    """PDF → 文本 / 图片 / HTML。"""

    source_formats = ["pdf"]
    target_formats = ["txt", "md", "jpg", "jpeg", "png", "html"]

    def convert(self, src: Path, dst: Path, **options: Any) -> ConvertResult:
        src, dst = Path(src), Path(dst)
        ext = dst.suffix.lower().lstrip(".")

        with Timer() as timer:
            if ext in TEXT_SUFFIXES:
                result = self._extract_text(src, dst, ext)
            elif ext in IMAGE_SUFFIXES:
                result = self._extract_images(src, dst, ext)
            elif ext == "html":
                result = self._extract_to_html(src, dst)
            else:
                result = ConvertResult.failure(
                    ErrorCode.FORMAT_NOT_SUPPORTED,
                    f"不支持的 PDF 输出格式：{ext or '（无扩展名）'}",
                    src,
                )

        result.input_path = src
        result.duration = timer.elapsed
        return result

    # ------------------------------------------------------------ 文本
    def _extract_text(self, src: Path, dst: Path, fmt: str) -> ConvertResult:
        try:
            from pypdf import PdfReader
        except ImportError:
            return ConvertResult.failure(
                ErrorCode.DEPENDENCY_MISSING, "缺少依赖 pypdf，请运行：pip install pypdf", src
            )

        try:
            reader = PdfReader(str(src))
            if len(reader.pages) == 0:
                return ConvertResult.failure(ErrorCode.INVALID_INPUT, "PDF 没有任何页面", src)

            pages: list[tuple[int, str]] = []
            for index, page in enumerate(reader.pages):
                try:
                    text = page.extract_text() or ""
                except Exception as exc:  # 单页坏了不影响整篇
                    logger.warning("第 %d 页文字提取失败：%s", index + 1, exc)
                    text = ""
                pages.append((index + 1, text.strip()))

            if fmt == "md":
                chunks = [f"---\n\n## 第 {no} 页\n\n{text}\n" for no, text in pages]
                content = "\n".join(chunks)
            else:
                chunks = [f"=== 第 {no} 页 ===\n{text}" for no, text in pages]
                content = "\n\n".join(chunks)

            if not content.strip():
                logger.warning("PDF 未提取到文字（可能是扫描件）：%s", src.name)

            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(content, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.error("PDF 文字提取失败：%s", exc)
            return ConvertResult.failure(
                ErrorCode.CONVERSION_FAILED, f"PDF 文字提取失败：{exc}", src
            )

        logger.info("PDF 文字提取成功：%s -> %s", src.name, dst.name)
        return ConvertResult.success(dst, extra={"pages": len(pages)})

    # ------------------------------------------------------------ 图片
    def _extract_images(self, src: Path, dst: Path, fmt: str) -> ConvertResult:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            return ConvertResult.failure(
                ErrorCode.DEPENDENCY_MISSING,
                "PDF 转图片需要可选依赖 PyMuPDF（AGPL 许可，未随本项目分发）。"
                "安装命令：pip install pymupdf",
                src,
            )

        try:
            document = fitz.open(str(src))
        except Exception as exc:  # noqa: BLE001
            return ConvertResult.failure(
                ErrorCode.INVALID_INPUT, f"无法打开 PDF：{exc}", src
            )

        try:
            page_count = len(document)
            if page_count == 0:
                return ConvertResult.failure(ErrorCode.INVALID_INPUT, "PDF 没有任何页面", src)

            suffix = ".jpg" if fmt in ("jpg", "jpeg") else ".png"
            # PDF 没有透明通道，转 JPG 直接用白底，避免出黑底
            render_format = "jpeg" if suffix == ".jpg" else "png"
            images: list[bytes] = [
                document.load_page(i).get_pixmap(dpi=150).tobytes(render_format)
                for i in range(page_count)
            ]
        finally:
            document.close()

        dst.parent.mkdir(parents=True, exist_ok=True)

        if len(images) == 1:
            dst.write_bytes(images[0])
            logger.info("PDF 单页转图片成功：%s -> %s", src.name, dst.name)
            return ConvertResult.success(dst, extra={"pages": 1})

        zip_path = dst.parent / (dst.stem + ".zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for index, data in enumerate(images, start=1):
                archive.writestr(f"{dst.stem}_p{index}{suffix}", data)

        logger.info("PDF 多页转图片成功：%s -> %s（%d 页）", src.name, zip_path.name, len(images))
        return ConvertResult.success(zip_path, extra={"pages": len(images), "packed": True})

    # ------------------------------------------------------------ HTML
    def _extract_to_html(self, src: Path, dst: Path) -> ConvertResult:
        try:
            from pypdf import PdfReader
        except ImportError:
            return ConvertResult.failure(
                ErrorCode.DEPENDENCY_MISSING, "缺少依赖 pypdf，请运行：pip install pypdf", src
            )

        try:
            reader = PdfReader(str(src))
            parts = [
                "<!DOCTYPE html>",
                '<html lang="zh-CN">',
                "<head>",
                '<meta charset="utf-8">',
                "<title>PDF 导出</title>",
                f"<style>{HTML_CSS}</style>",
                "</head>",
                "<body>",
            ]
            for index, page in enumerate(reader.pages, start=1):
                try:
                    text = (page.extract_text() or "").strip()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("第 %d 页提取失败：%s", index, exc)
                    text = ""
                if text:
                    parts.append(
                        f'<section class="page"><h2>第 {index} 页</h2>'
                        f"<pre>{_escape(text)}</pre></section>"
                    )
                else:
                    parts.append(
                        f'<section class="page"><h2>第 {index} 页</h2>'
                        "<pre>（本页没有可提取的文字，可能是扫描图片）</pre></section>"
                    )
            parts.append("</body></html>")

            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text("\n".join(parts), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.error("PDF 转 HTML 失败：%s", exc)
            return ConvertResult.failure(ErrorCode.CONVERSION_FAILED, f"PDF 转 HTML 失败：{exc}", src)

        logger.info("PDF 转 HTML 成功：%s -> %s", src.name, dst.name)
        return ConvertResult.success(dst)


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
