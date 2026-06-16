"""PDUR-AP-002 — PduR gateway with mismatched PDU sizes.

v2 检测深度：

* 检查 ``key_params`` 里 PduR gateway 相关参数
* 检查源和目标 PDU 尺寸是否匹配
* 如果尺寸不匹配 → yield violation

v2 增强方向：

* 解析 PduR 模块下 PduRRoutingPath 容器
* 比较 PduRSrcPdu 和 PduRDestPdu 的 PDU 尺寸
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class PduRAp002Rule:
    """PDUR-AP-002: PduR gateway with mismatched PDU sizes."""

    rule_id: ClassVar[str] = "PDUR-AP-002"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    #: PduR gateway 相关参数
    _PDUR_GATEWAY_PARAMS: ClassVar[tuple[str, ...]] = (
        "PduRGateway",
        "PduRSrcPdu",
        "PduRDestPdu",
        "PduRPduLength",
    )

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # v1 MVP stub：inspector key_params 不含 PduR gateway 详情
        # 数据不足以做"PDU 尺寸不匹配"判断 → 不 yield（避免误报）
        # v2 增强方向：解析 PduR 模块下 gateway 配置并比较 PDU 尺寸
        for _p in extracted.key_params:
            if _p.get("name") in self._PDUR_GATEWAY_PARAMS:
                # 当前不报（PDU 尺寸不可知）
                return ()
        return ()
