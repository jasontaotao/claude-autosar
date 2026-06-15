"""Sprint 9.4 T9.4-α — DEM-AP-001 单测。"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    XdmLintData,
)
from claude_autosar.core.bsw.lint.rules.xdm_rules.dem_ap_001 import DemAp001Rule


def _mk_xdm(
    leaves: tuple[dict, ...] = (),
    module_name: str = "Dem",
) -> XdmLintData:
    return XdmLintData(
        module_name=module_name,
        containers=(),
        leaves=leaves,
    )


class TestDemAp001Rule:
    def test_empty_data_no_violation(self) -> None:
        assert list(DemAp001Rule().check(_mk_xdm())) == []

    def test_arxml_data_skipped(self) -> None:
        """非 XDM 数据 → 跳过（不抛异常）。"""
        arxml_data = ArxmlLintData(
            module_name="Com",
            ipdus=(),
            signals_by_ipdu={},
            key_params=(),
        )
        assert list(DemAp001Rule().check(arxml_data)) == []

    def test_with_unrelated_leaves_no_violation(self) -> None:
        data = _mk_xdm(
            leaves=({"name": "Foo", "type": "INTEGER", "value": "1", "path": "Dem/General/Foo"},)
        )
        assert list(DemAp001Rule().check(data)) == []

    def test_v1_stub_no_violation_with_dem_path(self) -> None:
        """v1 MVP stub — 即使 path 含 DemPrimaryMemory 也 0 报。"""
        data = _mk_xdm(
            leaves=(
                {
                    "name": "StartAddress",
                    "type": "INTEGER",
                    "value": "0x80000000",
                    "path": "Dem/DemPrimaryMemory/StartAddress",
                },
            )
        )
        assert list(DemAp001Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = DemAp001Rule()
        assert rule.rule_id == "DEM-AP-001"
        assert rule.severity_default == LintSeverity.ERROR

    def test_returns_iterable(self) -> None:
        result = DemAp001Rule().check(_mk_xdm())
        assert result is not None
        assert list(result) == []
