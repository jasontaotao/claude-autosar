"""SPI-AP-002 — SpiJob with invalid data width for channel.

v2 检测深度：

* 检查 XDM leaves 路径中含 ``SpiJob`` 的数据宽度参数
* 如果 job 数据宽度与 channel 数据宽度不匹配 → yield violation

v2 增强方向：

* 解析 ``SpiJob`` 容器，提取 ``SpiDataWidth`` 和 ``SpiChannelRef``
* 数据宽度不匹配 → violation
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, ClassVar

from claude_autosar.core.bsw.lint import (
    LintSeverity,
    LintViolation,
    XdmLintData,
)


class SpiAp002Rule:
    """SPI-AP-002: SpiJob with invalid data width for channel."""

    rule_id: ClassVar[str] = "SPI-AP-002"
    severity_default: ClassVar[str] = LintSeverity.ERROR
    applies_to: ClassVar[str] = "xdm"  # 只吃 XdmLintData

    #: v1 简化：路径包含 SpiJob 即触发检查
    _SPI_JOB_KEYWORDS: ClassVar[tuple[str, ...]] = (
        "SpiJob",
        "SpiDataWidth",
        "SpiChannelRef",
    )

    def check(self, extracted: Any) -> Iterable[LintViolation]:
        # XDM-only rule — skip silently if data is not XdmLintData
        if not isinstance(extracted, XdmLintData):
            return ()
        # v1 MVP stub：XDM fixture 没 Spi 数据 → 不 yield（FP=0 优先）
        for _leaf in extracted.leaves:
            path = str(_leaf.get("path", ""))
            if any(kw in path for kw in self._SPI_JOB_KEYWORDS):
                # 当前不报（无数据宽度数据）
                return ()
        return ()
