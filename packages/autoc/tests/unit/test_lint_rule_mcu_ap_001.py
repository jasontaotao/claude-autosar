"""v2.4.1 — MCU-AP-001 单测。

McuClockSettingConfig with zero frequency → ERROR。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    LintSeverity,
    XdmLintData,
)
from claude_autosar.core.bsw.lint.rules.xdm_rules.mcu_ap_001 import McuAp001Rule


def _mk_data(
    leaves: tuple[dict, ...] = (),
    module_name: str = "Mcu",
) -> XdmLintData:
    return XdmLintData(
        module_name=module_name,
        containers=(),
        leaves=leaves,
    )


class TestMcuAp001Rule:
    def test_stub_no_violation(self) -> None:
        """v1 stub：不 yield。"""
        data = _mk_data()
        assert list(McuAp001Rule().check(data)) == []

    def test_with_clock_leaf_no_violation(self) -> None:
        """有 clock leaf 但数据不足 → 不报。"""
        data = _mk_data(
            leaves=({"path": "Mcu/McuClockSettingConfig/McuClockFrequency", "raw": "0"},)
        )
        assert list(McuAp001Rule().check(data)) == []

    def test_non_xdm_data_skipped(self) -> None:
        """非 XdmLintData → skip。"""
        assert list(McuAp001Rule().check("not_xdm_data")) == []

    def test_rule_metadata(self) -> None:
        rule = McuAp001Rule()
        assert rule.rule_id == "MCU-AP-001"
        assert rule.severity_default == LintSeverity.ERROR
        assert rule.applies_to == "xdm"
