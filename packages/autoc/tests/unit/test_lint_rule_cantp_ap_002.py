"""v2.4.1 — CANTP-AP-002 单测。

CanTpRxTaType mismatch with addressing mode → WARNING。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.cantp_ap_002 import CanTpAp002Rule


def _mk_data(
    key_params: tuple[dict, ...] = (),
    module_name: str = "CanTp",
) -> ArxmlLintData:
    return ArxmlLintData(
        module_name=module_name,
        ipdus=(),
        signals_by_ipdu={},
        key_params=key_params,
    )


class TestCanTpAp002Rule:
    def test_stub_no_violation(self) -> None:
        """v1 stub：不 yield。"""
        data = _mk_data()
        assert list(CanTpAp002Rule().check(data)) == []

    def test_with_addressing_param_no_violation(self) -> None:
        """有 addressing 参数但数据不足 → 不报。"""
        data = _mk_data(
            key_params=({"name": "CanTpRxTaType", "value": "PHYSICAL"},)
        )
        assert list(CanTpAp002Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = CanTpAp002Rule()
        assert rule.rule_id == "CANTP-AP-002"
        assert rule.severity_default == LintSeverity.WARNING
        assert rule.applies_to == "arxml"
