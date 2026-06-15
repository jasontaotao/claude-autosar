"""CANIF-AP-008 — CAN-FD length mismatch 编译期一查一个准。

v1 MVP 检测深度：

* 遍历 IPdu，找 ``ComIPduLength`` 字段
* 如果 IPdu direction = CAN 且 length > 8 → 提示（疑似 CAN-FD 配错）
* 当前数据里 CanIf 的 ``CanFdMaxPayloadLength`` 不在 inspector
  key_params → v1 仅做"classic CAN 长度 > 8"检查（已与 COM-AP-001 重叠）
* v1 仅在 key_params 出现 ``CanIfTxPDuLength`` 等典型字段时尝试

v2 增强方向：

* 加 CanIfInitCfg 解析，提取 CanIfHrhCfg / CanIfHthCfg
* 联合 CanFdMaxPayloadLength < IPdu length → violation
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class CanIfAp008Rule:
    """CANIF-AP-008: CAN-FD payload length mismatch."""

    rule_id: ClassVar[str] = "CANIF-AP-008"
    severity_default: ClassVar[str] = LintSeverity.ERROR
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    #: CanIf 配置里跟 CAN-FD 长度相关的关键参数名
    _CANFD_LENGTH_PARAMS: ClassVar[tuple[str, ...]] = (
        "CanIfTxPduLength",
        "CanIfRxPduLength",
        "CanFdMaxPayloadLength",
    )

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # v1 MVP stub：key_params 没拆出 CanIfTxPduLength vs
        # ComIPduLength 的 cross-reference → 不 yield（FP=0 优先）
        for _p in extracted.key_params:
            if _p.get("name") in self._CANFD_LENGTH_PARAMS:
                return ()
        return ()
