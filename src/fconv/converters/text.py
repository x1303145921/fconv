"""
文本文档转换器 - TXT / MD / HTML / JSON / CSV / XML / YAML 互转。

设计：**统一中转表示（pivot）**
    源格式 --parse--> Python 对象(str/dict/list) --render--> 目标格式
这样 7×7 共 49 个方向都由「解析 + 渲染」两个小函数组合出来，
不再出现旧版「没写分支就原样拷贝、结果扩展名和内容对不上」的问题。
"""
from __future__ import annotations

import csv
import io
import json
import logging
from pathlib import Path
from typing import Any

from ..core import Converter, ConvertResult, ErrorCode, Timer

logger = logging.getLogger(__name__)

SOURCE_FORMATS = ["txt", "md", "html", "json", "csv", "xml", "yaml"]
TARGET_FORMATS = ["txt", "md", "html", "json", "csv", "xml", "yaml"]

MD_EXT, TXT_EXT, HTML_EXT = "md", "txt", "html"


class UnsupportedConversion(Exception):
    """该转换方向没有合理结果（例如把纯文本转成结构化表格）。"""


class TextConverter(Converter):
    """文本文档格式转换器。"""

    source_formats = SOURCE_FORMATS
    target_formats = TARGET_FORMATS

    # ------------------------------------------------------------ 主流程
    def convert(self, src: Path, dst: Path, **options: Any) -> ConvertResult:
        src, dst = Path(src), Path(dst)
        src_ext = self._ext(src)
        dst_ext = self._ext(dst)
        encoding = str(options.get("encoding", "utf-8"))

        try:
            raw = src.read_text(encoding=encoding, errors="replace")
        except OSError as exc:
            return ConvertResult.failure(
                ErrorCode.CONVERSION_FAILED, f"读取文件失败：{exc}", src
            )

        try:
            with Timer() as timer:
                data = self._parse(raw, src_ext, encoding)
                output = self._render(data, dst_ext, options)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(output, encoding=encoding, errors="replace")
        except UnsupportedConversion as exc:
            return ConvertResult.failure(ErrorCode.FORMAT_NOT_SUPPORTED, str(exc), src)
        except json.JSONDecodeError as exc:
            return ConvertResult.failure(
                ErrorCode.INVALID_INPUT, f"JSON 格式错误：第 {exc.lineno} 行 {exc.msg}", src
            )
        except _NeedYaml as exc:
            return ConvertResult.failure(ErrorCode.DEPENDENCY_MISSING, str(exc), src)
        except Exception as exc:  # noqa: BLE001 - 兜底，保证不崩
            logger.exception("文本转换失败：%s", src)
            return ConvertResult.failure(
                ErrorCode.CONVERSION_FAILED, f"转换失败：{exc}", src
            )

        logger.info("文本转换成功：%s → %s", src.name, dst.name)
        return ConvertResult.success(dst, duration=timer.elapsed)

    # ------------------------------------------------------------ 解析
    @staticmethod
    def _ext(path: Path) -> str:
        ext = path.suffix.lower().lstrip(".")
        return {"htm": "html", "yml": "yaml", "markdown": "md"}.get(ext, ext)

    def _parse(self, raw: str, src_ext: str, encoding: str) -> Any:
        if src_ext == "json":
            return json.loads(raw)

        if src_ext == "csv":
            return self._parse_csv(raw)

        if src_ext == "xml":
            return self._parse_xml(raw)

        if src_ext == "yaml":
            yaml = _import_yaml()
            return yaml.safe_load(raw)

        if src_ext == "html":
            return {"text": self._strip_html(raw)}

        return raw  # txt / md：保持原文

    @staticmethod
    def _parse_csv(raw: str) -> Any:
        rows = list(csv.reader(io.StringIO(raw)))
        rows = [row for row in rows if any(cell.strip() for cell in row)]
        if not rows:
            return []
        header = [cell.strip() for cell in rows[0]]
        records = []
        for row in rows[1:]:
            padded = list(row) + [""] * (len(header) - len(row))
            records.append(dict(zip(header, padded[: len(header)])))
        if not records:  # 只有表头
            return [dict.fromkeys(header, "")]
        return records

    @staticmethod
    def _parse_xml(raw: str) -> Any:
        import xml.etree.ElementTree as ET

        root = ET.fromstring(raw)

        def to_value(element: ET.Element) -> Any:
            children = list(element)
            if not children:
                return (element.text or "").strip()
            grouped: dict[str, list[Any]] = {}
            for child in children:
                grouped.setdefault(child.tag, []).append(to_value(child))
            return {
                key: (values[0] if len(values) == 1 else values)
                for key, values in grouped.items()
            }

        return {root.tag: to_value(root)}

    # ------------------------------------------------------------ 渲染
    def _render(self, data: Any, dst_ext: str, options: dict) -> str:
        if dst_ext == "json":
            return self._render_json(data, options)
        if dst_ext == "csv":
            return self._render_csv(data)
        if dst_ext == "xml":
            return self._render_xml(data)
        if dst_ext == "yaml":
            return self._render_yaml(data)
        if dst_ext == HTML_EXT:
            return self._render_html(data)
        if dst_ext == MD_EXT:
            return self._render_markdown(data)
        if dst_ext == TXT_EXT:
            return self._render_text(data)
        raise UnsupportedConversion(f"不支持的文本输出格式：{dst_ext or '（无扩展名）'}")

    @staticmethod
    def _render_json(data: Any, options: dict) -> str:
        if isinstance(data, str):
            payload: Any = {"content": data.splitlines()}
        else:
            payload = data
        indent = int(options.get("indent", 2))
        return json.dumps(payload, ensure_ascii=False, indent=indent)

    @staticmethod
    def _render_csv(data: Any) -> str:
        rows = _as_records(data)
        if not rows:
            return ""
        fieldnames: list[str] = []
        for record in rows:
            for key in record:
                if key not in fieldnames:
                    fieldnames.append(key)
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\r\n")
        writer.writeheader()
        for record in rows:
            writer.writerow({key: record.get(key, "") for key in fieldnames})
        return buffer.getvalue()

    @staticmethod
    def _render_xml(data: Any) -> str:
        import xml.dom.minidom as minidom

        document = minidom.Document()
        _append_xml(document, document, "root", data)
        return document.toprettyxml(indent="  ")

    @staticmethod
    def _render_yaml(data: Any) -> str:
        yaml = _import_yaml()
        if isinstance(data, str):
            return yaml.safe_dump({"content": data}, allow_unicode=True, sort_keys=False)
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)

    def _render_markdown(self, data: Any) -> str:
        if isinstance(data, str):
            return data
        return _structure_to_markdown(data)

    def _render_text(self, data: Any) -> str:
        if isinstance(data, str):
            return data
        return _structure_to_text(data)

    def _render_html(self, data: Any) -> str:
        body = _structure_to_html(data) if not isinstance(data, str) else _text_to_html(data)
        return (
            '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
            "<title>文档</title>\n<style>"
            "body{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;"
            "max-width:820px;margin:40px auto;padding:0 20px;line-height:1.75;color:#111}"
            "table{border-collapse:collapse;width:100%;font-size:14px}"
            "th,td{border:1px solid #e2e2e2;padding:8px 10px;text-align:left}"
            "th{background:#fafafa;font-weight:600}"
            "pre{white-space:pre-wrap;word-break:break-word;font-size:14px}"
            "</style>\n</head>\n<body>\n" + body + "\n</body>\n</html>\n"
        )

    # ------------------------------------------------------------ HTML 去标签
    @staticmethod
    def _strip_html(html: str) -> str:
        import html as html_module
        import re

        without_scripts = re.sub(
            r"(?is)<(script|style)[^>]*>.*?</\1>", "", html
        )
        with_breaks = re.sub(r"(?i)<br\s*/?>", "\n", without_scripts)
        with_breaks = re.sub(r"(?i)</(p|div|li|h[1-6]|tr)>", "\n", with_breaks)
        text = re.sub(r"<[^>]+>", "", with_breaks)
        text = html_module.unescape(text)
        lines = [line.strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line)


# ---------------------------------------------------------------- 辅助函数
class _NeedYaml(Exception):
    """缺少 PyYAML。"""


def _import_yaml():
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - 取决于环境
        raise _NeedYaml(
            "该方向需要可选依赖 PyYAML，请运行：pip install PyYAML"
        ) from exc
    return yaml


def _as_records(data: Any) -> list[dict[str, Any]]:
    """把任意结构压成「一行一记录」，供 CSV 渲染。"""
    if data is None:
        return []
    if isinstance(data, dict):
        # {"a": 1, "b": 2} → 单行；{"items": [...]} → 展开列表
        if len(data) == 1:
            only = next(iter(data.values()))
            if isinstance(only, list):
                return _as_records(only)
        if all(not isinstance(v, (dict, list)) for v in data.values()):
            return [data]
        rows = []
        for key, value in data.items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        rows.append({"key": key, **item})
                    else:
                        rows.append({"key": key, "value": item})
            elif isinstance(value, dict):
                rows.append({"key": key, **value})
            else:
                rows.append({"key": key, "value": value})
        return rows
    if isinstance(data, list):
        rows = []
        for item in data:
            if isinstance(item, dict):
                rows.append(item)
            elif isinstance(item, list):
                rows.append({f"col{i + 1}": cell for i, cell in enumerate(item)})
            else:
                rows.append({"value": item})
        return rows
    return [{"value": data}]  # 纯字符串 / 数字


def _append_xml(document: Any, parent: Any, tag: str, value: Any) -> None:
    safe_tag = _safe_xml_tag(tag)
    node = document.createElement(safe_tag)
    parent.appendChild(node)
    if isinstance(value, dict):
        for key, child in value.items():
            _append_xml(document, node, str(key), child)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _append_xml(document, node, "item", item)
    elif value is not None:
        node.appendChild(document.createTextNode(str(value)))


def _safe_xml_tag(tag: str) -> str:
    import re

    cleaned = re.sub(r"[^0-9A-Za-z_.-]", "_", tag or "item")
    if not cleaned or cleaned[0].isdigit():
        cleaned = "n_" + cleaned
    return cleaned


def _structure_to_text(data: Any, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(data, dict):
        lines = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.append(_structure_to_text(value, indent + 1))
            else:
                lines.append(f"{pad}{key}: {value}")
        return "\n".join(lines)
    if isinstance(data, list):
        lines = []
        for item in data:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                lines.append(_structure_to_text(item, indent + 1))
            else:
                lines.append(f"{pad}- {item}")
        return "\n".join(lines)
    return f"{pad}{data}"


def _structure_to_markdown(data: Any) -> str:
    if isinstance(data, list) and data and all(isinstance(x, dict) for x in data):
        return _records_to_markdown_table(data)
    if isinstance(data, dict) and all(not isinstance(v, (dict, list)) for v in data.values()):
        return "\n".join(f"- **{key}**：{value}" for key, value in data.items())
    return _structure_to_text(data)


def _records_to_markdown_table(records: list[dict[str, Any]]) -> str:
    columns: list[str] = []
    for record in records:
        for key in record:
            if key not in columns:
                columns.append(key)
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    rows = [
        "| " + " | ".join(_cell(record.get(column, "")) for column in columns) + " |"
        for record in records
    ]
    return "\n".join([header, divider, *rows])


def _cell(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False).replace("|", "\\|")
    return str(value).replace("|", "\\|").replace("\n", " ")


def _structure_to_html(data: Any) -> str:
    if isinstance(data, list) and data and all(isinstance(x, dict) for x in data):
        columns: list[str] = []
        for record in data:
            for key in record:
                if key not in columns:
                    columns.append(key)
        head = "".join(f"<th>{_escape_html(str(c))}</th>" for c in columns)
        body = "".join(
            "<tr>" + "".join(f"<td>{_escape_html(_cell(r.get(c, '')))}</td>" for c in columns) + "</tr>"
            for r in data
        )
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    if isinstance(data, dict):
        rows = "".join(
            f"<tr><th>{_escape_html(str(k))}</th><td>{_escape_html(_cell(v))}</td></tr>"
            for k, v in data.items()
        )
        return f"<table>{rows}</table>"
    return f"<pre>{_escape_html(_structure_to_text(data))}</pre>"


def _text_to_html(text: str) -> str:
    """极简 Markdown 子集 → HTML：标题 / 列表 / 引用 / 段落。"""
    lines = text.split("\n")
    html: list[str] = []
    in_list = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")):
            if not in_list:
                html.append("<ul>")
                in_list = True
            html.append(f"<li>{_escape_html(stripped[2:])}</li>")
            continue
        if in_list:
            html.append("</ul>")
            in_list = False
        if stripped.startswith("### "):
            html.append(f"<h3>{_escape_html(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            html.append(f"<h2>{_escape_html(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            html.append(f"<h1>{_escape_html(stripped[2:])}</h1>")
        elif stripped.startswith("> "):
            html.append(f"<blockquote>{_escape_html(stripped[2:])}</blockquote>")
        elif stripped:
            html.append(f"<p>{_escape_html(stripped)}</p>")
    if in_list:
        html.append("</ul>")
    return "\n".join(html)


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
