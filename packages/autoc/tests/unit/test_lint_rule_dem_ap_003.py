"""v2.4.1 — DEM-AP-003 单测。

DemFreezeFrameEvent exceeds max count → WARNING。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.dem_ap_003 import DemAp003Rule


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


class TestDemAp003Rule:
    def test_stub_no_violation(self) -> None:
        """v1 stub：不 yield。"""
        data = _mk_data()
        assert list(DemAp003Rule().check(data)) == []

    def test_with_freeze_frame_param_no_violation(self) -> None:
        """有 freeze frame 参数但数据不足 → 不报。"""
        data = _mk_data(
            key_params=({"name": "DemFreezeFrameEvent", "value": "FF1"},)
        )
        assert list(DemAp003Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = DemAp003Rule()
        assert rule.rule_id == "DEM-AP-003"
        assert rule.severity_default == LintSeverity.WARNING
        assert rule.applies_to == "arxml"
