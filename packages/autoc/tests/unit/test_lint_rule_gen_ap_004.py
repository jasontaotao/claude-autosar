"""v2.4.1 — GEN-AP-004 单测。

BswMRule without conditions → WARNING。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.gen_ap_004 import GenAp004Rule


def _mk_data(
    key_params: tuple[dict, ...] = (),
    module_name: str = "BswM",
) -> ArxmlLintData:
    return ArxmlLintData(
        module_name=module_name,
        ipdus=(),
        signals_by_ipdu={},
        key_params=key_params,
    )


class TestGenAp004Rule:
    def test_stub_no_violation(self) -> None:
        """v1 stub：不 yield。"""
        data = _mk_data()
        assert list(GenAp004Rule().check(data)) == []

    def test_with_rule_param_no_violation(self) -> None:
        """有 rule 参数但数据不足 → 不报。"""
        data = _mk_data(
            key_params=({"name": "BswMRule", "value": "MyRule"},)
        )
        assert list(GenAp004Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = GenAp004Rule()
        assert rule.rule_id == "GEN-AP-004"
        assert rule.severity_default == LintSeverity.WARNING
        assert rule.applies_to == "arxml"
