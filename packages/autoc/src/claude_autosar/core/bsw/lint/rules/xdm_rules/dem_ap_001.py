"""DEM-AP-001 — Flash 越界 = 量产刷写变砖。

v1 MVP 检测深度：

* 检查 XDM leaves 路径中含 ``DemPrimaryMemory`` 的 start / size
* 当前 XDM fixture 没 Dem 数据 → 不 yield（FP=0 优先）

v2 增强方向：

* 解析 ``DemPrimaryMemory`` / ``DemSecondaryMemory`` 容器，提取
  ``StartAddress`` + ``Size``，合并算 end-address
* end-address > 实际 flash size（从 MCU 模块读） → violation
"""

from __future__ import annotations

from typing import Any, ClassVar
from collections.abc import Iterable

from claude_autosar.core.bsw.lint import (
    LintSeverity,
    LintViolation,
    XdmLintData,
)


class DemAp001Rule:
    """DEM-AP-001: DEM memory address range exceeds flash size."""

    rule_id: ClassVar[str] = "DEM-AP-001"
    severity_default: ClassVar[str] = LintSeverity.ERROR
    applies_to: ClassVar[str] = "xdm"  # 只吃 XdmLintData

    #: v1 简化：路径包含 DemPrimary / DemSecondary 即触发检查
    _DEM_MEMORY_KEYWORDS: ClassVar[tuple[str, ...]] = (
        "DemPrimaryMemory",
        "DemSecondaryMemory",
    )

    def check(
        self, extracted: Any
    ) -> Iterable[LintViolation]:
        # XDM-only rule — skip silently if data is not XdmLintData
        if not isinstance(extracted, XdmLintData):
            return ()
        # v1 MVP stub：XDM fixture 无 Dem 数据 → 不 yield
        for _leaf in extracted.leaves:
            path = str(_leaf.get("path", ""))
            if any(kw in path for kw in self._DEM_MEMORY_KEYWORDS):
                # 当前不报（无 flash size 信息）
                return ()
        return ()
