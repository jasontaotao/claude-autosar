"""CANIF-AP-007 — 软件全开 + 硬件全关 = CPU 风暴。

v1 MVP 检测深度：

* ``key_params`` 里找 ``CanIfTxConfirmation`` / ``CanIfRxIndication`` 等
  软件回调是否 enabled；以及 ``CanIfHardwareObject`` count = 0
* 数据不足（v1 没解析 CanIfHardwareObject 容器数量）→ 跳过

v2 增强方向：

* 解析 ``CanIfInitCfg`` 子容器里的 ``CanIfHardwareObject`` 实际 count
* 跨字段联合：software_enabled && hw_count == 0 → violation
"""

from __future__ import annotations

from typing import ClassVar
from collections.abc import Iterable

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class CanIfAp007Rule:
    """CANIF-AP-007: software enabled but no hardware objects → CPU storm."""

    rule_id: ClassVar[str] = "CANIF-AP-007"
    severity_default: ClassVar[str] = LintSeverity.ERROR
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    #: v1 简化：只检查 CanIfDispatchCfg 的关键 software enable 字段
    _SOFTWARE_ENABLE_PARAMS: ClassVar[tuple[str, ...]] = (
        "CanIfTxConfirmationDispatch",
        "CanIfRxIndicationDispatch",
        "CanIfDispatchUserCtrlService",
    )

    def check(
        self, extracted: ArxmlLintData
    ) -> Iterable[LintViolation]:
        # v1 MVP stub：inspector key_params 不含 CanIfHardwareObject 计数
        # 数据不足以做"软件全开+硬件全关"判断 → 不 yield（避免误报）
        # 触发条件：key_params 里出现上述任意 software_enable 参数且值为
        # TRUE/TRUE，但 CanIfHardwareObject count 不可知
        # v2 增强方向：解析 CanIfInitCfg 子容器里的 CanIfHardwareObject count
        for _p in extracted.key_params:
            if _p.get("name") in self._SOFTWARE_ENABLE_PARAMS:
                # 当前不报（hw count 不可知）
                return ()
        return ()
