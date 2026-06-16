"""ETHIF-AP-001 — EthIfController without Ethernet driver.

v2 检测深度：

* 检查 ``key_params`` 里 EthIfController 相关参数
* 检查 controller 是否引用了 Ethernet driver
* 如果没有驱动引用 → yield violation

v2 增强方向：

* 解析 EthIf 模块下 EthIfController 容器
* 检查 EthIfCtrlRef 是否指向有效的 Ethernet driver
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class EthIfAp001Rule:
    """ETHIF-AP-001: EthIfController without Ethernet driver."""

    rule_id: ClassVar[str] = "ETHIF-AP-001"
    severity_default: ClassVar[str] = LintSeverity.ERROR
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    #: EthIf controller 相关参数
    _ETHIF_CONTROLLER_PARAMS: ClassVar[tuple[str, ...]] = (
        "EthIfController",
        "EthIfCtrlRef",
        "EthIfEthDrvRef",
    )

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # v1 MVP stub：inspector key_params 不含 EthIfController 详情
        # 数据不足以做"controller 无驱动"判断 → 不 yield（避免误报）
        # v2 增强方向：解析 EthIf 模块下 EthIfController 容器和驱动引用
        for _p in extracted.key_params:
            if _p.get("name") in self._ETHIF_CONTROLLER_PARAMS:
                # 当前不报（driver 引用不可知）
                return ()
        return ()
