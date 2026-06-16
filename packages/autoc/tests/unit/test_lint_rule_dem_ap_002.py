"""v2.4.1 — DEM-AP-002 单测。

DemEventParameter without DTC mapping → WARNING。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.dem_ap_002 import DemAp002Rule


def _mk_data(
    key_params: tuple[dict, ...] = (),
    module_name: str = "Dem",
) -> ArxmlLintData:
    return ArxmlLintData(
        module_name=module_name,
        ipdus=(),
        signals_by_ipdu={},
        key_params=key_params,
    )


class TestDemAp002Rule:
    def test_stub_no_violation(self) -> None:
        """v1 stub：不 yield。"""
        data = _mk_data()
        assert list(DemAp002Rule().check(data)) == []

    def test_with_event_param_no_violation(self) -> None:
        """有 event 参数但数据不足 → 不报。"""
        data = _mk_data(
            key_params=({"name": "DemEventParameter", "value": "Evt1"},)
        )
        assert list(DemAp002Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = DemAp002Rule()
        assert rule.rule_id == "DEM-AP-002"
        assert rule.severity_default == LintSeverity.WARNING
        assert rule.applies_to == "arxml"
