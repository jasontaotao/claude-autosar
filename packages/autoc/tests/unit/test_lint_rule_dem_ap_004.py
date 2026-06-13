"""Sprint 9.4 T9.4-α — DEM-AP-004 单测。"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
    XdmLintData,
)
from claude_autosar.core.bsw.lint.rules.xdm_rules.dem_ap_004 import DemAp004Rule


def _mk_xdm(leaves: tuple[dict, ...] = ()) -> XdmLintData:
    return XdmLintData(
        module_name="Dem",
        containers=(),
        leaves=leaves,
    )


class TestDemAp004Rule:
    def test_empty_data_no_violation(self) -> None:
        assert list(DemAp004Rule().check(_mk_xdm())) == []

    def test_arxml_data_skipped(self) -> None:
        arxml_data = ArxmlLintData(
            module_name="Com",
            ipdus=(),
            signals_by_ipdu={},
            key_params=(),
        )
        assert list(DemAp004Rule().check(arxml_data)) == []

    def test_v1_stub_no_violation(self) -> None:
        data = _mk_xdm(
            leaves=(
                {"name": "SnapshotDataLength", "type": "INTEGER",
                 "value": "256", "path": "Dem/DemEventParameter/E1/SnapshotDataLength"},
            )
        )
        assert list(DemAp004Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = DemAp004Rule()
        assert rule.rule_id == "DEM-AP-004"
        assert rule.severity_default == LintSeverity.ERROR

    def test_returns_iterable(self) -> None:
        result = DemAp004Rule().check(_mk_xdm())
        assert result is not None
