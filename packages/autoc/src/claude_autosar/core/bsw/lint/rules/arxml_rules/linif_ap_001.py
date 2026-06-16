"""LINIF-AP-001 — LinIfScheduleTable without entries.

v2 检测深度：

* 检查 ``key_params`` 里 LinIfScheduleTable 相关参数
* 检查 schedule table 是否有条目
* 如果没有条目 → yield violation

v2 增强方向：

* 解析 LinIf 模块下 LinIfScheduleTable 容器
* 检查 LinIfEntry 引用
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class LinIfAp001Rule:
    """LINIF-AP-001: LinIfScheduleTable without entries."""

    rule_id: ClassVar[str] = "LINIF-AP-001"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    #: LinIf schedule table 相关参数
    _LINIF_SCHEDULE_PARAMS: ClassVar[tuple[str, ...]] = (
        "LinIfScheduleTable",
        "LinIfEntry",
    )

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # v1 MVP stub：inspector key_params 不含 LinIfScheduleTable 详情
        # 数据不足以做"schedule table 无条目"判断 → 不 yield（避免误报）
        # v2 增强方向：解析 LinIf 模块下 LinIfScheduleTable 容器和 entry 引用
        for _p in extracted.key_params:
            if _p.get("name") in self._LINIF_SCHEDULE_PARAMS:
                # 当前不报（schedule table 条目不可知）
                return ()
        return ()
