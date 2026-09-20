"""
图片转换器 - 基于 Pillow。

支持：PNG / JPG / GIF / BMP / TIFF / WEBP / ICO（互相转换）。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..core import Converter, ConvertResult, ErrorCode, Timer

logger = logging.getLogger(__name__)

# Pillow 的保存格式名
PIL_FORMATS: dict[str, str] = {
    "png": "PNG",
    "jpg": "JPEG",
    "gif": "GIF",
    "bmp": "BMP",
    "tif": "TIFF",
    "webp": "WEBP",
    "ico": "ICO",
}

# 不支持透明通道的输出格式
OPAQUE_FORMATS = {"jpg", "bmp"}


class ImageConverter(Converter):
    """图片格式转换器。"""

    source_formats = ["png", "jpg", "gif", "bmp", "tif", "webp", "ico"]
    target_formats = ["png", "jpg", "gif", "bmp", "tif", "webp", "ico"]

    def convert(
        self,
        src: Path,
        dst: Path,
        quality: int = 95,
        optimize: bool = True,
        **options: Any,
    ) -> ConvertResult:
        """
        Args:
            quality: JPEG / WebP 质量（1-100），默认 95
            optimize: 是否启用编码优化
        """
        from PIL import Image as PILImage
        from PIL import UnidentifiedImageError

        src, dst = Path(src), Path(dst)
        dst_format = PIL_FORMATS.get(dst.suffix.lower().lstrip("."))
        if dst_format is None:
            return ConvertResult.failure(
                ErrorCode.FORMAT_NOT_SUPPORTED,
                f"不支持的图片输出格式：{dst.suffix.lstrip('.') or '（无扩展名）'}",
                src,
            )

        quality = max(1, min(100, int(quality)))

        try:
            with Timer() as timer, PILImage.open(src) as img:
                img = self._prepare_mode(img, PILImage, dst.suffix.lower())
                save_kwargs = self._save_kwargs(dst_format, quality, optimize, img)
                dst.parent.mkdir(parents=True, exist_ok=True)
                img.save(dst, format=dst_format, **save_kwargs)
        except (UnidentifiedImageError, OSError) as exc:
            # 「不是图片」和「文件坏了」都归到输入无效，不把堆栈甩给用户
            if isinstance(exc, UnidentifiedImageError) or "cannot identify" in str(exc):
                logger.warning("无法识别的图片：%s", src.name)
                return ConvertResult.failure(
                    ErrorCode.INVALID_INPUT, f"无法识别的图片文件：{src.name}", src
                )
            return ConvertResult.failure(
                ErrorCode.CONVERSION_FAILED, f"图片读写失败：{exc}", src
            )
        except PILImage.DecompressionBombError:
            return ConvertResult.failure(
                ErrorCode.INVALID_INPUT, "图片像素过大，超出安全阈值", src
            )
        except MemoryError:
            return ConvertResult.failure(
                ErrorCode.CONVERSION_FAILED, "内存不足，图片过大", src
            )
        except Exception as exc:  # noqa: BLE001 - 兜底，保证服务不崩
            logger.exception("图片转换失败：%s", src)
            return ConvertResult.failure(
                ErrorCode.CONVERSION_FAILED, f"转换失败：{exc}", src
            )

        logger.info("图片转换成功：%s → %s", src.name, dst.name)
        return ConvertResult.success(dst, duration=timer.elapsed)

    # ------------------------------------------------------------ 内部实现
    @staticmethod
    def _prepare_mode(img: Any, PILImage: Any, dst_suffix: str) -> Any:
        """按目标格式把像素模式调整好（透明通道、调色板）。"""
        key = dst_suffix.lstrip(".")
        if key in OPAQUE_FORMATS and img.mode in ("RGBA", "LA", "P"):
            # 透明底压到白底，避免变黑
            if img.mode == "P":
                img = img.convert("RGBA")
            background = PILImage.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            return background
        if key == "gif":
            return img.convert("P", palette=PILImage.ADAPTIVE)
        if key == "ico":
            return img.convert("RGBA") if img.mode not in ("RGBA", "RGB") else img
        if img.mode not in ("RGB", "RGBA", "L", "P", "I;16"):
            return img.convert("RGB")
        return img

    @staticmethod
    def _save_kwargs(dst_format: str, quality: int, optimize: bool, img: Any) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if dst_format == "JPEG":
            kwargs["quality"] = quality
            kwargs["optimize"] = optimize
            kwargs["progressive"] = True
            kwargs["subsampling"] = 2 if quality < 90 else 0
        elif dst_format == "WEBP":
            kwargs["quality"] = quality
            kwargs["method"] = 4
        elif dst_format == "PNG":
            kwargs["optimize"] = optimize
            kwargs["compress_level"] = 6
        elif dst_format == "GIF":
            kwargs["optimize"] = optimize
        elif dst_format == "ICO":
            kwargs["sizes"] = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        return kwargs
