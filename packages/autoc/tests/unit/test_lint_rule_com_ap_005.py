"""v2.4.1 — COM-AP-005 单测。

ComSignalGroup without signals → WARNING。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.com_ap_005 import ComAp005Rule


def _mk_data(
    module_name: str = "Com",
) -> ArxmlLintData:
    return ArxmlLintData(
        module_name=module_name,
        ipdus=(),
        signals_by_ipdu={},
        key_params=(),
    )


class TestComAp005Rule:
    def test_stub_no_violation(self) -> None:
        """v1 stub：不 yield。"""
        data = _mk_data()
        assert list(ComAp005Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = ComAp005Rule()
        assert rule.rule_id == "COM-AP-005"
        assert rule.severity_default == LintSeverity.WARNING
        assert rule.applies_to == "arxml"

    def test_iterable_returned(self) -> None:
        result = ComAp005Rule().check(_mk_data())
        assert result is not None
        assert list(result) == []
