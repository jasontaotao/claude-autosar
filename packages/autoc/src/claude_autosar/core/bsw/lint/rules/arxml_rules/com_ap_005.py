"""COM-AP-005 — ComSignalGroup without signals.

v2 检测深度：

* 遍历 ``ipdus``，检查每个 IPdu 的 signal group 定义
* 如果 signal group 没有 signal 引用 → yield violation

v2 增强方向：

* 解析 ComSignalGroupRef 引用链
* 支持嵌套 signal group
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class ComAp005Rule:
    """COM-AP-005: ComSignalGroup without signals."""

    rule_id: ClassVar[str] = "COM-AP-005"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # v1 MVP stub：inspector 没拆 signal group 数据
        # 数据不足以检查 signal group 是否为空 → 不 yield（FP=0 优先）
        # v2 增强方向：解析 ComSignalGroup 子节点里的 ComSignalRef 列表
        return ()
