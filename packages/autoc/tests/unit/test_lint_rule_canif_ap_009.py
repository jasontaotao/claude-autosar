"""v2.4.1 — CANIF-AP-009 单测。

CanIfHrhSoftwareFilter with no HRH configured → WARNING。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.canif_ap_009 import CanIfAp009Rule


def _mk_data(
    key_params: tuple[dict, ...] = (),
    module_name: str = "CanIf",
) -> ArxmlLintData:
    return ArxmlLintData(
        module_name=module_name,
        ipdus=(),
        signals_by_ipdu={},
        key_params=key_params,
    )


class TestCanIfAp009Rule:
    def test_stub_no_violation(self) -> None:
        """v1 stub：不 yield。"""
        data = _mk_data()
        assert list(CanIfAp009Rule().check(data)) == []

    def test_with_hrh_param_no_violation(self) -> None:
        """有 HRH 参数但数据不足 → 不报。"""
        data = _mk_data(
            key_params=({"name": "CanIfHrhSoftwareFilter", "value": "true"},)
        )
        assert list(CanIfAp009Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = CanIfAp009Rule()
        assert rule.rule_id == "CANIF-AP-009"
        assert rule.severity_default == LintSeverity.WARNING
        assert rule.applies_to == "arxml"
