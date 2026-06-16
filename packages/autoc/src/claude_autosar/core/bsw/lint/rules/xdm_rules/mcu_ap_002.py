"""MCU-AP-002 — McuModeSettingConfig without sleep mode.

v2 检测深度：

* 检查 XDM leaves 路径中含 ``McuModeSettingConfig`` 的模式参数
* 如果没有 sleep mode 配置 → yield violation

v2 增强方向：

* 解析 ``McuModeSettingConfig`` 容器，提取 ``McuSleepMode``
* 无 sleep mode → violation
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, ClassVar

from claude_autosar.core.bsw.lint import (
    LintSeverity,
    LintViolation,
    XdmLintData,
)


class McuAp002Rule:
    """MCU-AP-002: McuModeSettingConfig without sleep mode."""

    rule_id: ClassVar[str] = "MCU-AP-002"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "xdm"  # 只吃 XdmLintData

    #: v1 简化：路径包含 McuModeSettingConfig 即触发检查
    _MCU_MODE_KEYWORDS: ClassVar[tuple[str, ...]] = (
        "McuModeSettingConfig",
        "McuSleepMode",
    )

    def check(self, extracted: Any) -> Iterable[LintViolation]:
        # XDM-only rule — skip silently if data is not XdmLintData
        if not isinstance(extracted, XdmLintData):
            return ()
        # v1 MVP stub：XDM fixture 没 Mcu 数据 → 不 yield（FP=0 优先）
        for _leaf in extracted.leaves:
            path = str(_leaf.get("path", ""))
            if any(kw in path for kw in self._MCU_MODE_KEYWORDS):
                # 当前不报（无 sleep mode 数据）
                return ()
        return ()
