"""NVM-AP-001 — NvMBlockCrcType 未配置。

Sprint 12 T12.1。NvMBlockDescriptor 缺少 NvMBlockCrcType 时告警。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class NvmAp001Rule:
    """NVM-AP-001: NvMBlockCrcType not configured."""

    rule_id: ClassVar[str] = "NVM-AP-001"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "arxml"

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        for block in extracted.nvm_blocks:
            crc_type = block.get("NvMBlockCrcType")
            if crc_type is None:
                yield LintViolation(
                    rule_id=self.rule_id,
                    severity=self.severity_default,
                    message="NvMBlockCrcType not configured",
                    location=block.get("name", "?"),
                    module=extracted.module_name,
                    suggestion="set NvMBlockCrcType (e.g. CRC16, CRC32)",
                )
