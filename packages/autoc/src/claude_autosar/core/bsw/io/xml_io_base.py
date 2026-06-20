"""Shared XML I/O primitives for ARXML and DataModel2 modules.

Sprint 9.5 — 提取 ``arxml_io.py`` 与 ``datamodel2_io.py`` 的共同模式：

  - ``atomic_write``：.tmp + ``os.replace`` 原子写入（格式无关）
  - ``cleanup_namespaces_fallback``：surgical patch 不可用时的 tostring 退路
  - ``_SurgicalPatchUnavailable``：surgical patch 路径不可用异常

各格式专属的 ``_apply_surgical_patch_to_bytes`` 保留在各自模块中。
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import Any, Type

from lxml import etree


class _SurgicalPatchUnavailable(Exception):
    """Surgical patch 路径不可用（无原文件 / 文件结构变化 / 改的不是目标元素）。"""


def atomic_write(
    path: Path,
    tree: Any,
    write_fn: Any,
    error_cls: Type[Exception],
) -> None:
    """Atomic write: .tmp + ``os.replace``。

    Parameters
    ----------
    path
        目标文件路径（非 .tmp 后缀）。
    tree
        lxml ``_ElementTree`` 或兼容对象。
    write_fn
        ``write_fn(path, tree)`` 回调，负责把 tree 写到指定 path。
        对于 preserve_format=True 场景，调用方包装 ``_write_to_path``。
    error_cls
        写入失败时抛出的异常类型（``ARXMLError`` 或 ``DataModel2Error``）。
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        write_fn(tmp, tree)
        os.replace(tmp, path)
    except (OSError, etree.SerialisationError) as e:
        with contextlib.suppress(OSError):
            if tmp.exists():
                tmp.unlink()
        raise error_cls(f"Failed to write XML atomically to {path}: {e}") from e


def cleanup_namespaces_fallback(
    path: Path,
    tree: Any,
    *,
    preserve_format: bool,
) -> None:
    """退路：``cleanup_namespaces`` + ``tostring`` + 重建 DOCTYPE。

    surgical patch 不可用时使用。``preserve_format=True`` 保留 DOCTYPE；
    ``False`` 走纯 tostring 软保真。
    """
    if preserve_format:
        with contextlib.suppress(ValueError, etree.Error):
            etree.cleanup_namespaces(tree)
        doctype = tree.docinfo.doctype if hasattr(tree, "docinfo") else None
        body = etree.tostring(
            tree,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
            doctype=doctype,
        )
        path.write_bytes(body)
    else:
        path.write_bytes(
            etree.tostring(
                tree,
                xml_declaration=True,
                encoding="UTF-8",
                standalone=True,
            )
        )


__all__ = [
    "_SurgicalPatchUnavailable",
    "atomic_write",
    "cleanup_namespaces_fallback",
]
