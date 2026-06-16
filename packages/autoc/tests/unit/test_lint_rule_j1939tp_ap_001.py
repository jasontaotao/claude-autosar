"""v2.4.1 — J1939TP-AP-001 单测。

J1939TpChannel with invalid MTU → ERROR。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.j1939tp_ap_001 import (
    J1939TpAp001Rule,
)


def _mk_data(
    key_params: tuple[dict, ...] = (),
    module_name: str = "J1939Tp",
) -> ArxmlLintData:
    return ArxmlLintData(
        module_name=module_name,
        ipdus=(),
        signals_by_ipdu={},
        key_params=key_params,
    )


class TestJ1939TpAp001Rule:
    def test_stub_no_violation(self) -> None:
        """v1 stub：不 yield。"""
        data = _mk_data()
        assert list(J1939TpAp001Rule().check(data)) == []

    def test_with_channel_param_no_violation(self) -> None:
        """有 channel 参数但数据不足 → 不报。"""
        data = _mk_data(
            key_params=({"name": "J1939TpChannel", "value": "Ch1"},)
        )
        assert list(J1939TpAp001Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = J1939TpAp001Rule()
        assert rule.rule_id == "J1939TP-AP-001"
        assert rule.severity_default == LintSeverity.ERROR
        assert rule.applies_to == "arxml"
