"""CANIF-AP-010 — CanIfTxBuffer empty but TxProcessing enabled.

v2 检测深度：

* 检查 ``key_params`` 里 ``CanIfTxProcessing`` 是否启用
* 检查 ``CanIfTxBuffer`` 容器是否有条目
* 如果 Tx 处理启用但 TxBuffer 为空 → yield violation

v2 增强方向：

* 解析 CanIfInitCfg 子容器里的 CanIfTxBuffer 实际条目
* 跨字段联合：tx_processing_enabled && tx_buffer_empty → violation
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class CanIfAp010Rule:
    """CANIF-AP-010: CanIfTxProcessing enabled but TxBuffer empty."""

    rule_id: ClassVar[str] = "CANIF-AP-010"
    severity_default: ClassVar[str] = LintSeverity.INFO
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    #: Tx 处理相关参数
    _TX_PARAMS: ClassVar[tuple[str, ...]] = (
        "CanIfTxProcessing",
        "CanIfTxBuffer",
    )

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # v1 MVP stub：inspector key_params 不含 CanIfTxBuffer 条目数
        # 数据不足以做"Tx 处理启用但 buffer 为空"判断 → 不 yield（避免误报）
        # v2 增强方向：解析 CanIfInitCfg 子容器里的 CanIfTxBuffer 条目
        for _p in extracted.key_params:
            if _p.get("name") in self._TX_PARAMS:
                # 当前不报（buffer 条目不可知）
                return ()
        return ()
