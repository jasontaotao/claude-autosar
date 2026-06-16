"""v2.4.1 — FRIF-AP-001 单测。

FrIfCluster without FrIfController → ERROR。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.frif_ap_001 import FrIfAp001Rule


def _mk_data(
    key_params: tuple[dict, ...] = (),
    module_name: str = "FrIf",
) -> ArxmlLintData:
    return ArxmlLintData(
        module_name=module_name,
        ipdus=(),
        signals_by_ipdu={},
        key_params=key_params,
    )


class TestFrIfAp001Rule:
    def test_stub_no_violation(self) -> None:
        """v1 stub：不 yield。"""
        data = _mk_data()
        assert list(FrIfAp001Rule().check(data)) == []

    def test_with_cluster_param_no_violation(self) -> None:
        """有 cluster 参数但数据不足 → 不报。"""
        data = _mk_data(
            key_params=({"name": "FrIfCluster", "value": "Cl1"},)
        )
        assert list(FrIfAp001Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = FrIfAp001Rule()
        assert rule.rule_id == "FRIF-AP-001"
        assert rule.severity_default == LintSeverity.ERROR
        assert rule.applies_to == "arxml"
