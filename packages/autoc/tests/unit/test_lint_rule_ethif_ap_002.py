"""v2.4.1 — ETHIF-AP-002 单测。

EthIfSwitchPortGroup empty but switching enabled → WARNING。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.ethif_ap_002 import EthIfAp002Rule


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


class TestEthIfAp002Rule:
    def test_stub_no_violation(self) -> None:
        """v1 stub：不 yield。"""
        data = _mk_data()
        assert list(EthIfAp002Rule().check(data)) == []

    def test_with_switch_param_no_violation(self) -> None:
        """有 switch 参数但数据不足 → 不报。"""
        data = _mk_data(
            key_params=({"name": "EthIfSwitchPortGroup", "value": "PG1"},)
        )
        assert list(EthIfAp002Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = EthIfAp002Rule()
        assert rule.rule_id == "ETHIF-AP-002"
        assert rule.severity_default == LintSeverity.WARNING
        assert rule.applies_to == "arxml"
