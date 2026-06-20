"""BSW 领域共享类型定义。

``ParamType`` 统一 ``config.py`` 的 Enum 与 ``bswmd.py`` 的 Literal 别名，
合并为 ``str, Enum``（6 成员）。继承 ``str`` 使得序列化 / 比较兼容现有
Literal 字符串用法（``ParamType.INTEGER == "INTEGER"`` → ``True``）。
"""

from __future__ import annotations

from enum import Enum


class ParamType(str, Enum):
    """BSW 参数类型枚举。

    继承 ``str`` 使得：
    - ``ParamType.INTEGER == "INTEGER"`` → ``True``（向后兼容 Literal 用法）
    - ``ParamType("INTEGER")`` → ``ParamType.INTEGER``（构造器兼容）
    - JSON / dict 序列化时 ``str(member)`` 自动得到大写字符串
    """

    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    STRING = "STRING"
    BOOLEAN = "BOOLEAN"
    ENUMERATION = "ENUMERATION"
    FUNCTION_NAME = "FUNCTION_NAME"
