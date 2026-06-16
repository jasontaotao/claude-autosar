"""J1939TP-AP-001 — J1939TpChannel with invalid MTU.

v2 检测深度：

* 检查 ``key_params`` 里 J1939TpChannel 相关参数
* 检查 channel MTU 是否超过 J1939 限制（通常 1785 bytes）
* 如果超过限制 → yield violation

v2 增强方向：

* 解析 J1939Tp 模块下 J1939TpChannel 容器
* 检查 MTU 与 J1939 规范
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class J1939TpAp001Rule:
    """J1939TP-AP-001: J1939TpChannel with invalid MTU."""

    rule_id: ClassVar[str] = "J1939TP-AP-001"
    severity_default: ClassVar[str] = LintSeverity.ERROR
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    #: J1939 最大 MTU
    _MAX_J1939_MTU: ClassVar[int] = 1785

    #: J1939Tp channel 相关参数
    _J1939TP_CHANNEL_PARAMS: ClassVar[tuple[str, ...]] = (
        "J1939TpChannel",
        "J1939TpMTU",
        "J1939TpChannelRef",
    )

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # v1 MVP stub：inspector key_params 不含 J1939TpChannel 详情
        # 数据不足以做"MTU 无效"判断 → 不 yield（避免误报）
        # v2 增强方向：解析 J1939Tp 模块下 J1939TpChannel 容器并检查 MTU
        for _p in extracted.key_params:
            if _p.get("name") in self._J1939TP_CHANNEL_PARAMS:
                # 当前不报（MTU 不可知）
                return ()
        return ()
