"""v2.4.1 — ETHIF-AP-001 单测。

EthIfController without Ethernet driver → ERROR。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.ethif_ap_001 import EthIfAp001Rule


def _mk_data(
    key_params: tuple[dict, ...] = (),
    module_name: str = "EthIf",
) -> ArxmlLintData:
    return ArxmlLintData(
        module_name=module_name,
        ipdus=(),
        signals_by_ipdu={},
        key_params=key_params,
    )


class TestEthIfAp001Rule:
    def test_stub_no_violation(self) -> None:
        """v1 stub：不 yield。"""
        data = _mk_data()
        assert list(EthIfAp001Rule().check(data)) == []

    def test_with_controller_param_no_violation(self) -> None:
        """有 controller 参数但数据不足 → 不报。"""
        data = _mk_data(
            key_params=({"name": "EthIfController", "value": "Ctrl1"},)
        )
        assert list(EthIfAp001Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = EthIfAp001Rule()
        assert rule.rule_id == "ETHIF-AP-001"
        assert rule.severity_default == LintSeverity.ERROR
        assert rule.applies_to == "arxml"
