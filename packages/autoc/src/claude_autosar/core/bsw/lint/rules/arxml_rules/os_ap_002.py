"""OS-AP-002 — OsTask 优先级重复。

Sprint 12 T12.1。多个 OsTask 使用相同优先级时告警。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class OsAp002Rule:
    """OS-AP-002: Duplicate OsTask priority."""

    rule_id: ClassVar[str] = "OS-AP-002"
    severity_default: ClassVar[str] = LintSeverity.WARNING
    applies_to: ClassVar[str] = "arxml"

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        seen: dict[str, str] = {}  # priority → task name
        for task in extracted.os_tasks:
            priority_str = task.get("OsTaskPriority")
            if priority_str is None:
                continue
            task_name = task.get("name", "?")
            if priority_str in seen:
                yield LintViolation(
                    rule_id=self.rule_id,
                    severity=self.severity_default,
                    message=(
                        f"OsTask priority {priority_str} used by both "
                        f"{seen[priority_str]} and {task_name}"
                    ),
                    location=task_name,
                    module=extracted.module_name,
                    suggestion="assign unique priorities to each OsTask",
                )
            else:
                seen[priority_str] = task_name
