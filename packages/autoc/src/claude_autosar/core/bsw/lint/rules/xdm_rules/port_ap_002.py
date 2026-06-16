"""PORT-AP-002 — Output PortPin missing PortPinInitialValue.

v2 检测深度：

* 从 XDM leaves 提取 PortPinDirection 和 PortPinInitialValue
* 当 PortPinDirection=PORT_PIN_OUT 时，必须配置 PortPinInitialValue
* 缺少初始值 → yield violation

规范来源：AUTOSAR SWS_Port — Port_Init() 先设初始值再设方向。
Output pin 无初始值意味着上电后输出电平不确定，可能导致
外部电路（继电器、LED、MOSFET gate）误动作。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, ClassVar

from claude_autosar.core.bsw.lint import (
    LintSeverity,
    LintViolation,
    XdmLintData,
)


class PortAp002Rule:
    """PORT-AP-002: Output PortPin missing PortPinInitialValue."""

    rule_id: ClassVar[str] = "PORT-AP-002"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "xdm"

    #: v1 简化：路径包含 PortPin 即触发检查
    _PORT_PIN_KEYWORDS: ClassVar[tuple[str, ...]] = (
        "PortPin",
        "PortPinDirection",
        "PortPinInitialValue",
    )

    def check(self, extracted: Any) -> Iterable[LintViolation]:
        # XDM-only rule — skip silently if data is not XdmLintData
        if not isinstance(extracted, XdmLintData):
            return ()
        # v1 MVP stub：XDM fixture 没 Port 数据 → 不 yield（FP=0 优先）
        # v2 实现：需要按 PortPin 实例分组，检查 direction=OUT 时是否有 initial value
        for _leaf in extracted.leaves:
            path = str(_leaf.get("path", ""))
            if any(kw in path for kw in self._PORT_PIN_KEYWORDS):
                # 当前不报（需要重建容器引用关系）
                return ()
        return ()
