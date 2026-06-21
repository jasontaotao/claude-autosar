"""MCP 输入校验 — 阻断路径遍历 / XPath 注入 / session_dir 注入。

Sprint 9.5 M9–M12 安全修复：共享校验函数，供 inspect_ops / bsw_read_ops /
bsw_write_ops / session_ops 调用。
"""

from __future__ import annotations

import os
import re

#: 白名单：模块 / segment 名必须以字母开头，仅含字母数字下划线。
#: 阻断 XPath 注入（双引号、方括号、斜杠）和路径遍历（../）。
_SAFE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def validate_module_name(name: str) -> str:
    """校验模块名 / XPath segment，拒绝非法字符。

    :raises ValueError: 名称不匹配 ``^[A-Za-z][A-Za-z0-9_]*$``
    """
    if not _SAFE_NAME.match(name):
        raise ValueError(f"Invalid module name: {name!r}")
    return name


def validate_no_traversal(path: str) -> str:
    """校验路径不含 ``..``，阻断目录遍历攻击。

    :raises ValueError: 路径含 ``..``
    """
    if ".." in path:
        raise ValueError(f"Path traversal not allowed: {path!r}")
    if os.path.isabs(path) or path.startswith("/"):
        raise ValueError(f"Path traversal not allowed: {path!r}")
    return path
