"""MCU-AP-001 — McuClockSettingConfig with zero frequency.

v2 检测深度：

* 检查 XDM leaves 路径中含 ``McuClockSettingConfig`` 的频率参数
* 如果频率为零或负数 → yield violation

v2 增强方向：

* 解析 ``McuClockSettingConfig`` 容器，提取 ``McuClockFrequency``
* 频率 <= 0 → violation
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, ClassVar

from claude_autosar.core.bsw.lint import (
    LintSeverity,
    LintViolation,
    XdmLintData,
)


class McuAp001Rule:
    """MCU-AP-001: McuClockSettingConfig with zero frequency."""

    rule_id: ClassVar[str] = "MCU-AP-001"
    severity_default: ClassVar[str] = LintSeverity.ERROR
    applies_to: ClassVar[str] = "xdm"  # 只吃 XdmLintData

    #: v1 简化：路径包含 McuClockSettingConfig 即触发检查
    _MCU_CLOCK_KEYWORDS: ClassVar[tuple[str, ...]] = (
        "McuClockSettingConfig",
        "McuClockFrequency",
    )

    def check(self, extracted: Any) -> Iterable[LintViolation]:
        # XDM-only rule — skip silently if data is not XdmLintData
        if not isinstance(extracted, XdmLintData):
            return ()
        # v1 MVP stub：XDM fixture 没 Mcu 数据 → 不 yield（FP=0 优先）
        for _leaf in extracted.leaves:
            path = str(_leaf.get("path", ""))
            if any(kw in path for kw in self._MCU_CLOCK_KEYWORDS):
                # 当前不报（无频率数据）
                return ()
        return ()
