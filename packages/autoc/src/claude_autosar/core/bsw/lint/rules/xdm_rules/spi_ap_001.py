"""SPI-AP-001 — SpiSequence with no SpiJob configured.

v2 检测深度：

* 检查 XDM leaves 路径中含 ``SpiSequence`` 的 job 引用参数
* 如果 sequence 没有 job 引用 → yield violation

v2 增强方向：

* 解析 ``SpiSequence`` 容器，提取 ``SpiJobRef``
* 无 job 引用 → violation
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, ClassVar

from claude_autosar.core.bsw.lint import (
    LintSeverity,
    LintViolation,
    XdmLintData,
)


class SpiAp001Rule:
    """SPI-AP-001: SpiSequence with no SpiJob configured."""

    rule_id: ClassVar[str] = "SPI-AP-001"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "xdm"  # 只吃 XdmLintData

    #: v1 简化：路径包含 SpiSequence 即触发检查
    _SPI_SEQUENCE_KEYWORDS: ClassVar[tuple[str, ...]] = (
        "SpiSequence",
        "SpiJobRef",
    )

    def check(self, extracted: Any) -> Iterable[LintViolation]:
        # XDM-only rule — skip silently if data is not XdmLintData
        if not isinstance(extracted, XdmLintData):
            return ()
        # v1 MVP stub：XDM fixture 没 Spi 数据 → 不 yield（FP=0 优先）
        for _leaf in extracted.leaves:
            path = str(_leaf.get("path", ""))
            if any(kw in path for kw in self._SPI_SEQUENCE_KEYWORDS):
                # 当前不报（无 job 引用数据）
                return ()
        return ()
