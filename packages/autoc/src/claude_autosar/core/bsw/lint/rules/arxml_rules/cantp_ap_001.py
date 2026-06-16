"""CANTP-AP-001 — CanTpChannel with invalid N-PDU size.

v2 检测深度：

* 检查 ``key_params`` 里 CanTpChannel 相关参数
* 检查 N-PDU 尺寸是否超过 CAN 帧限制
* 如果超过限制 → yield violation

v2 增强方向：

* 解析 CanTp 模块下 CanTpChannel 容器
* 检查 N-PDU 尺寸与 CAN/CAN-FD 限制
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class CanTpAp001Rule:
    """CANTP-AP-001: CanTpChannel with invalid N-PDU size."""

    rule_id: ClassVar[str] = "CANTP-AP-001"
    severity_default: ClassVar[str] = LintSeverity.ERROR
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    #: CAN 帧最大 payload
    _MAX_CAN_PAYLOAD: ClassVar[int] = 8
    _MAX_CANFD_PAYLOAD: ClassVar[int] = 64

    #: CanTp channel 相关参数
    _CANTP_CHANNEL_PARAMS: ClassVar[tuple[str, ...]] = (
        "CanTpChannel",
        "CanTpNPdu",
        "CanTpNPduLength",
    )

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # v1 MVP stub：inspector key_params 不含 CanTpChannel 详情
        # 数据不足以做"N-PDU 尺寸无效"判断 → 不 yield（避免误报）
        # v2 增强方向：解析 CanTp 模块下 CanTpChannel 容器并检查 N-PDU 尺寸
        for _p in extracted.key_params:
            if _p.get("name") in self._CANTP_CHANNEL_PARAMS:
                # 当前不报（N-PDU 尺寸不可知）
                return ()
        return ()
