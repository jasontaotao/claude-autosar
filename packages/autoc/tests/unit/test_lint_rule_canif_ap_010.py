"""v2.4.1 — CANIF-AP-010 单测。

CanIfTxBuffer empty but TxProcessing enabled → WARNING。
"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import (
    ArxmlLintData,
    LintSeverity,
)
from claude_autosar.core.bsw.lint.rules.arxml_rules.canif_ap_010 import CanIfAp010Rule


def _mk_data(
    key_params: tuple[dict, ...] = (),
    module_name: str = "CanIf",
) -> ArxmlLintData:
    return ArxmlLintData(
        module_name=module_name,
        ipdus=(),
        signals_by_ipdu={},
        key_params=key_params,
    )


class TestCanIfAp010Rule:
    def test_stub_no_violation(self) -> None:
        """v1 stub：不 yield。"""
        data = _mk_data()
        assert list(CanIfAp010Rule().check(data)) == []

    def test_with_tx_param_no_violation(self) -> None:
        """有 Tx 参数但数据不足 → 不报。"""
        data = _mk_data(
            key_params=({"name": "CanIfTxProcessing", "value": "true"},)
        )
        assert list(CanIfAp010Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = CanIfAp010Rule()
        assert rule.rule_id == "CANIF-AP-010"
        assert rule.severity_default == LintSeverity.INFO
        assert rule.applies_to == "arxml"
