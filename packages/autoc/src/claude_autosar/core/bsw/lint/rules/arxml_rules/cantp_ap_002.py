"""CANTP-AP-002 — CanTpRxTaType mismatch with addressing mode.

v2 检测深度：

* 检查 ``key_params`` 里 CanTpRxTaType 相关参数
* 检查 RxTaType 是否与 addressing mode 匹配
* 如果不匹配 → yield violation

v2 增强方向：

* 解析 CanTp 模块下 CanTpChannel 容器
* 比较 CanTpRxTaType 与 CanTpAddressingMode
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class CanTpAp002Rule:
    """CANTP-AP-002: CanTpRxTaType mismatch with addressing mode."""

    rule_id: ClassVar[str] = "CANTP-AP-002"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    #: CanTp addressing 相关参数
    _CANTP_ADDRESSING_PARAMS: ClassVar[tuple[str, ...]] = (
        "CanTpRxTaType",
        "CanTpAddressingMode",
        "CanTpChannel",
    )

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # v1 MVP stub：inspector key_params 不含 CanTp addressing 详情
        # 数据不足以做"RxTaType 不匹配"判断 → 不 yield（避免误报）
        # v2 增强方向：解析 CanTp 模块下 addressing 配置并比较
        for _p in extracted.key_params:
            if _p.get("name") in self._CANTP_ADDRESSING_PARAMS:
                # 当前不报（addressing 配置不可知）
                return ()
        return ()
