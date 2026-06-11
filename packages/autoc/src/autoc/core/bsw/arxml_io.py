"""lxml-based low-level ARXML read/write utilities.

Sprint 3 — T3.1。提供命名空间感知的元素查找、属性/子文本读写、原子写文件。
仅作低层工具；高层 ECUC 语义解析在 `ecuc.py`。
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, cast

from lxml import etree

# AUTOSAR 经典平台默认命名空间
DEFAULT_NAMESPACES: dict[str, str] = {
    "ar": "http://autosar.org/schema/r4.0",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}


class ARXMLError(Exception):
    """ARXML I/O 失败时抛出的统一异常（包装 lxml/OSError）。"""


@dataclass(frozen=True)
class ARXMLDocument:
    """不可变 ARXML 文档：path + 解析后的 lxml 树。"""

    path: Path
    tree: Any  # lxml.etree._ElementTree（不指定 generic 避免 mypy 噪音）


def read(path: Path) -> ARXMLDocument:
    """读 ARXML 文件。文件不存在或 XML 畸形时抛 ARXMLError。"""
    try:
        tree = etree.parse(str(path))
    except OSError as e:
        # lxml 抛 OSError（FileNotFoundError / PermissionError 等）
        raise ARXMLError(f"ARXML file not readable: {path}: {e}") from e
    except etree.XMLSyntaxError as e:
        raise ARXMLError(f"Malformed ARXML in {path}: {e}") from e
    return ARXMLDocument(path=path, tree=tree)


def write(doc: ARXMLDocument, *, atomic: bool = True) -> None:
    """写 ARXML 文档到其 path。

    atomic=True（默认）：先写 .tmp 文件再 os.replace 替换。失败时原文件保持不变。
    atomic=False：直接覆盖。
    """
    target = doc.path
    if not atomic:
        _write_to_path(target, doc)
        return

    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        _write_to_path(tmp, doc)
        os.replace(tmp, target)
    except (OSError, etree.SerialisationError) as e:
        # 清理可能残留的 .tmp（用 suppress 避免异常吞噬）
        with contextlib.suppress(OSError):
            if tmp.exists():
                tmp.unlink()
        raise ARXMLError(f"Failed to write ARXML atomically to {target}: {e}") from e


def _write_to_path(path: Path, doc: ARXMLDocument) -> None:
    """实际写 XML 字节到 path。"""
    path.write_bytes(
        etree.tostring(
            doc.tree,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        )
    )


def find_elements(
    doc: ARXMLDocument,
    xpath: str,
    namespaces: dict[str, str] | None = None,
) -> list[Any]:
    """xpath 查找元素。返回列表（无匹配返回空）。

    如果 doc 有命名空间但调用者没传 namespaces 字典，结果会是空（lxml 默认行为）。
    """
    ns = namespaces if namespaces is not None else {}
    try:
        return cast(list[Any], doc.tree.xpath(xpath, namespaces=ns))
    except etree.XPathEvalError as e:
        raise ARXMLError(f"Invalid XPath {xpath!r}: {e}") from e


def get_attribute(
    elem: Any,
    name: str,
    *,
    default: str | None = None,
) -> str | None:
    """取元素属性值；不存在时返回 default（默认 None）。"""
    return cast(str | None, elem.get(name, default))


def set_attribute(elem: Any, name: str, value: str) -> None:
    """设置元素属性（覆盖已有值）。"""
    elem.set(name, value)


def get_child_text(
    elem: Any,
    tag: str,
    *,
    namespaces: dict[str, str] | None = None,
) -> str | None:
    """取 elem 下第一个 tag 子元素的文本。子元素不存在时返回 None。

    namespaces=None（默认）：namespace-blind 匹配（用 lxml 的 `{*}` wildcard，
    按 local name 匹配）。绝大多数 ARXML 子树都在 AUTOSAR 默认命名空间下，
    这种匹配是最常用的。

    namespaces=非空：用第一个 prefix 拼接 tag 走 xpath 查找
    （如 namespaces={"ar": "..."}，"VALUE" → "ar:VALUE"）。
    """
    child = _find_child(elem, tag, namespaces)
    if child is None:
        return None
    return cast(str | None, child.text)


def set_child_text(
    elem: Any,
    tag: str,
    value: str,
    *,
    namespaces: dict[str, str] | None = None,
) -> None:
    """设置 elem 下 tag 子元素的文本。如果子元素存在则覆盖文本；否则创建新子元素。

    命名空间规则同 get_child_text。
    """
    child = _find_child(elem, tag, namespaces)
    if child is None:
        if namespaces:
            ns_uri = next(iter(namespaces.values()))
            child = etree.SubElement(elem, f"{{{ns_uri}}}{tag}")
        else:
            # 不指定 ns → 新元素无命名空间；调用方如有强需求可显式传 namespaces
            child = etree.SubElement(elem, tag)
    child.text = value


def _find_child(elem: Any, tag: str, namespaces: dict[str, str] | None) -> Any | None:
    """内部：找 elem 的直接子元素匹配 tag。"""
    if namespaces:
        prefix = next(iter(namespaces))
        return elem.find(f"{prefix}:{tag}", namespaces=namespaces)
    return elem.find("{*}" + tag)
