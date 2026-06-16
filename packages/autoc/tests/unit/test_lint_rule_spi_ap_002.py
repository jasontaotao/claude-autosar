"""v2.4.1 — SPI-AP-002 单测。

SpiJob with invalid data width for channel → ERROR。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    LintSeverity,
    XdmLintData,
)
from claude_autosar.core.bsw.lint.rules.xdm_rules.spi_ap_002 import SpiAp002Rule


def _mk_data(
    leaves: tuple[dict, ...] = (),
    module_name: str = "Spi",
) -> XdmLintData:
    return XdmLintData(
        module_name=module_name,
        containers=(),
        leaves=leaves,
    )


class TestSpiAp002Rule:
    def test_stub_no_violation(self) -> None:
        """v1 stub：不 yield。"""
        data = _mk_data()
        assert list(SpiAp002Rule().check(data)) == []

    def test_with_job_leaf_no_violation(self) -> None:
        """有 job leaf 但数据不足 → 不报。"""
        data = _mk_data(
            leaves=({"path": "Spi/SpiJob/SpiDataWidth", "raw": "8"},)
        )
        assert list(SpiAp002Rule().check(data)) == []

    def test_non_xdm_data_skipped(self) -> None:
        """非 XdmLintData → skip。"""
        assert list(SpiAp002Rule().check("not_xdm_data")) == []

    def test_rule_metadata(self) -> None:
        rule = SpiAp002Rule()
        assert rule.rule_id == "SPI-AP-002"
        assert rule.severity_default == LintSeverity.ERROR
        assert rule.applies_to == "xdm"
