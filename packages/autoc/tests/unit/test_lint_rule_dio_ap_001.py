"""v2.4.1 — DIO-AP-001 单测。

DioChannelGroup with invalid channel range → ERROR。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    LintSeverity,
    XdmLintData,
)
from claude_autosar.core.bsw.lint.rules.xdm_rules.dio_ap_001 import DioAp001Rule


def _mk_data(
    leaves: tuple[dict, ...] = (),
    module_name: str = "Dio",
) -> XdmLintData:
    return XdmLintData(
        module_name=module_name,
        containers=(),
        leaves=leaves,
    )


class TestDioAp001Rule:
    def test_stub_no_violation(self) -> None:
        """v1 stub：不 yield。"""
        data = _mk_data()
        assert list(DioAp001Rule().check(data)) == []

    def test_with_channel_group_leaf_no_violation(self) -> None:
        """有 channel group leaf 但数据不足 → 不报。"""
        data = _mk_data(
            leaves=({"path": "Dio/DioChannelGroup/DioChannelGroupChannelRange", "raw": "0-7"},)
        )
        assert list(DioAp001Rule().check(data)) == []

    def test_non_xdm_data_skipped(self) -> None:
        """非 XdmLintData → skip。"""
        assert list(DioAp001Rule().check("not_xdm_data")) == []

    def test_rule_metadata(self) -> None:
        rule = DioAp001Rule()
        assert rule.rule_id == "DIO-AP-001"
        assert rule.severity_default == LintSeverity.ERROR
        assert rule.applies_to == "xdm"
