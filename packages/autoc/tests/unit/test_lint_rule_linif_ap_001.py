"""v2.4.1 — LINIF-AP-001 单测。

LinIfScheduleTable without entries → WARNING。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.linif_ap_001 import LinIfAp001Rule


def _mk_data(
    key_params: tuple[dict, ...] = (),
    module_name: str = "LinIf",
) -> ArxmlLintData:
    return ArxmlLintData(
        module_name=module_name,
        ipdus=(),
        signals_by_ipdu={},
        key_params=key_params,
    )


class TestLinIfAp001Rule:
    def test_stub_no_violation(self) -> None:
        """v1 stub：不 yield。"""
        data = _mk_data()
        assert list(LinIfAp001Rule().check(data)) == []

    def test_with_schedule_param_no_violation(self) -> None:
        """有 schedule 参数但数据不足 → 不报。"""
        data = _mk_data(
            key_params=({"name": "LinIfScheduleTable", "value": "ST1"},)
        )
        assert list(LinIfAp001Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = LinIfAp001Rule()
        assert rule.rule_id == "LINIF-AP-001"
        assert rule.severity_default == LintSeverity.WARNING
        assert rule.applies_to == "arxml"
