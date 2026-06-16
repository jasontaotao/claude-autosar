"""v2.4.1 — COM-AP-003 单测。

ComSignal without ComIPdu reference → ERROR。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.com_ap_003 import ComAp003Rule


def _mk_data(
    signals_by_ipdu: dict[str, tuple[dict, ...]] | None = None,
    module_name: str = "Com",
) -> ArxmlLintData:
    return ArxmlLintData(
        module_name=module_name,
        ipdus=(),
        signals_by_ipdu=signals_by_ipdu or {},
        key_params=(),
    )


class TestComAp003Rule:
    def test_no_signals_no_violation(self) -> None:
        """无 signal 数据 → 不报（FP=0 优先）。"""
        data = _mk_data()
        assert list(ComAp003Rule().check(data)) == []

    def test_signals_referenced_no_violation(self) -> None:
        """signal 被 IPdu 引用 → 不报。"""
        data = _mk_data(
            signals_by_ipdu={
                "TxPdu": ({"name": "S1"},),
            }
        )
        assert list(ComAp003Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = ComAp003Rule()
        assert rule.rule_id == "COM-AP-003"
        assert rule.severity_default == LintSeverity.ERROR
        assert rule.applies_to == "arxml"

    def test_iterable_returned(self) -> None:
        data = _mk_data()
        result = ComAp003Rule().check(data)
        assert result is not None
        assert list(result) == []
