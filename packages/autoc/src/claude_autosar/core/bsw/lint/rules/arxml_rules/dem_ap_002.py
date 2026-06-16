"""DEM-AP-002 — DemEventParameter without DTC mapping.

v2 检测深度：

* 检查 ``key_params`` 里 DemEventParameter 相关参数
* 检查 event parameter 是否有 DTC 映射
* 如果 event 没有映射到 DTC → yield violation

v2 增强方向：

* 解析 Dem 模块下 DemEventParameter 容器
* 检查每个 event 的 DemDTCRef 引用
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class DemAp002Rule:
    """DEM-AP-002: DemEventParameter without DTC mapping."""

    rule_id: ClassVar[str] = "DEM-AP-002"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    #: DEM event 相关参数
    _DEM_EVENT_PARAMS: ClassVar[tuple[str, ...]] = (
        "DemEventParameter",
        "DemDTCRef",
    )

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # v1 MVP stub：inspector key_params 不含 DemEventParameter 详情
        # 数据不足以做"event 无 DTC 映射"判断 → 不 yield（避免误报）
        # v2 增强方向：解析 Dem 模块下 DemEventParameter 容器和 DTC 引用
        for _p in extracted.key_params:
            if _p.get("name") in self._DEM_EVENT_PARAMS:
                # 当前不报（event DTC 映射不可知）
                return ()
        return ()
