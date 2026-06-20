"""FEE-AP-001 — FeeBlockSize < NvMBlockSize。

Sprint 12 T12.1。Fee 块大小必须 >= NvM 块大小。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class FeeAp001Rule:
    """FEE-AP-001: FeeBlockSize < NvMBlockSize."""

    rule_id: ClassVar[str] = "FEE-AP-001"
    severity_default: ClassVar[str] = LintSeverity.ERROR
    applies_to: ClassVar[str] = "arxml"

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # 构建 NvM block name → size 映射
        nvm_sizes: dict[str, int] = {}
        for block in extracted.nvm_blocks:
            name = block.get("name", "")
            size_str = block.get("NvMBlockSize")
            if size_str is not None:
                try:
                    nvm_sizes[name] = int(size_str)
                except (TypeError, ValueError):
                    pass

        for fee_block in extracted.fee_blocks:
            fee_name = fee_block.get("name", "")
            fee_size_str = fee_block.get("FeeBlockSize")
            if fee_size_str is None:
                continue
            try:
                fee_size = int(fee_size_str)
            except (TypeError, ValueError):
                continue

            # 同名 NvM block 存在时比较
            nvm_size = nvm_sizes.get(fee_name)
            if nvm_size is not None and fee_size < nvm_size:
                yield LintViolation(
                    rule_id=self.rule_id,
                    severity=self.severity_default,
                    message=f"FeeBlockSize {fee_size} < NvMBlockSize {nvm_size}",
                    location=fee_name,
                    module=extracted.module_name,
                    suggestion=f"set FeeBlockSize >= {nvm_size}",
                )
