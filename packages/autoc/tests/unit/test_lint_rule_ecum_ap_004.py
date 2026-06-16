"""v2.4.1 — ECUM-AP-004 单测。

EcuMWakeupSource configured but no validation → WARNING。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.ecum_ap_004 import EcuMAp004Rule


def _mk_data(
    key_params: tuple[dict, ...] = (),
    module_name: str = "EcuM",
) -> ArxmlLintData:
    return ArxmlLintData(
        module_name=module_name,
        ipdus=(),
        signals_by_ipdu={},
        key_params=key_params,
    )


class TestEcuMAp004Rule:
    def test_stub_no_violation(self) -> None:
        """v1 stub：不 yield。"""
        data = _mk_data()
        assert list(EcuMAp004Rule().check(data)) == []

    def test_with_wakeup_param_no_violation(self) -> None:
        """有唤醒源参数但数据不足 → 不报。"""
        data = _mk_data(
            key_params=({"name": "EcuMWakeupSource", "value": "CAN"},)
        )
        assert list(EcuMAp004Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = EcuMAp004Rule()
        assert rule.rule_id == "ECUM-AP-004"
        assert rule.severity_default == LintSeverity.WARNING
        assert rule.applies_to == "arxml"
