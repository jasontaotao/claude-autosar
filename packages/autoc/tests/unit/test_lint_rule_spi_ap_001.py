"""v2.4.1 — SPI-AP-001 单测。

SpiSequence with no SpiJob configured → WARNING。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    LintSeverity,
    XdmLintData,
)
from claude_autosar.core.bsw.lint.rules.xdm_rules.spi_ap_001 import SpiAp001Rule


def _mk_data(
    leaves: tuple[dict, ...] = (),
    module_name: str = "Spi",
) -> XdmLintData:
    return XdmLintData(
        module_name=module_name,
        containers=(),
        leaves=leaves,
    )


class TestSpiAp001Rule:
    def test_stub_no_violation(self) -> None:
        """v1 stub：不 yield。"""
        data = _mk_data()
        assert list(SpiAp001Rule().check(data)) == []

    def test_with_sequence_leaf_no_violation(self) -> None:
        """有 sequence leaf 但数据不足 → 不报。"""
        data = _mk_data(
            leaves=({"path": "Spi/SpiSequence/SpiJobRef", "raw": "Job1"},)
        )
        assert list(SpiAp001Rule().check(data)) == []

    def test_non_xdm_data_skipped(self) -> None:
        """非 XdmLintData → skip。"""
        assert list(SpiAp001Rule().check("not_xdm_data")) == []

    def test_rule_metadata(self) -> None:
        rule = SpiAp001Rule()
        assert rule.rule_id == "SPI-AP-001"
        assert rule.severity_default == LintSeverity.WARNING
        assert rule.applies_to == "xdm"
