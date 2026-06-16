"""v2.4.1 — NM-AP-003 单测。

NmPnEnabled but no partial networking config → WARNING。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.nm_ap_003 import NmAp003Rule


def _mk_data(
    key_params: tuple[dict, ...] = (),
    module_name: str = "Nm",
) -> ArxmlLintData:
    return ArxmlLintData(
        module_name=module_name,
        ipdus=(),
        signals_by_ipdu={},
        key_params=key_params,
    )


class TestNmAp003Rule:
    def test_stub_no_violation(self) -> None:
        """v1 stub：不 yield。"""
        data = _mk_data()
        assert list(NmAp003Rule().check(data)) == []

    def test_with_pn_param_no_violation(self) -> None:
        """有 PN 参数但数据不足 → 不报。"""
        data = _mk_data(
            key_params=({"name": "NmPnEnabled", "value": "true"},)
        )
        assert list(NmAp003Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = NmAp003Rule()
        assert rule.rule_id == "NM-AP-003"
        assert rule.severity_default == LintSeverity.WARNING
        assert rule.applies_to == "arxml"
