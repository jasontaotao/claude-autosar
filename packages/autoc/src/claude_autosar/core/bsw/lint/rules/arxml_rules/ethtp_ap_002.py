"""ETHTP-AP-002 — EthTpRxBufferCount 为 0。

Sprint 12 T12.1。EthTp 接收缓冲区数量为 0 时告警。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class EthtpAp002Rule:
    """ETHTP-AP-002: EthTpRxBufferCount is 0."""

    rule_id: ClassVar[str] = "ETHTP-AP-002"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "arxml"

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        for param in extracted.key_params:
            if "EthTpRxBufferCount" in param.get("name", ""):
                value_str = param.get("value")
                if value_str is not None:
                    try:
                        value = int(value_str)
                    except (TypeError, ValueError):
                        continue
                    if value < 1:
                        yield LintViolation(
                            rule_id=self.rule_id,
                            severity=self.severity_default,
                            message=f"EthTpRxBufferCount is {value} (should be >= 1)",
                            location=param.get("container", "?"),
                            module=extracted.module_name,
                            suggestion="set EthTpRxBufferCount >= 1",
                        )
