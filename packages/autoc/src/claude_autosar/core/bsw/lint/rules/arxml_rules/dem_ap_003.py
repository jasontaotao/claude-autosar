"""DEM-AP-003 — DemFreezeFrameEvent exceeds max count.

v2 检测深度：

* 检查 ``key_params`` 里 DemFreezeFrameEvent 相关参数
* 检查 freeze frame 事件数量是否超过 UDS 限制（通常 255）
* 如果超过限制 → yield violation

v2 增强方向：

* 解析 Dem 模块下 DemFreezeFrameEvent 容器
* 统计每个 DTC 的 freeze frame 事件数量
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class DemAp003Rule:
    """DEM-AP-003: DemFreezeFrameEvent exceeds max count."""

    rule_id: ClassVar[str] = "DEM-AP-003"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    #: UDS 标准 freeze frame 最大数量
    _MAX_FREEZE_FRAME_COUNT: ClassVar[int] = 255

    #: DEM freeze frame 相关参数
    _FREEZE_FRAME_PARAMS: ClassVar[tuple[str, ...]] = (
        "DemFreezeFrameEvent",
        "DemFreezeFrameRecNum",
    )

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # v1 MVP stub：inspector key_params 不含 DemFreezeFrameEvent 详情
        # 数据不足以做"freeze frame 超限"判断 → 不 yield（避免误报）
        # v2 增强方向：解析 Dem 模块下 DemFreezeFrameEvent 容器并计数
        for _p in extracted.key_params:
            if _p.get("name") in self._FREEZE_FRAME_PARAMS:
                # 当前不报（freeze frame 数量不可知）
                return ()
        return ()
