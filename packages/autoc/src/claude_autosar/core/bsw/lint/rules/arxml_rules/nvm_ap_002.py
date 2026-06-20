"""NVM-AP-002 — NvMBlockSize 未对齐到 8 字节。

Sprint 12 T12.1。NvMBlockSize 不是 8 的倍数时告警。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class NvmAp002Rule:
    """NVM-AP-002: NvMBlockSize not aligned to 8 bytes."""

    rule_id: ClassVar[str] = "NVM-AP-002"
    severity_default: ClassVar[str] = LintSeverity.INFO
    applies_to: ClassVar[str] = "arxml"

    _ALIGNMENT: ClassVar[int] = 8

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        for block in extracted.nvm_blocks:
            size_str = block.get("NvMBlockSize")
            if size_str is None:
                continue
            try:
                size = int(size_str)
            except (TypeError, ValueError):
                continue
            if size % self._ALIGNMENT != 0:
                yield LintViolation(
                    rule_id=self.rule_id,
                    severity=self.severity_default,
                    message=f"NvMBlockSize {size} not aligned to {self._ALIGNMENT} bytes",
                    location=block.get("name", "?"),
                    module=extracted.module_name,
                    suggestion=f"round NvMBlockSize up to nearest {self._ALIGNMENT}",
                )
