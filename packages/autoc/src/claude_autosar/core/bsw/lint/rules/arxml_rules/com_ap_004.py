"""COM-AP-004 — Duplicate ComIPdu handle IDs.

v2 检测深度：

* 遍历 ``ipdus``，提取每个 IPdu 的 ``ComIPduHandleId``
* 检测重复的 handle ID → yield violation

v2 增强方向：

* 支持 ComTxIPdu / ComRxIPdu 分别检查
* 考虑 handle ID 范围（0-65535）
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    LintViolation,
)


class ComAp004Rule:
    """COM-AP-004: Duplicate ComIPdu handle IDs."""

    rule_id: ClassVar[str] = "COM-AP-004"
    severity_default: ClassVar[str] = LintSeverity.ERROR
    applies_to: ClassVar[str] = "arxml"  # 只吃 ArxmlLintData

    def check(self, extracted: ArxmlLintData) -> Iterable[LintViolation]:
        # 收集所有 handle ID
        handle_ids: dict[str, str] = {}  # handle_id -> ipdu_name

        for ipdu in extracted.ipdus:
            handle_id = str(ipdu.get("ComIPduHandleId", ""))
            ipdu_name = str(ipdu.get("name", ""))

            if not handle_id or not ipdu_name:
                continue

            if handle_id in handle_ids:
                # 发现重复
                yield LintViolation(
                    rule_id=self.rule_id,
                    severity=self.severity_default,
                    message=(
                        f"Duplicate ComIPduHandleId '{handle_id}': "
                        f"'{ipdu_name}' and '{handle_ids[handle_id]}'"
                    ),
                    location=ipdu_name,
                    module=extracted.module_name,
                    suggestion="Assign unique handle IDs to each ComIPdu",
                )
            else:
                handle_ids[handle_id] = ipdu_name
