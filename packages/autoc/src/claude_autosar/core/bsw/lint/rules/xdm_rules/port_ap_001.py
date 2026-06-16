"""PORT-AP-001 — PortPin with conflicting direction and mode.

v2 检测深度：

* 检查 XDM leaves 路径中含 ``PortPin`` 的方向和模式参数
* 如果方向与模式冲突（如 input + output mode） → yield violation

v2 增强方向：

* 解析 ``PortPin`` 容器，提取 ``PortPinDirection`` 和 ``PortPinMode``
* 方向与模式不匹配 → violation
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, ClassVar

from claude_autosar.core.bsw.lint import (
    LintSeverity,
    LintViolation,
    XdmLintData,
)


class PortAp001Rule:
    """PORT-AP-001: PortPin with conflicting direction and mode."""

    rule_id: ClassVar[str] = "PORT-AP-001"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "xdm"  # 只吃 XdmLintData

    #: v1 简化：路径包含 PortPin 即触发检查
    _PORT_PIN_KEYWORDS: ClassVar[tuple[str, ...]] = (
        "PortPin",
        "PortPinDirection",
        "PortPinMode",
    )

    def check(self, extracted: Any) -> Iterable[LintViolation]:
        # XDM-only rule — skip silently if data is not XdmLintData
        if not isinstance(extracted, XdmLintData):
            return ()
        # v1 MVP stub：XDM fixture 没 Port 数据 → 不 yield（FP=0 优先）
        for _leaf in extracted.leaves:
            path = str(_leaf.get("path", ""))
            if any(kw in path for kw in self._PORT_PIN_KEYWORDS):
                # 当前不报（无方向/模式数据）
                return ()
        return ()
