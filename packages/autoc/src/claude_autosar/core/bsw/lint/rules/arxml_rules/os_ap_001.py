"""OS-AP-001 — OsTask stack size 过小。

Sprint 12 T12.1。OsTaskStackDepth < 512 字节时告警。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class OsAp001Rule:
    """OS-AP-001: OsTask stack size too small."""

    rule_id: ClassVar[str] = "OS-AP-001"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "arxml"

    _MIN_STACK_SIZE: ClassVar[int] = 512

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        for task in extracted.os_tasks:
            stack_str = task.get("OsTaskStackDepth")
            if stack_str is None:
                continue
            try:
                stack = int(stack_str)
            except (TypeError, ValueError):
                continue
            if stack < self._MIN_STACK_SIZE:
                yield LintViolation(
                    rule_id=self.rule_id,
                    severity=self.severity_default,
                    message=f"OsTask stack size {stack} < {self._MIN_STACK_SIZE} bytes",
                    location=task.get("name", "?"),
                    module=extracted.module_name,
                    suggestion="increase OsTaskStackDepth to at least 512",
                )
