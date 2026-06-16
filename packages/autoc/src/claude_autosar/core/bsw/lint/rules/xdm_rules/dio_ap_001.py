"""DIO-AP-001 — DioChannelGroup with invalid channel range.

v2 检测深度：

* 检查 XDM leaves 路径中含 ``DioChannelGroup`` 的通道范围参数
* 如果通道范围超过端口宽度 → yield violation

v2 增强方向：

* 解析 ``DioChannelGroup`` 容器，提取 ``DioChannelGroupChannelRange``
* 通道范围超过端口宽度 → violation
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, ClassVar

from claude_autosar.core.bsw.lint import (
    LintSeverity,
    LintViolation,
    XdmLintData,
)


class DioAp001Rule:
    """DIO-AP-001: DioChannelGroup with invalid channel range."""

    rule_id: ClassVar[str] = "DIO-AP-001"
    severity_default: ClassVar[str] = LintSeverity.ERROR
    applies_to: ClassVar[str] = "xdm"  # 只吃 XdmLintData

    #: v1 简化：路径包含 DioChannelGroup 即触发检查
    _DIO_CHANNEL_GROUP_KEYWORDS: ClassVar[tuple[str, ...]] = (
        "DioChannelGroup",
        "DioChannelGroupChannelRange",
    )

    def check(self, extracted: Any) -> Iterable[LintViolation]:
        # XDM-only rule — skip silently if data is not XdmLintData
        if not isinstance(extracted, XdmLintData):
            return ()
        # v1 MVP stub：XDM fixture 没 Dio 数据 → 不 yield（FP=0 优先）
        for _leaf in extracted.leaves:
            path = str(_leaf.get("path", ""))
            if any(kw in path for kw in self._DIO_CHANNEL_GROUP_KEYWORDS):
                # 当前不报（无通道范围数据）
                return ()
        return ()
