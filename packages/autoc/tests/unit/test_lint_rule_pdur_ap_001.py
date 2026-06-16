"""v2.4.1 — PDUR-AP-001 单测。

PduRRoutingPath without source and destination → ERROR。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.pdur_ap_001 import PduRAp001Rule


def _mk_data(
    key_params: tuple[dict, ...] = (),
    module_name: str = "PduR",
) -> ArxmlLintData:
    return ArxmlLintData(
        module_name=module_name,
        ipdus=(),
        signals_by_ipdu={},
        key_params=key_params,
    )


class TestPduRAp001Rule:
    def test_stub_no_violation(self) -> None:
        """v1 stub：不 yield。"""
        data = _mk_data()
        assert list(PduRAp001Rule().check(data)) == []

    def test_with_routing_param_no_violation(self) -> None:
        """有 routing 参数但数据不足 → 不报。"""
        data = _mk_data(
            key_params=({"name": "PduRRoutingPath", "value": "Route1"},)
        )
        assert list(PduRAp001Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = PduRAp001Rule()
        assert rule.rule_id == "PDUR-AP-001"
        assert rule.severity_default == LintSeverity.ERROR
        assert rule.applies_to == "arxml"
