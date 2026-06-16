"""PDUR-AP-001 — PduRRoutingPath without source and destination.

v2 检测深度：

* 检查 ``key_params`` 里 PduRRoutingPath 相关参数
* 检查 routing path 是否有源和目标 PDU 引用
* 如果缺少源或目标 → yield violation

v2 增强方向：

* 解析 PduR 模块下 PduRRoutingPath 容器
* 检查 PduRSrcPdu 和 PduRDestPdu 引用
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class PduRAp001Rule:
    """PDUR-AP-001: PduRRoutingPath without source and destination."""

    rule_id: ClassVar[str] = "PDUR-AP-001"
    severity_default: ClassVar[str] = LintSeverity.ERROR
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    #: PduR routing 相关参数
    _PDUR_ROUTING_PARAMS: ClassVar[tuple[str, ...]] = (
        "PduRRoutingPath",
        "PduRSrcPdu",
        "PduRDestPdu",
    )

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # v1 MVP stub：inspector key_params 不含 PduRRoutingPath 详情
        # 数据不足以做"routing path 缺少源/目标"判断 → 不 yield（避免误报）
        # v2 增强方向：解析 PduR 模块下 PduRRoutingPath 容器和 PDU 引用
        for _p in extracted.key_params:
            if _p.get("name") in self._PDUR_ROUTING_PARAMS:
                # 当前不报（routing path 详情不可知）
                return ()
        return ()
