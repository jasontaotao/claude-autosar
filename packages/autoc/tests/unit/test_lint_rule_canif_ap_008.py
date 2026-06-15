"""Sprint 9.4 T9.4-α — CANIF-AP-008 单测。"""

from __future__ import annotations

from claude_autosar.core.bsw.lint import ArxmlLintData, LintSeverity
from claude_autosar.core.bsw.lint.rules.arxml_rules.canif_ap_008 import (
    CanIfAp008Rule,
)


def _mk_data(
    key_params: tuple[dict, ...] = (),
) -> ArxmlLintData:
    return ArxmlLintData(
        module_name="CanIf",
        ipdus=(),
        signals_by_ipdu={},
        key_params=key_params,
    )


class TestCanIfAp008Rule:
    def test_empty_data_no_violation(self) -> None:
        assert list(CanIfAp008Rule().check(_mk_data())) == []

    def test_with_length_param_no_violation_v1(self) -> None:
        """v1 MVP stub — 没 cross-reference 数据 → 0 报。"""
        data = _mk_data(
            key_params=({"container": "CanIf/X", "name": "CanIfTxPduLength", "value": "8"},)
        )
        assert list(CanIfAp008Rule().check(data)) == []

    def test_rule_metadata(self) -> None:
        rule = CanIfAp008Rule()
        assert rule.rule_id == "CANIF-AP-008"
        assert rule.severity_default == LintSeverity.ERROR

    def test_returns_iterable(self) -> None:
        result = CanIfAp008Rule().check(_mk_data())
        assert result is not None
        assert list(result) == []
