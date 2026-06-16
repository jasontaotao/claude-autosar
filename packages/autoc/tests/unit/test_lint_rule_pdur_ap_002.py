"""v2.4.1 — PDUR-AP-002 单测。

PduR gateway with mismatched PDU sizes → ERROR。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.pdur_ap_002 import PduRAp002Rule


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


class TestPduRAp002Rule:
    def test_stub_no_violation(self) -> None:
        """v1 stub：不 yield。"""
        data = _mk_data()
        assert list(PduRAp002Rule().check(data)) == []

    def test_with_gateway_param_no_violation(self) -> None:
        """有 gateway 参数但数据不足 → 不报。"""
        data = _mk_data(
            key_params=({"name": "PduRGateway", "value": "GW1"},)
        )
        assert list(PduRAp002Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = PduRAp002Rule()
        assert rule.rule_id == "PDUR-AP-002"
        assert rule.severity_default == LintSeverity.WARNING
        assert rule.applies_to == "arxml"
