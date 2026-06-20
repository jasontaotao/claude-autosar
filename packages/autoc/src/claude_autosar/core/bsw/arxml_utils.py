"""ARXML 通用工具函数。

从 ``ecuc.py`` 提取的公共辅助函数，供 validator / ecuc 等模块复用。
"""

from __future__ import annotations

from typing import Any, cast

from lxml import etree

__all__ = ["find_module_root", "local_tag"]


def local_tag(elem: Any) -> str:
    """返回 elem 的 local tag（去命名空间）。"""
    qname = etree.QName(elem.tag)
    return cast(str, qname.localname)


def find_module_root(root: Any, module_name: str) -> Any | None:
    """在 ARXML root 下找 SHORT-NAME == module_name 的 ECUC-MODULE-CONFIGURATION-VALUES。"""

    # ECUC-MODULE-CONFIGURATION-VALUES 可能在任意命名空间下
    for elem in root.iter("{*}ECUC-MODULE-CONFIGURATION-VALUES"):
        sn = elem.find("{*}SHORT-NAME")
        if sn is not None and sn.text == module_name:
            return elem
    return None
