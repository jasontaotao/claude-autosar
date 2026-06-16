"""v2.4.1 — PORT-AP-002 单测（重写版）。

Output PortPin missing PortPinInitialValue → WARNING。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    LintSeverity,
    XdmLintData,
)
from claude_autosar.core.bsw.lint.rules.xdm_rules.port_ap_002 import PortAp002Rule


def _mk_data(
    leaves: tuple[dict, ...] = (),
    module_name: str = "Port",
) -> XdmLintData:
    return XdmLintData(
        module_name=module_name,
        containers=(),
        leaves=leaves,
    )


class TestPortAp002Rule:
    def test_stub_no_violation(self) -> None:
        """v1 stub：不 yield。"""
        data = _mk_data()
        assert list(PortAp002Rule().check(data)) == []

    def test_with_pin_leaf_no_violation(self) -> None:
        """有 pin leaf 但数据不足 → 不报。"""
        data = _mk_data(
            leaves=({"path": "Port/PortPin/PortPinDirection", "raw": "PORT_PIN_OUT"},)
        )
        assert list(PortAp002Rule().check(data)) == []

    def test_non_xdm_data_skipped(self) -> None:
        """非 XdmLintData → skip。"""
        assert list(PortAp002Rule().check("not_xdm_data")) == []

    def test_rule_metadata(self) -> None:
        rule = PortAp002Rule()
        assert rule.rule_id == "PORT-AP-002"
        assert rule.severity_default == LintSeverity.WARNING
        assert rule.applies_to == "xdm"
